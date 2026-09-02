# =============================================================
# 文件介绍：智能查询路由器（IntelligentQueryRouter）
# 目标：法律问题自动路由到传统检索、图RAG检索或组合检索。
# =============================================================
"""
法律智能查询路由器
"""

import json
import logging
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
from enum import Enum

from langchain_core.documents import Document
from .text_safety import sanitize_query_text

logger = logging.getLogger(__name__)


class SearchStrategy(Enum):
    HYBRID_TRADITIONAL = "hybrid_traditional"
    GRAPH_RAG = "graph_rag"
    COMBINED = "combined"


@dataclass
class QueryAnalysis:
    query_complexity: float
    relationship_intensity: float
    reasoning_required: bool
    entity_count: int
    recommended_strategy: SearchStrategy
    confidence: float
    reasoning: str


class IntelligentQueryRouter:
    """法律场景智能查询路由。"""

    LEGAL_QUERY_TERMS = (
        "刑法",
        "民法典",
        "劳动合同法",
        "未成年人保护法",
        "道路交通安全法",
        "消费者权益保护法",
        "个人信息保护法",
        "数据安全法",
        "网络安全法",
        "行政处罚法",
        "刑事诉讼法",
        "民事诉讼法",
    )

    def __init__(
        self,
        traditional_retrieval,
        graph_rag_retrieval,
        llm_client,
        config,
        llm_dispatcher: Optional[object] = None,
    ):
        self.traditional_retrieval = traditional_retrieval
        self.graph_rag_retrieval = graph_rag_retrieval
        self.llm_client = llm_client
        self.config = config
        self.llm_dispatcher = llm_dispatcher
        self.route_stats = {
            "traditional_count": 0,
            "graph_rag_count": 0,
            "combined_count": 0,
            "total_queries": 0,
            "graph_route_count": 0,
            "graph_grounding_success_count": 0,
            "graph_empty_no_grounding_count": 0,
            "graph_fallback_to_traditional_count": 0,
        }
        self.last_route_trace: Dict[str, Any] = {}

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    def _reset_last_route_trace(self, strategy: SearchStrategy, reason: str = "") -> None:
        self.last_route_trace = {
            "recommended_strategy": strategy.value,
            "graph_attempted": strategy in {SearchStrategy.GRAPH_RAG, SearchStrategy.COMBINED},
            "graph_empty_reason": reason,
            "graph_query_type": "",
            "graph_source_candidate_count": 0,
            "graph_source_hit_count": 0,
            "graph_target_candidate_count": 0,
            "graph_target_hit_count": 0,
            "graph_result_count": 0,
            "source_grounding_mode": "",
            "target_grounding_mode": "",
            "graph_fallback_to_traditional": False,
            "final_document_count": 0,
        }

    def get_last_route_trace(self) -> Dict[str, Any]:
        return dict(self.last_route_trace or {})

    def _has_legal_query_signal(self, query: str) -> bool:
        query = sanitize_query_text(query)
        if not query:
            return False
        if any(term in query for term in self.LEGAL_QUERY_TERMS):
            return True
        if "《" in query and "》" in query:
            return True
        if "第" in query and "条" in query:
            return True
        return False

    @staticmethod
    def _is_graph_candidate(doc: Document) -> bool:
        md = doc.metadata or {}
        source = str(md.get("search_source", "") or "")
        search_type = str(md.get("search_type", "") or "")
        return source == "graph_rag" or search_type in {"graph_path", "knowledge_subgraph"}

    def _is_graph_high_quality(self, doc: Document, query: str, has_legal_signal: bool) -> bool:
        md = doc.metadata or {}
        query = sanitize_query_text(query)
        law_name = str(md.get("law_name", "") or "").strip()
        article_id = str(md.get("article_id", "") or "").strip()
        has_structured = bool(law_name and article_id)

        min_relevance = self._safe_float(getattr(self.config, "graph_quality_min_relevance", 0.55))
        relevance = self._doc_pre_rank_score(doc)
        has_score = relevance >= min_relevance
        if has_score:
            return True

        # 证据不足的图结果不应靠结构字段直接放行。
        if bool(md.get("evidence_insufficient", False)):
            return False

        if not has_structured:
            return False

        law_in_query = bool(law_name) and (law_name in query)
        article_in_query = bool(article_id) and (article_id in query)
        if has_legal_signal and (law_in_query or article_in_query):
            return True

        # 无显式对齐时，至少要求接近阈值，避免低质量结构化结果被放过。
        return self._safe_float(md.get("relevance_score", 0.0)) >= (min_relevance * 0.9)

    def _apply_graph_quality_gate(
        self,
        documents: List[Document],
        strategy: SearchStrategy,
        query: str,
        top_k: int,
    ) -> List[Document]:
        if not documents:
            return []
        if strategy not in {SearchStrategy.GRAPH_RAG, SearchStrategy.COMBINED}:
            return documents[:top_k]
        if not bool(getattr(self.config, "graph_quality_gate_enabled", True)):
            return documents[:top_k]

        max_low_keep = max(0, int(getattr(self.config, "graph_low_quality_max_keep", 1)))
        penalty = self._safe_float(getattr(self.config, "graph_low_quality_penalty", 0.35))
        penalty = max(0.0, min(1.0, penalty))
        has_legal_signal = self._has_legal_query_signal(query)

        filtered: List[Document] = []
        low_kept = 0
        for doc in documents:
            if not self._is_graph_candidate(doc):
                filtered.append(doc)
                continue

            md = doc.metadata or {}
            if self._is_graph_high_quality(doc, query, has_legal_signal):
                md["graph_quality_gate"] = "pass"
                doc.metadata = md
                filtered.append(doc)
                continue

            if low_kept < max_low_keep:
                low_kept += 1
                md["graph_quality_gate"] = "low_kept"
                md["graph_quality_penalty"] = penalty
                for key in ("relevance_score", "final_score", "score", "rerank_score"):
                    if key in md:
                        md[key] = round(self._safe_float(md.get(key, 0.0)) * penalty, 6)
                doc.metadata = md
                filtered.append(doc)
                continue

            md["graph_quality_gate"] = "dropped"
            doc.metadata = md
        filtered.sort(key=self._doc_pre_rank_score, reverse=True)
        return filtered[:top_k]

    def _doc_merge_key(self, doc: Document) -> str:
        md = doc.metadata or {}
        chunk_id = str(md.get("chunk_id", "") or "").strip()
        if chunk_id:
            return f"chunk::{chunk_id}"
        node_id = str(md.get("node_id", "") or "").strip()
        if node_id:
            return f"node::{node_id}"
        return f"text::{hash((doc.page_content or '')[:200])}"

    def _doc_pre_rank_score(self, doc: Document) -> float:
        md = doc.metadata or {}
        for key in ("final_score", "rerank_score", "relevance_score", "score", "score_vector", "score_bm25"):
            if key in md:
                return self._safe_float(md.get(key, 0.0))
        return 0.0

    def _assist_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 500):
        if self.llm_dispatcher is not None:
            response, provider, model = self.llm_dispatcher.create_chat_completion(
                role="assist",
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            logger.info("辅助调用通道(路由): provider=%s model=%s", provider, model)
            return response
        return self.llm_client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )

    def analyze_query(self, query: str) -> QueryAnalysis:
        query = sanitize_query_text(query)
        if not query:
            return self._rule_based_analysis("")

        prompt = f"""
        你是法律RAG路由分析器。请评估以下查询并返回JSON。

        查询: {query}

        评估维度:
        1) query_complexity 0-1:
           - 0.0-0.3: 简单法条定位（如“劳动合同法第39条是什么”）
           - 0.4-0.7: 中等复杂（如“试用期辞退需要满足什么条件”）
           - 0.8-1.0: 复杂推理（如“未签合同+违法辞退会触发哪些责任链条”）
        2) relationship_intensity 0-1:
           - 是否涉及引用链、多法规关联、程序链条
        3) reasoning_required: 是否需要多跳解释
        4) entity_count: 识别到的法规/条文/场景实体数量
        5) recommended_strategy:
           - hybrid_traditional / graph_rag / combined

        返回:
        {{
          "query_complexity": 0.6,
          "relationship_intensity": 0.7,
          "reasoning_required": true,
          "entity_count": 2,
          "recommended_strategy": "graph_rag",
          "confidence": 0.82,
          "reasoning": "涉及条文关联和责任链"
        }}
        """
        try:
            response = self._assist_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            data = self._safe_json_loads(response.choices[0].message.content.strip())
            return QueryAnalysis(
                query_complexity=float(data.get("query_complexity", 0.5)),
                relationship_intensity=float(data.get("relationship_intensity", 0.5)),
                reasoning_required=bool(data.get("reasoning_required", False)),
                entity_count=int(data.get("entity_count", 1)),
                recommended_strategy=SearchStrategy(data.get("recommended_strategy", "hybrid_traditional")),
                confidence=float(data.get("confidence", 0.6)),
                reasoning=str(data.get("reasoning", "LLM分析")),
            )
        except Exception as e:
            logger.error("路由分析失败，使用规则降级: %s", e)
            return self._rule_based_analysis(query)

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _rule_based_analysis(self, query: str) -> QueryAnalysis:
        query = sanitize_query_text(query)

        complexity_keywords = ["是否", "适用", "依据", "责任", "后果", "引用", "关联", "区别"]
        relation_keywords = ["根据", "参照", "同时违反", "连带", "程序", "条件", "路径", "链条"]

        query_complexity = min(
            sum(1 for kw in complexity_keywords if kw in query) / len(complexity_keywords),
            1.0,
        )
        relationship_intensity = min(
            sum(1 for kw in relation_keywords if kw in query) / len(relation_keywords),
            1.0,
        )
        reasoning_required = query_complexity > 0.35 or relationship_intensity > 0.35

        if query_complexity > 0.65 and relationship_intensity > 0.45:
            strategy = SearchStrategy.COMBINED
        elif reasoning_required:
            strategy = SearchStrategy.GRAPH_RAG
        else:
            strategy = SearchStrategy.HYBRID_TRADITIONAL

        return QueryAnalysis(
            query_complexity=query_complexity,
            relationship_intensity=relationship_intensity,
            reasoning_required=reasoning_required,
            entity_count=max(1, len(query.split())),
            recommended_strategy=strategy,
            confidence=0.65,
            reasoning="规则降级分析",
        )

    def format_routing_explanation(self, query: str, analysis: QueryAnalysis) -> str:
        query = sanitize_query_text(query)
        return f"""
查询路由分析报告

查询：{query}
复杂度：{analysis.query_complexity:.2f}
关系密集度：{analysis.relationship_intensity:.2f}
推理需求：{'是' if analysis.reasoning_required else '否'}
实体数量：{analysis.entity_count}
推荐策略：{analysis.recommended_strategy.value}
置信度：{analysis.confidence:.2f}
理由：{analysis.reasoning}
""".strip()

    def route_query(
        self,
        query: str,
        top_k: int = 5,
        analysis: Optional[QueryAnalysis] = None,
        retrieval_scope: Optional[Dict[str, Any]] = None,
        apply_rerank: bool = False,
        force_rule_intent: bool = False,
    ) -> Tuple[List[Document], QueryAnalysis]:
        query = sanitize_query_text(query)
        if not query:
            analysis = self._rule_based_analysis("")
            self._reset_last_route_trace(analysis.recommended_strategy, reason="empty_query")
            return [], analysis

        if analysis is None:
            analysis = self.analyze_query(query)
        self._reset_last_route_trace(analysis.recommended_strategy, reason="")
        self._update_route_stats(analysis.recommended_strategy)

        try:
            if analysis.recommended_strategy == SearchStrategy.HYBRID_TRADITIONAL:
                documents = self.traditional_retrieval.hybrid_search(
                    query,
                    top_k,
                    retrieval_scope=retrieval_scope,
                    apply_rerank=apply_rerank,
                    use_rule_intent=force_rule_intent,
                )
            elif analysis.recommended_strategy == SearchStrategy.GRAPH_RAG:
                documents = self.graph_rag_retrieval.graph_rag_search(query, top_k)
            else:
                documents = self._combined_search(
                    query,
                    top_k,
                    retrieval_scope=retrieval_scope,
                    apply_rerank=apply_rerank,
                    force_rule_intent=force_rule_intent,
                )
            documents = self._apply_graph_quality_gate(documents, analysis.recommended_strategy, query, top_k)

            graph_empty_reason = getattr(self.graph_rag_retrieval, "last_empty_reason", "")
            grounding_stats = getattr(self.graph_rag_retrieval, "last_grounding_stats", {}) or {}
            graph_trace = getattr(self.graph_rag_retrieval, "last_graph_trace", {}) or {}
            if analysis.recommended_strategy in {SearchStrategy.GRAPH_RAG, SearchStrategy.COMBINED}:
                self.route_stats["graph_route_count"] += 1
                if int(graph_trace.get("source_hit_count", 0)) > 0:
                    self.route_stats["graph_grounding_success_count"] += 1
                if graph_empty_reason == "no_grounded_nodes":
                    self.route_stats["graph_empty_no_grounding_count"] += 1
                self.last_route_trace.update(
                    {
                        "graph_empty_reason": str(graph_empty_reason or ""),
                        "graph_query_type": str(graph_trace.get("query_type", "") or ""),
                        "graph_source_candidate_count": self._safe_int(
                            grounding_stats.get("source_candidate_count", 0)
                        ),
                        "graph_source_hit_count": self._safe_int(grounding_stats.get("source_hit_count", 0)),
                        "graph_target_candidate_count": self._safe_int(
                            grounding_stats.get("target_candidate_count", 0)
                        ),
                        "graph_target_hit_count": self._safe_int(grounding_stats.get("target_hit_count", 0)),
                        "graph_result_count": self._safe_int(graph_trace.get("result_count", 0)),
                        "source_grounding_mode": str(grounding_stats.get("source_grounding_mode", "") or ""),
                        "target_grounding_mode": str(grounding_stats.get("target_grounding_mode", "") or ""),
                    }
                )

            # 空结果降级：图检索或组合检索返回空时自动回退传统检索
            if (
                not documents
                and analysis.recommended_strategy in {SearchStrategy.GRAPH_RAG, SearchStrategy.COMBINED}
            ):
                graph_empty_reason = graph_empty_reason or "empty_result"
                source_candidates = int(grounding_stats.get("source_candidate_count", 0))
                source_hits = int(grounding_stats.get("source_hit_count", 0))
                log_func = (
                    logger.info
                    if graph_empty_reason in {"no_grounded_nodes", "path_target_not_grounded", "no_paths_found"}
                    else logger.warning
                )
                log_func(
                    "路由策略 %s 返回空结果，自动降级到传统检索: reason=%s source_candidates=%s source_hits=%s",
                    analysis.recommended_strategy.value,
                    graph_empty_reason,
                    source_candidates,
                    source_hits,
                )
                self.route_stats["graph_fallback_to_traditional_count"] += 1
                self.last_route_trace["graph_fallback_to_traditional"] = True
                documents = self.traditional_retrieval.hybrid_search(
                    query,
                    top_k,
                    retrieval_scope=retrieval_scope,
                    apply_rerank=apply_rerank,
                    use_rule_intent=force_rule_intent,
                )
                for doc in documents:
                    doc.metadata["route_fallback"] = "empty_result_to_traditional"
                    doc.metadata["graph_empty_reason"] = graph_empty_reason
                    doc.metadata["graph_grounding_candidates"] = grounding_stats.get("source_candidates", [])
                    doc.metadata["graph_grounding_hit_count"] = source_hits
                    doc.metadata["graph_grounding_candidate_count"] = source_candidates
                    doc.metadata["graph_grounding_target_candidate_count"] = int(
                        grounding_stats.get("target_candidate_count", 0)
                    )
                    doc.metadata["graph_grounding_target_hit_count"] = int(grounding_stats.get("target_hit_count", 0))

            self.last_route_trace["final_document_count"] = len(documents or [])
            return self._post_process_results(documents, analysis), analysis
        except Exception as e:
            logger.error("查询路由失败，降级到传统检索: %s", e)
            fallback_docs = self.traditional_retrieval.hybrid_search(
                query,
                top_k,
                retrieval_scope=retrieval_scope,
                apply_rerank=apply_rerank,
                use_rule_intent=force_rule_intent,
            )
            self.last_route_trace.update(
                {
                    "graph_empty_reason": "route_exception",
                    "graph_fallback_to_traditional": True,
                    "final_document_count": len(fallback_docs or []),
                }
            )
            return fallback_docs, analysis

    def _combined_search(
        self,
        query: str,
        top_k: int,
        retrieval_scope: Optional[Dict[str, Any]] = None,
        apply_rerank: bool = False,
        force_rule_intent: bool = False,
    ) -> List[Document]:
        query = sanitize_query_text(query)
        if not query:
            return []

        traditional_docs = self.traditional_retrieval.hybrid_search(
            query,
            top_k,
            retrieval_scope=retrieval_scope,
            apply_rerank=apply_rerank,
            use_rule_intent=force_rule_intent,
        )
        graph_docs = self.graph_rag_retrieval.graph_rag_search(query, top_k)

        candidate_map: Dict[str, Document] = {}
        for source, docs in (("traditional", traditional_docs), ("graph_rag", graph_docs)):
            for doc in docs:
                if doc.metadata is None:
                    doc.metadata = {}
                doc.metadata["search_source"] = source
                key = self._doc_merge_key(doc)
                existing = candidate_map.get(key)
                if existing is None:
                    candidate_map[key] = doc
                    continue
                if self._doc_pre_rank_score(doc) > self._doc_pre_rank_score(existing):
                    candidate_map[key] = doc

        combined = list(candidate_map.values())
        combined.sort(key=self._doc_pre_rank_score, reverse=True)
        return combined[:top_k]

    def _post_process_results(self, documents: List[Document], analysis: QueryAnalysis) -> List[Document]:
        for doc in documents:
            doc.metadata.update(
                {
                    "route_strategy": analysis.recommended_strategy.value,
                    "query_complexity": analysis.query_complexity,
                    "route_confidence": analysis.confidence,
                }
            )
        return documents

    def _update_route_stats(self, strategy: SearchStrategy):
        self.route_stats["total_queries"] += 1
        if strategy == SearchStrategy.HYBRID_TRADITIONAL:
            self.route_stats["traditional_count"] += 1
        elif strategy == SearchStrategy.GRAPH_RAG:
            self.route_stats["graph_rag_count"] += 1
        elif strategy == SearchStrategy.COMBINED:
            self.route_stats["combined_count"] += 1

    def get_route_statistics(self) -> Dict[str, Any]:
        total = self.route_stats["total_queries"]
        if total == 0:
            return self.route_stats
        graph_total = max(1, int(self.route_stats.get("graph_route_count", 0)))
        return {
            **self.route_stats,
            "traditional_ratio": self.route_stats["traditional_count"] / total,
            "graph_rag_ratio": self.route_stats["graph_rag_count"] / total,
            "combined_ratio": self.route_stats["combined_count"] / total,
            "graph_grounding_success_ratio": self.route_stats["graph_grounding_success_count"] / graph_total,
            "graph_empty_no_grounding_ratio": self.route_stats["graph_empty_no_grounding_count"] / graph_total,
            "graph_fallback_to_traditional_ratio": self.route_stats["graph_fallback_to_traditional_count"] / graph_total,
        }

    def explain_routing_decision(self, query: str) -> str:
        query = sanitize_query_text(query)
        analysis = self.analyze_query(query)
        return self.format_routing_explanation(query, analysis)
