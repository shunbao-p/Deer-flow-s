# =============================================================
# 文件介绍：混合检索模块（HybridRetrievalModule）
# 目标：法律场景下结合实体级/主题级/向量检索，进行稳定混合召回。
# =============================================================
"""
法律混合检索模块
"""

import json
import logging
import math
import re
import time
import threading
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from neo4j import GraphDatabase

from .graph_indexing import GraphIndexingModule
from .query_intent_template import QueryIntent, intent_to_keywords, parse_query_intent, rule_based_parse_query_intent
from .text_safety import sanitize_query_text

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    content: str
    node_id: str
    node_type: str
    relevance_score: float
    retrieval_level: str
    metadata: Dict[str, Any]


class HybridRetrievalModule:
    """法律场景混合检索模块。"""

    def __init__(self, config, milvus_module, data_module, llm_client, llm_dispatcher: Optional[object] = None):
        self.config = config
        self.milvus_module = milvus_module
        self.data_module = data_module
        self.llm_client = llm_client
        self.llm_dispatcher = llm_dispatcher
        self.driver = None
        self.bm25_retriever = None
        self.graph_indexing = GraphIndexingModule(config, llm_client, llm_dispatcher=llm_dispatcher)
        self.graph_indexed = False
        # 统一分数契约（0~1，越大越相关）与融合权重
        self.entity_weight = 0.4
        self.topic_weight = 0.2
        self.vector_weight = 0.4
        self.min_final_score = 0.2
        self.intent_enabled = bool(getattr(self.config, "intent_enabled", True))
        self.rerank_enabled = bool(getattr(self.config, "rerank_enabled", True))
        self.true_rerank_enabled = bool(getattr(self.config, "true_rerank_enabled", True))
        self.reranker_model_name = str(
            getattr(self.config, "reranker_model_name", "BAAI/bge-reranker-v2-m3")
        ).strip()
        self.reranker_device = str(getattr(self.config, "reranker_device", "auto")).strip() or "auto"
        self.reranker_batch_size = max(1, int(getattr(self.config, "reranker_batch_size", 8)))
        self.reranker_max_length = max(128, int(getattr(self.config, "reranker_max_length", 512)))
        self._cross_encoder = None
        self._cross_encoder_lock = threading.Lock()
        self._cross_encoder_failed_reason = ""
        self._cross_encoder_failed_at = 0.0
        self._cross_encoder_retry_cooldown_seconds = max(
            0, int(getattr(self.config, "reranker_retry_cooldown_seconds", 60))
        )
        self.last_query_intent: Optional[QueryIntent] = None

    @staticmethod
    def _clamp_01(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

    def _normalize_fulltext_score(self, raw_score: Any) -> float:
        """将 Neo4j fulltext 原始分映射到 0~1。"""
        try:
            score = float(raw_score)
        except Exception:
            return 0.0
        if score <= 0:
            return 0.0
        return self._clamp_01(score / (score + 1.0))

    def _normalize_vector_score(self, raw_score: Any) -> float:
        """
        统一向量分语义：越大越相关，最终映射到 0~1。
        - score <= 0 统一视为无效相似度（0）
        - score 在 (0, 1] 直接使用
        - score > 1 截断为 1（异常尺度保护）
        """
        try:
            score = float(raw_score)
        except Exception:
            return 0.0
        if score <= 0:
            return 0.0
        if score <= 1.0:
            return self._clamp_01(score)
        return 1.0

    def _estimate_entity_relevance(self, entity_name: str, index_keys: List[str], keyword: str) -> float:
        name = (entity_name or "").lower()
        kw = (keyword or "").lower().strip()
        if not kw:
            return 0.45
        score = 0.45
        if name == kw:
            score += 0.35
        elif kw in name or name in kw:
            score += 0.25
        if any(kw in (k or "").lower() or (k or "").lower() in kw for k in (index_keys or [])):
            score += 0.15
        if re.search(r"第[0-9一二三四五六七八九十百千]+条", kw):
            score += 0.05
        return self._clamp_01(score)

    def _estimate_topic_relevance(
        self,
        keyword: str,
        relation_type: str = "",
        law_name: str = "",
        article_title: str = "",
        legal_domain: str = "",
        content: str = "",
    ) -> float:
        kw = (keyword or "").lower().strip()
        score = 0.35
        if not kw:
            return score
        if kw in (law_name or "").lower():
            score += 0.20
        if kw in (article_title or "").lower():
            score += 0.20
        if kw in (legal_domain or "").lower():
            score += 0.20
        if kw and kw in (content or "").lower():
            score += 0.15
        if relation_type in {"CITES", "RELATES_TO", "APPLIES_TO"}:
            score += 0.05
        return self._clamp_01(score)

    def _apply_result_contract(self, doc: Document) -> Document:
        """
        统一展示字段契约，避免“未知内容”由 metadata 缺失引起。
        """
        md = doc.metadata or {}
        node_type = str(md.get("node_type", ""))
        entity_name = str(md.get("entity_name", ""))
        law_name = str(md.get("law_name", "") or "")
        article_title = str(md.get("article_title", "") or "")
        article_id = str(md.get("article_id", "") or "")

        if not law_name and node_type == "LawDocument" and entity_name:
            law_name = entity_name
        if not article_title and node_type == "Article":
            article_title = entity_name or article_id

        fallback_title = ""
        if not fallback_title and doc.page_content:
            first_line = doc.page_content.strip().splitlines()[0] if doc.page_content.strip() else ""
            fallback_title = first_line[:60]

        display_title = (
            str(md.get("display_title", "") or "")
            or law_name
            or article_title
            or entity_name
            or article_id
            or fallback_title
            or "未知内容"
        )
        md.update(
            {
                "law_name": law_name,
                "article_title": article_title,
                "article_id": article_id,
                "display_title": display_title,
            }
        )
        doc.metadata = md
        return doc

    def _apply_intent_metadata(self, doc: Document, intent: Optional[QueryIntent]) -> Document:
        doc = self._apply_result_contract(doc)
        if intent is None:
            return doc
        md = doc.metadata or {}
        md.update(
            {
                "intent_question_type": intent.question_type,
                "intent_legal_domain": intent.legal_domain,
                "intent_subject": intent.subject,
                "intent_action": intent.action,
                "law_candidates": list(intent.law_candidates),
                "article_candidates": list(intent.article_candidates),
                "must_terms": list(intent.must_terms),
                "exclude_terms": list(intent.exclude_terms),
            }
        )
        doc.metadata = md
        return doc

    def _parse_query_intent(self, query: str) -> QueryIntent:
        query = sanitize_query_text(query)
        intent = parse_query_intent(
            query=query,
            llm_dispatcher=self.llm_dispatcher if self.intent_enabled else None,
            llm_client=self.llm_client if self.intent_enabled else None,
            model_name=getattr(self.config, "llm_model", ""),
            max_tokens=500,
        )
        self.last_query_intent = intent
        return intent

    def _assist_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 500):
        if self.llm_dispatcher is not None:
            response, provider, model = self.llm_dispatcher.create_chat_completion(
                role="assist",
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            logger.info("辅助调用通道(关键词): provider=%s model=%s", provider, model)
            return response
        return self.llm_client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )

    def initialize(self, chunks: List[Document]):
        """初始化检索系统。"""
        logger.info("初始化混合检索模块...")
        self.driver = GraphDatabase.driver(
            self.config.neo4j_uri,
            auth=(self.config.neo4j_user, self.config.neo4j_password),
        )

        if chunks:
            self.bm25_retriever = BM25Retriever.from_documents(chunks)
            logger.info("BM25检索器初始化完成，文档数量: %s", len(chunks))
        self._build_graph_index()

    def _build_graph_index(self):
        if self.graph_indexed:
            return
        logger.info("开始构建法律图索引...")
        try:
            self.graph_indexing.create_entity_key_values(
                self.data_module.law_documents,
                self.data_module.articles,
                self.data_module.compliance_steps,
                self.data_module.risk_scenarios,
            )
            relationships = self._extract_relationships_from_graph()
            self.graph_indexing.create_relation_key_values(relationships)
            self.graph_indexing.deduplicate_entities_and_relations()
            self.graph_indexed = True
            logger.info("法律图索引构建完成: %s", self.graph_indexing.get_statistics())
        except Exception as e:
            logger.error("构建图索引失败: %s", e)

    def _extract_relationships_from_graph(self) -> List[Tuple[str, str, str]]:
        relationships: List[Tuple[str, str, str]] = []
        relation_types = getattr(self.config, "graph_relation_types", [])
        relation_filter = ""
        params: Dict[str, Any] = {}
        if relation_types:
            relation_filter = "AND type(r) IN $relation_types"
            params["relation_types"] = relation_types

        query = f"""
        MATCH (source)-[r]->(target)
        WHERE (source:LawDocument OR source:Article OR source:RiskScenario OR source:ComplianceStep)
          AND (target:LawDocument OR target:Article OR target:RiskScenario OR target:ComplianceStep)
          {relation_filter}
        RETURN
            COALESCE(toString(source.nodeId), elementId(source)) AS source_id,
            type(r) AS relation_type,
            COALESCE(toString(target.nodeId), elementId(target)) AS target_id
        LIMIT 3000
        """

        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(query, params):
                    relationships.append(
                        (record["source_id"], record["relation_type"], record["target_id"])
                    )
        except Exception as e:
            logger.error("提取法律图关系失败: %s", e)
        return relationships

    def extract_query_keywords(
        self,
        query: str,
        intent: Optional[QueryIntent] = None,
    ) -> Tuple[List[str], List[str]]:
        """提取法律查询关键词（实体级 + 主题级）。"""
        query = sanitize_query_text(query)
        if not query:
            return [], []

        if self.intent_enabled:
            resolved_intent = intent or self._parse_query_intent(query)
            intent_keywords = intent_to_keywords(resolved_intent, query)
            entity_keywords = intent_keywords.get("entity_keywords", [])
            topic_keywords = intent_keywords.get("topic_keywords", [])
            if entity_keywords or topic_keywords:
                return entity_keywords, topic_keywords

        prompt = f"""
        你是法律检索助手。请从下述问题提取两类关键词，并返回 JSON。

        问题：{query}

        1) entity_keywords：法规名、条文号、主体、行为、具体制度名
        2) topic_keywords：劳动争议、合同履行、数据合规、责任承担、程序义务等主题词

        返回格式：
        {{
          "entity_keywords": ["关键词1", "关键词2"],
          "topic_keywords": ["主题1", "主题2"]
        }}
        """
        try:
            response = self._assist_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            result = self._safe_json_loads(response.choices[0].message.content.strip())
            entity_keywords = [k.strip() for k in result.get("entity_keywords", []) if k and k.strip()]
            topic_keywords = [k.strip() for k in result.get("topic_keywords", []) if k and k.strip()]
            if entity_keywords or topic_keywords:
                return entity_keywords, topic_keywords
        except Exception as e:
            logger.error("关键词提取失败，使用规则降级: %s", e)
        return self._rule_based_keywords(query)

    def _rule_based_keywords(self, query: str) -> Tuple[List[str], List[str]]:
        query = sanitize_query_text(query)
        if not query:
            return [], []

        entity_keywords: List[str] = []
        topic_keywords: List[str] = []

        article_hits = re.findall(r"第[0-9一二三四五六七八九十百千]+条", query)
        entity_keywords.extend(article_hits)

        legal_terms = ["劳动合同法", "民法典", "个人信息保护法", "劳动争议", "试用期", "辞退", "赔偿", "社保"]
        for term in legal_terms:
            if term in query:
                if term in {"劳动争议", "试用期", "辞退", "赔偿", "社保"}:
                    topic_keywords.append(term)
                else:
                    entity_keywords.append(term)

        if not entity_keywords:
            entity_keywords = [query[:12]]
        if not topic_keywords:
            topic_keywords = [query[:12]]
        return entity_keywords[:5], topic_keywords[:5]

    def _document_match_text(self, doc: Document) -> str:
        md = doc.metadata or {}
        fields = [
            doc.page_content or "",
            str(md.get("display_title", "") or ""),
            str(md.get("law_name", "") or ""),
            str(md.get("article_title", "") or ""),
            str(md.get("article_id", "") or ""),
        ]
        return " ".join(fields).lower()

    def _calc_must_term_coverage(self, text: str, must_terms: List[str]) -> Tuple[int, float]:
        terms = [sanitize_query_text(x).strip().lower() for x in (must_terms or []) if x and str(x).strip()]
        if not terms:
            return 0, 0.0
        hit_count = sum(1 for term in terms if term and term in text)
        return hit_count, self._clamp_01(hit_count / float(len(terms)))

    def _calc_exclude_term_hits(self, text: str, exclude_terms: List[str]) -> int:
        terms = [sanitize_query_text(x).strip().lower() for x in (exclude_terms or []) if x and str(x).strip()]
        return sum(1 for term in terms if term and term in text)

    def _calc_exact_title_or_article_hit(self, doc: Document, intent: QueryIntent) -> float:
        if intent is None:
            return 0.0
        text = self._document_match_text(doc)
        law_hits = any(term.lower() in text for term in intent.law_candidates)
        article_hits = any(term.lower() in text for term in intent.article_candidates)
        return 1.0 if law_hits or article_hits else 0.0

    def _lightweight_rerank(
        self,
        docs: List[Document],
        intent: Optional[QueryIntent],
        top_k: int,
    ) -> List[Document]:
        if not docs:
            return []

        if intent is None:
            for doc in docs:
                md = doc.metadata or {}
                md["rerank_score"] = round(
                    self._clamp_01(md.get("final_score", md.get("relevance_score", 0.0))),
                    4,
                )
                md["must_terms_hit_count"] = int(md.get("must_terms_hit_count", 0))
                md["must_terms_hit_ratio"] = float(md.get("must_terms_hit_ratio", 0.0))
                md["rerank_contract"] = "no_intent_fallback_to_final_score"
                doc.metadata = md
            return docs[:top_k]

        reranked: List[Document] = []
        for doc in docs:
            doc = self._apply_intent_metadata(doc, intent)
            md = doc.metadata or {}
            base_score = self._clamp_01(md.get("final_score", md.get("relevance_score", 0.0)))
            text = self._document_match_text(doc)
            must_hit_count, must_hit_ratio = self._calc_must_term_coverage(text, intent.must_terms)
            exact_hit = self._calc_exact_title_or_article_hit(doc, intent)
            exclude_hits = self._calc_exclude_term_hits(text, intent.exclude_terms)

            penalty = 0.1 if exclude_hits > 0 else 0.0
            rerank_score = self._clamp_01(0.60 * base_score + 0.25 * must_hit_ratio + 0.15 * exact_hit - penalty)

            md.update(
                {
                    "rerank_score": round(rerank_score, 4),
                    "must_terms_hit_count": int(must_hit_count),
                    "must_terms_hit_ratio": round(must_hit_ratio, 4),
                    "exact_title_or_article_hit": round(exact_hit, 4),
                    "exclude_terms_hit_count": int(exclude_hits),
                    "rerank_contract": "rerank=0.60*final+0.25*must+0.15*exact-penalty",
                }
            )
            doc.metadata = md
            reranked.append(doc)

        reranked.sort(key=lambda x: x.metadata.get("rerank_score", 0.0), reverse=True)
        return reranked[:top_k]

    def _resolve_reranker_device(self) -> str:
        preferred = str(self.reranker_device or "auto").strip().lower()
        if preferred and preferred != "auto":
            return preferred
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def _ensure_cross_encoder(self):
        if self._cross_encoder is not None:
            return self._cross_encoder
        if self._cross_encoder_failed_reason:
            elapsed = time.time() - float(self._cross_encoder_failed_at or 0.0)
            if elapsed < float(self._cross_encoder_retry_cooldown_seconds):
                raise RuntimeError(self._cross_encoder_failed_reason)
        if not self.true_rerank_enabled:
            raise RuntimeError("true_rerank_disabled")
        if not self.reranker_model_name:
            raise RuntimeError("empty_reranker_model_name")

        with self._cross_encoder_lock:
            if self._cross_encoder is not None:
                return self._cross_encoder
            if self._cross_encoder_failed_reason:
                elapsed = time.time() - float(self._cross_encoder_failed_at or 0.0)
                if elapsed < float(self._cross_encoder_retry_cooldown_seconds):
                    raise RuntimeError(self._cross_encoder_failed_reason)
                logger.warning(
                    "Cross-Encoder初始化失败后达到重试窗口，开始重试: reason=%s elapsed=%.1fs cooldown=%ss",
                    self._cross_encoder_failed_reason,
                    elapsed,
                    self._cross_encoder_retry_cooldown_seconds,
                )
                self._cross_encoder_failed_reason = ""
                self._cross_encoder_failed_at = 0.0
            try:
                from sentence_transformers import CrossEncoder

                resolved_device = self._resolve_reranker_device()
                self._cross_encoder = CrossEncoder(
                    self.reranker_model_name,
                    device=resolved_device,
                    max_length=self.reranker_max_length,
                    trust_remote_code=True,
                )
                logger.info(
                    "Cross-Encoder重排模型加载完成: model=%s device=%s",
                    self.reranker_model_name,
                    resolved_device,
                )
                return self._cross_encoder
            except Exception as exc:
                self._cross_encoder_failed_reason = f"cross_encoder_init_failed:{exc.__class__.__name__}:{exc}"
                self._cross_encoder_failed_at = time.time()
                logger.error("Cross-Encoder重排模型初始化失败: %s", self._cross_encoder_failed_reason)
                raise RuntimeError(self._cross_encoder_failed_reason) from exc

    def prewarm_cross_encoder(self, query: str = "法律咨询预热", passage: str = "预热样本") -> Dict[str, Any]:
        """
        显式预热Cross-Encoder，避免首个真实请求承担全部冷启动开销。
        """
        if not self.rerank_enabled:
            return {"ready": False, "reason": "rerank_disabled", "model": self.reranker_model_name}
        if not self.true_rerank_enabled:
            return {"ready": False, "reason": "true_rerank_disabled", "model": self.reranker_model_name}

        started_at = time.time()
        try:
            model = self._ensure_cross_encoder()
            model.predict(
                [[str(query or "法律咨询预热"), str(passage or "预热样本")]],
                batch_size=1,
                show_progress_bar=False,
            )
            latency_ms = int((time.time() - started_at) * 1000)
            return {
                "ready": True,
                "reason": "",
                "model": self.reranker_model_name,
                "latency_ms": latency_ms,
            }
        except Exception as exc:
            latency_ms = int((time.time() - started_at) * 1000)
            reason = str(exc) or "cross_encoder_prewarm_failed"
            return {
                "ready": False,
                "reason": reason,
                "model": self.reranker_model_name,
                "latency_ms": latency_ms,
            }

    def _build_rerank_passage(self, doc: Document) -> str:
        md = doc.metadata or {}
        fields = [
            str(md.get("law_name", "") or ""),
            str(md.get("article_id", "") or ""),
            str(md.get("article_title", "") or ""),
            str(md.get("display_title", "") or ""),
            (doc.page_content or "")[:1400],
        ]
        return "\n".join(x for x in fields if x).strip()

    @staticmethod
    def _sigmoid(value: float) -> float:
        try:
            v = float(value)
        except Exception:
            return 0.0
        v = max(-60.0, min(60.0, v))
        return 1.0 / (1.0 + math.exp(-v))

    def _score_for_fusion(self, doc: Document, key: str, fallback: float = 0.0) -> float:
        md = doc.metadata or {}
        if key in md:
            return self._clamp_01(md.get(key, fallback))
        return self._clamp_01(fallback)

    def _diversity_key(self, doc: Document) -> str:
        md = doc.metadata or {}
        law_name = str(md.get("law_name", "") or "").strip()
        article_id = str(md.get("article_id", "") or "").strip()
        if law_name and article_id:
            return f"{law_name}::{article_id}"
        return ""

    def _select_diverse_top_k(self, docs: List[Document], top_k: int) -> List[Document]:
        selected: List[Document] = []
        overflow: List[Document] = []
        used = set()

        for doc in docs:
            key = self._diversity_key(doc)
            if key and key in used:
                overflow.append(doc)
                continue
            if key:
                used.add(key)
            selected.append(doc)
            if len(selected) >= top_k:
                break

        if len(selected) < top_k:
            for doc in overflow:
                selected.append(doc)
                if len(selected) >= top_k:
                    break
        return selected[:top_k]

    def _cross_encoder_rerank(
        self,
        query: str,
        docs: List[Document],
        top_k: int,
    ) -> List[Document]:
        model = self._ensure_cross_encoder()
        pairs = [[query, self._build_rerank_passage(doc)] for doc in docs]
        raw_scores = model.predict(
            pairs,
            batch_size=self.reranker_batch_size,
            show_progress_bar=False,
        )

        reranked: List[Document] = []
        for idx, doc in enumerate(docs):
            md = doc.metadata or {}
            try:
                raw = float(raw_scores[idx])
            except Exception:
                raw = 0.0
            score_rerank = self._clamp_01(self._sigmoid(raw))
            score_vector = self._score_for_fusion(doc, "score_vector", fallback=md.get("score", 0.0))
            score_bm25 = self._score_for_fusion(doc, "score_bm25", fallback=0.0)
            final_rank_score = self._clamp_01(0.75 * score_rerank + 0.15 * score_vector + 0.10 * score_bm25)

            md.update(
                {
                    "score_rerank": round(score_rerank, 4),
                    "rerank_score_raw": round(raw, 6),
                    "rerank_score": round(final_rank_score, 4),
                    "rerank_model": self.reranker_model_name,
                    "rerank_contract": "0.75*rerank+0.15*vector+0.10*bm25",
                    "rerank_fallback_reason": "",
                }
            )
            doc.metadata = md
            reranked.append(doc)

        reranked.sort(key=lambda x: x.metadata.get("rerank_score", 0.0), reverse=True)
        return self._select_diverse_top_k(reranked, top_k=top_k)

    def rerank_documents(
        self,
        query: str,
        docs: List[Document],
        top_k: int = 5,
        intent: Optional[QueryIntent] = None,
    ) -> List[Document]:
        query = sanitize_query_text(query)
        if not query or not docs:
            return []
        limit = max(1, int(top_k))

        started_at = time.time()
        fallback_reason = ""
        if self.rerank_enabled and self.true_rerank_enabled:
            try:
                reranked = self._cross_encoder_rerank(query, docs, top_k=limit)
                latency_ms = int((time.time() - started_at) * 1000)
                for doc in reranked:
                    md = doc.metadata or {}
                    md["rerank_latency_ms"] = latency_ms
                    doc.metadata = md
                return reranked[:limit]
            except Exception as exc:
                fallback_reason = f"cross_encoder_failed:{exc.__class__.__name__}"
                logger.warning("Cross-Encoder重排失败，降级轻量重排: %s", exc)
        elif not self.rerank_enabled:
            fallback_reason = "rerank_disabled"
        else:
            fallback_reason = "true_rerank_disabled"

        resolved_intent = intent
        if resolved_intent is None:
            # 仅在降级轻量重排时才尝试解析意图，避免每次请求额外触发一次LLM调用。
            if self.intent_enabled:
                try:
                    resolved_intent = self._parse_query_intent(query)
                except Exception as exc:
                    logger.warning("降级重排意图解析失败，继续无意图重排: %s", exc)

        baseline_docs = self._lightweight_rerank(docs, intent=resolved_intent, top_k=limit)
        latency_ms = int((time.time() - started_at) * 1000)
        for doc in baseline_docs:
            md = doc.metadata or {}
            md["rerank_model"] = "lightweight_fallback"
            md["rerank_fallback_reason"] = fallback_reason
            md["rerank_latency_ms"] = latency_ms
            doc.metadata = md
        return baseline_docs[:limit]

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def entity_level_retrieval(self, entity_keywords: List[str], top_k: int = 5) -> List[RetrievalResult]:
        """实体级检索：优先基于法律图索引。"""
        results: List[RetrievalResult] = []
        for keyword in entity_keywords:
            for entity in self.graph_indexing.search_entities(keyword, limit=top_k):
                node_id = entity.metadata["node_id"]
                neighbors = self._get_node_neighbors(node_id, max_neighbors=3)
                content = entity.value_content
                if neighbors:
                    content += f"\n相关节点: {', '.join(neighbors)}"
                results.append(
                    RetrievalResult(
                        content=content,
                        node_id=node_id,
                        node_type=entity.entity_type,
                        relevance_score=self._estimate_entity_relevance(
                            entity_name=entity.entity_name,
                            index_keys=entity.index_keys,
                            keyword=keyword,
                        ),
                        retrieval_level="entity",
                        metadata={
                            "entity_name": entity.entity_name,
                            "entity_type": entity.entity_type,
                            "law_name": entity.entity_name if entity.entity_type == "LawDocument" else "",
                            "article_title": entity.entity_name if entity.entity_type == "Article" else "",
                            "article_id": str(entity.metadata.get("properties", {}).get("articleId", "")),
                            "matched_keyword": keyword,
                            "index_keys": entity.index_keys,
                        },
                    )
                )

        if len(results) < top_k:
            results.extend(self._neo4j_entity_level_search(entity_keywords, top_k - len(results)))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return self._dedup_results(results)[:top_k]

    def _neo4j_entity_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        results: List[RetrievalResult] = []
        index_name = getattr(self.config, "neo4j_legal_fulltext_index", "legal_fulltext_idx")
        query = """
        UNWIND $keywords AS keyword
        CALL db.index.fulltext.queryNodes($index_name, keyword) YIELD node, score
        RETURN
            COALESCE(toString(node.nodeId), elementId(node)) AS node_id,
            labels(node) AS labels,
            COALESCE(node.name, node.title, node.articleId, '') AS display_name,
            COALESCE(node.articleId, '') AS article_id,
            COALESCE(node.title, '') AS article_title,
            COALESCE(node.content, node.description, '') AS content,
            keyword AS matched_keyword,
            score
        ORDER BY score DESC
        LIMIT $limit
        """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(
                    query, {"keywords": keywords, "limit": limit, "index_name": index_name}
                ):
                    labels = record["labels"] or []
                    node_type = labels[0] if labels else "LegalNode"
                    content = f"名称: {record['display_name']}"
                    if record["article_id"]:
                        content += f"\n条文编号: {record['article_id']}"
                    if record["article_title"]:
                        content += f"\n条文标题: {record['article_title']}"
                    if record["content"]:
                        content += f"\n内容: {record['content'][:400]}"
                    results.append(
                        RetrievalResult(
                            content=content,
                            node_id=record["node_id"],
                            node_type=node_type,
                            relevance_score=self._normalize_fulltext_score(record["score"]),
                            retrieval_level="entity",
                            metadata={
                                "law_name": record["display_name"] if node_type == "LawDocument" else "",
                                "article_id": record["article_id"],
                                "article_title": record["article_title"],
                                "entity_name": record["display_name"],
                                "matched_keyword": record["matched_keyword"],
                                "raw_score": record["score"],
                                "source": "neo4j_fulltext",
                            },
                        )
                    )
        except Exception as e:
            logger.error("Neo4j实体检索失败: %s", e)
        return results

    def topic_level_retrieval(self, topic_keywords: List[str], top_k: int = 5) -> List[RetrievalResult]:
        """主题级检索：优先关系索引，再降级 Neo4j 查询。"""
        results: List[RetrievalResult] = []
        for keyword in topic_keywords:
            relations = self.graph_indexing.search_relations(keyword, limit=top_k)
            for relation in relations:
                source = self.graph_indexing.entity_kv_store.get(relation.source_entity)
                target = self.graph_indexing.entity_kv_store.get(relation.target_entity)
                if not source or not target:
                    continue
                content = (
                    f"主题: {keyword}\n"
                    f"{relation.value_content}\n"
                    f"关系说明: {source.entity_name} 与 {target.entity_name}"
                )
                results.append(
                    RetrievalResult(
                        content=content,
                        node_id=relation.source_entity,
                        node_type=source.entity_type,
                        relevance_score=self._estimate_topic_relevance(
                            keyword=keyword,
                            relation_type=relation.relation_type,
                            law_name=source.entity_name if source.entity_type == "LawDocument" else "",
                            article_title=source.metadata.get("properties", {}).get("title", ""),
                        ),
                        retrieval_level="topic",
                        metadata={
                            "relation_type": relation.relation_type,
                            "law_name": source.entity_name if source.entity_type == "LawDocument" else "",
                            "article_id": source.metadata.get("properties", {}).get("articleId", ""),
                            "article_title": source.metadata.get("properties", {}).get("title", ""),
                            "entity_name": source.entity_name,
                            "matched_keyword": keyword,
                            "source": "graph_relation",
                        },
                    )
                )

        if len(results) < top_k:
            results.extend(self._neo4j_topic_level_search(topic_keywords, top_k - len(results)))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return self._dedup_results(results)[:top_k]

    def _neo4j_topic_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        results: List[RetrievalResult] = []
        query = """
        UNWIND $keywords AS keyword
        MATCH (a:Article)-[:BELONGS_TO_DOMAIN]->(d:LegalDomain)
        OPTIONAL MATCH (law:LawDocument)-[:HAS_ARTICLE]->(a)
        WHERE d.name CONTAINS keyword
           OR COALESCE(a.content, '') CONTAINS keyword
           OR COALESCE(a.title, '') CONTAINS keyword
        RETURN
            COALESCE(toString(a.nodeId), elementId(a)) AS node_id,
            COALESCE(law.name, '') AS law_name,
            COALESCE(a.articleId, '') AS article_id,
            COALESCE(a.title, '') AS article_title,
            COALESCE(d.name, '') AS legal_domain,
            COALESCE(a.content, '') AS content,
            keyword AS matched_keyword
        LIMIT $limit
        """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(query, {"keywords": keywords, "limit": limit}):
                    text = (
                        f"法规: {record['law_name']}\n"
                        f"条文: {record['article_id']} {record['article_title']}\n"
                        f"领域: {record['legal_domain']}\n"
                        f"内容: {record['content'][:360]}"
                    )
                    results.append(
                        RetrievalResult(
                            content=text,
                            node_id=record["node_id"],
                            node_type="Article",
                            relevance_score=self._estimate_topic_relevance(
                                keyword=record["matched_keyword"],
                                law_name=record["law_name"],
                                article_title=record["article_title"],
                                legal_domain=record["legal_domain"],
                                content=record["content"],
                            ),
                            retrieval_level="topic",
                            metadata={
                                "law_name": record["law_name"],
                                "article_id": record["article_id"],
                                "article_title": record["article_title"],
                                "legal_domain": record["legal_domain"],
                                "matched_keyword": record["matched_keyword"],
                                "source": "neo4j_topic",
                            },
                        )
                    )
        except Exception as e:
            logger.error("Neo4j主题检索失败: %s", e)
        return results

    def dual_level_retrieval(
        self,
        query: str,
        top_k: int = 5,
        intent: Optional[QueryIntent] = None,
    ) -> List[Document]:
        query = sanitize_query_text(query)
        if not query:
            return []

        entity_keywords, topic_keywords = self.extract_query_keywords(query, intent=intent)
        entity_results = self.entity_level_retrieval(entity_keywords, top_k)
        topic_results = self.topic_level_retrieval(topic_keywords, top_k)

        # 这里不能跨 retrieval_level 去重，否则同一节点的“实体+主题”双信号会被截断。
        all_results = entity_results + topic_results
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        documents: List[Document] = []
        for result in all_results[: top_k * 2]:
            doc = Document(
                page_content=result.content,
                metadata={
                    "node_id": result.node_id,
                    "node_type": result.node_type,
                    "retrieval_level": result.retrieval_level,
                    "relevance_score": result.relevance_score,
                    "search_type": "dual_level",
                    **result.metadata,
                },
            )
            documents.append(self._apply_intent_metadata(doc, intent))
        return documents

    def vector_search_enhanced(
        self,
        query: str,
        top_k: int = 5,
        intent: Optional[QueryIntent] = None,
        retrieval_scope: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        query = sanitize_query_text(query)
        if not query:
            return []

        try:
            vector_filters = self._build_vector_filters(retrieval_scope)
            vector_docs = self.milvus_module.similarity_search(query, k=top_k * 2, filters=vector_filters)
            enhanced_docs: List[Document] = []
            for result in vector_docs:
                content = result.get("text", "")
                metadata = result.get("metadata", {})
                node_id = metadata.get("node_id", "")
                if node_id:
                    neighbors = self._get_node_neighbors(node_id, max_neighbors=2)
                    if neighbors:
                        content += f"\n关联节点: {', '.join(neighbors)}"

                law_name = metadata.get("law_name") or metadata.get("recipe_name", "")
                doc = Document(
                    page_content=content,
                    metadata={
                        **metadata,
                        "law_name": law_name,
                        "article_id": metadata.get("article_id", ""),
                        "article_title": metadata.get("article_title", ""),
                        "search_type": "vector_enhanced",
                        "score": result.get("score", 0.0),
                    },
                )
                enhanced_docs.append(self._apply_intent_metadata(doc, intent))
            return enhanced_docs[: top_k * 2]
        except Exception as e:
            logger.error("向量增强检索失败: %s", e)
            return []

    def _build_vector_filters(self, retrieval_scope: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not retrieval_scope:
            return None

        chat_id = str(retrieval_scope.get("chat_id", "")).strip()
        raw_file_ids = retrieval_scope.get("active_file_ids")
        if not chat_id or not isinstance(raw_file_ids, list):
            return None

        file_ids = [str(file_id).strip() for file_id in raw_file_ids if str(file_id).strip()]
        if not file_ids:
            return None

        return {"chat_id": chat_id, "file_id": file_ids}

    def bm25_search_enhanced(
        self,
        query: str,
        top_k: int = 5,
        intent: Optional[QueryIntent] = None,
    ) -> List[Document]:
        query = sanitize_query_text(query)
        if not query or self.bm25_retriever is None:
            return []

        try:
            raw_docs = self.bm25_retriever.invoke(query)
        except Exception as e:
            logger.error("BM25检索失败: %s", e)
            return []

        if not raw_docs:
            return []

        limit = min(len(raw_docs), max(1, top_k * 2))
        if limit == 1:
            normalized_scores = [1.0]
        else:
            normalized_scores = [1.0 - (rank / float(limit - 1)) for rank in range(limit)]

        enhanced_docs: List[Document] = []
        for rank, raw_doc in enumerate(raw_docs[:limit], start=1):
            metadata = dict(raw_doc.metadata or {})
            bm25_score = self._clamp_01(normalized_scores[rank - 1])
            doc = Document(
                page_content=raw_doc.page_content,
                metadata={
                    **metadata,
                    "search_type": "bm25",
                    "search_method": "bm25",
                    "bm25_rank": rank,
                    "score_bm25": round(bm25_score, 4),
                },
            )
            enhanced_docs.append(self._apply_intent_metadata(doc, intent))
        return enhanced_docs

    def _get_node_neighbors(self, node_id: str, max_neighbors: int = 3) -> List[str]:
        relation_types = getattr(self.config, "graph_relation_types", [])
        relation_filter = ""
        params: Dict[str, Any] = {"node_id": str(node_id), "limit": max_neighbors}
        if relation_types:
            relation_filter = "AND type(r) IN $relation_types"
            params["relation_types"] = relation_types

        query = f"""
        MATCH (n)-[r]-(neighbor)
        WHERE COALESCE(toString(n.nodeId), elementId(n)) = $node_id
          {relation_filter}
        RETURN COALESCE(neighbor.name, neighbor.title, neighbor.articleId, '') AS name
        LIMIT $limit
        """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                return [record["name"] for record in session.run(query, params) if record["name"]]
        except Exception as e:
            logger.error("获取邻居节点失败: %s", e)
            return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        retrieval_scope: Optional[Dict[str, Any]] = None,
        apply_rerank: bool = True,
        use_rule_intent: bool = False,
    ) -> List[Document]:
        """统一契约融合：字段统一 + 分数统一 + 加权排序。"""
        query = sanitize_query_text(query)
        if not query:
            return []

        if self.intent_enabled:
            if use_rule_intent:
                intent = rule_based_parse_query_intent(query)
            else:
                intent = self._parse_query_intent(query)
        else:
            intent = None

        dual_docs = self.dual_level_retrieval(query, top_k, intent=intent)
        vector_docs = self.vector_search_enhanced(
            query,
            top_k,
            intent=intent,
            retrieval_scope=retrieval_scope,
        )
        bm25_docs = self.bm25_search_enhanced(query, top_k, intent=intent)
        candidates: Dict[str, Dict[str, Any]] = {}

        def doc_key(doc: Document) -> str:
            node_id = str(doc.metadata.get("node_id", "")).strip()
            if node_id:
                return node_id
            return str(hash(doc.page_content[:200]))

        def ensure_candidate(key: str, doc: Document) -> Dict[str, Any]:
            if key not in candidates:
                candidates[key] = {
                    "doc": self._apply_intent_metadata(doc, intent),
                    "entity_score": 0.0,
                    "topic_score": 0.0,
                    "vector_score": 0.0,
                    "bm25_score": 0.0,
                }
            return candidates[key]

        for doc in dual_docs:
            doc = self._apply_intent_metadata(doc, intent)
            key = doc_key(doc)
            candidate = ensure_candidate(key, doc)
            raw_score = self._clamp_01(doc.metadata.get("relevance_score", 0.0))
            level = doc.metadata.get("retrieval_level", "")
            if level == "entity":
                candidate["entity_score"] = max(candidate["entity_score"], raw_score)
            elif level == "topic":
                candidate["topic_score"] = max(candidate["topic_score"], raw_score)
            else:
                candidate["topic_score"] = max(candidate["topic_score"], raw_score)
            candidate["doc"] = self._apply_intent_metadata(candidate["doc"], intent)

        for doc in vector_docs:
            doc = self._apply_intent_metadata(doc, intent)
            key = doc_key(doc)
            candidate = ensure_candidate(key, doc)
            vector_score = self._normalize_vector_score(doc.metadata.get("score", 0.0))
            candidate["vector_score"] = max(candidate["vector_score"], vector_score)
            if not candidate["doc"].metadata.get("law_name") and doc.metadata.get("law_name"):
                candidate["doc"] = doc
            candidate["doc"] = self._apply_intent_metadata(candidate["doc"], intent)

        for doc in bm25_docs:
            doc = self._apply_intent_metadata(doc, intent)
            key = doc_key(doc)
            candidate = ensure_candidate(key, doc)
            bm25_score = self._clamp_01(doc.metadata.get("score_bm25", 0.0))
            candidate["bm25_score"] = max(candidate["bm25_score"], bm25_score)
            candidate["topic_score"] = max(candidate["topic_score"], bm25_score)
            if not candidate["doc"].metadata.get("display_title") and doc.metadata.get("display_title"):
                candidate["doc"] = doc
            candidate["doc"] = self._apply_intent_metadata(candidate["doc"], intent)

        ranked_docs: List[Document] = []
        for candidate in candidates.values():
            doc = candidate["doc"]
            entity_score = candidate["entity_score"]
            topic_score = candidate["topic_score"]
            vector_score = candidate["vector_score"]
            bm25_score = candidate["bm25_score"]
            final_score = (
                self.entity_weight * entity_score
                + self.topic_weight * topic_score
                + self.vector_weight * vector_score
            )
            doc.metadata.update(
                {
                    "search_method": "contract_fusion",
                    "score_entity": round(entity_score, 4),
                    "score_topic": round(topic_score, 4),
                    "score_vector": round(vector_score, 4),
                    "score_bm25": round(bm25_score, 4),
                    "final_score": round(self._clamp_01(final_score), 4),
                    "score_contract": "final=0.4*entity+0.2*topic+0.4*vector",
                    "rerank_enabled": bool(self.rerank_enabled),
                }
            )
            ranked_docs.append(doc)

        ranked_docs.sort(key=lambda x: x.metadata.get("final_score", 0.0), reverse=True)
        filtered_docs = [d for d in ranked_docs if d.metadata.get("final_score", 0.0) >= self.min_final_score]
        selected_docs = filtered_docs if filtered_docs else ranked_docs

        if apply_rerank:
            return self.rerank_documents(query, selected_docs, top_k=top_k, intent=intent)

        pooled_docs = selected_docs[:top_k]
        for doc in pooled_docs:
            md = doc.metadata or {}
            if "rerank_score" not in md:
                md["rerank_score"] = round(
                    self._clamp_01(md.get("final_score", md.get("relevance_score", 0.0))),
                    4,
                )
            md.setdefault("rerank_model", "not_applied")
            md.setdefault("rerank_fallback_reason", "route_pool_only")
            doc.metadata = md
        return pooled_docs

    def _dedup_results(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        deduped: List[RetrievalResult] = []
        seen = set()
        for result in results:
            key = (result.node_id, result.node_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        return deduped

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j连接已关闭")
