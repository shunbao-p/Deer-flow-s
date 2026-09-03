# =============================================================
# 文件介绍：图 RAG 检索模块（GraphRAGRetrieval）
# 目标：法律场景多跳检索、关系链解释与路径推理。
# =============================================================
"""
法律图RAG检索模块
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.documents import Document
from neo4j import GraphDatabase
from .text_safety import sanitize_query_text

logger = logging.getLogger(__name__)


class QueryType(Enum):
    ENTITY_RELATION = "entity_relation"
    MULTI_HOP = "multi_hop"
    SUBGRAPH = "subgraph"
    PATH_FINDING = "path_finding"
    CLUSTERING = "clustering"


@dataclass
class GraphQuery:
    query_type: QueryType
    source_entities: List[str]
    target_entities: List[str]
    relation_types: List[str]
    source_node_ids: List[str] = field(default_factory=list)
    target_node_ids: List[str] = field(default_factory=list)
    max_depth: int = 2
    max_nodes: int = 50
    constraints: Dict[str, Any] = field(default_factory=dict)
    grounding_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    path_length: int
    relevance_score: float
    path_type: str


@dataclass
class KnowledgeSubgraph:
    central_nodes: List[Dict[str, Any]]
    connected_nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    graph_metrics: Dict[str, float]
    reasoning_chains: List[str]


class GraphRAGRetrieval:
    """法律图RAG检索系统。"""

    GENERIC_LABEL_TOKENS = {
        "lawdocument",
        "article",
        "legaldomain",
        "riskscenario",
        "compliancestep",
        "law",
        "domain",
        "risk",
        "label",
        "法律领域",
        "法规",
        "法条",
        "条文",
        "领域",
        "风险场景",
        "合规步骤",
        "法律概念",
        "实体",
    }

    ENTITY_ALIAS_MAP = {
        "孩童": "未成年人",
        "未成年": "未成年人",
        "欠薪": "拖欠工资",
        "拖薪": "拖欠工资",
        "恶意伤人": "故意伤害",
    }

    LEGAL_NAME_SUFFIXES = ("法", "法典", "条例", "规定", "办法", "解释", "罪")
    ENTITY_BEHAVIOR_TERMS = {
        "正当防卫",
        "紧急避险",
        "故意伤害",
        "未成年人",
        "诈骗",
        "诈骗罪",
        "盗窃",
        "盗窃罪",
        "非法经营罪",
        "帮助信息网络犯罪活动罪",
        "侵权",
        "拖欠工资",
        "辞退",
        "工伤",
        "违约",
        "取保候审",
        "劳动争议",
        "劳动仲裁",
    }
    LAW_CORE_TERMS = {
        "刑法",
        "民法典",
        "劳动法",
        "劳动合同法",
        "个人信息保护法",
        "数据安全法",
        "网络安全法",
        "行政处罚法",
        "刑事诉讼法",
        "民事诉讼法",
    }
    LAW_ALIAS_MAP = {
        "中华人民共和国刑法": "刑法",
        "中华人民共和国民法典": "民法典",
        "中华人民共和国劳动合同法": "劳动合同法",
        "中华人民共和国未成年人保护法": "未成年人保护法",
        "中华人民共和国道路交通安全法": "道路交通安全法",
        "中华人民共和国消费者权益保护法": "消费者权益保护法",
        "中华人民共和国个人信息保护法": "个人信息保护法",
        "中华人民共和国数据安全法": "数据安全法",
        "中华人民共和国网络安全法": "网络安全法",
        "中华人民共和国行政处罚法": "行政处罚法",
        "中华人民共和国刑事诉讼法": "刑事诉讼法",
        "中华人民共和国民事诉讼法": "民事诉讼法",
    }
    ZH_DIGIT = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    ZH_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}

    def __init__(self, config, llm_client, llm_dispatcher: Optional[object] = None):
        self.config = config
        self.llm_client = llm_client
        self.llm_dispatcher = llm_dispatcher
        self.driver = None
        self.entity_cache: Dict[str, Dict[str, Any]] = {}
        self.relation_cache: Dict[str, int] = {}
        self.last_empty_reason = ""
        self.last_grounding_stats: Dict[str, Any] = {}
        self.last_graph_trace: Dict[str, Any] = {}

    def _assist_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 800):
        if self.llm_dispatcher is not None:
            response, provider, model = self.llm_dispatcher.create_chat_completion(
                role="assist",
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            logger.info("辅助调用通道(图理解): provider=%s model=%s", provider, model)
            return response
        return self.llm_client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )

    def initialize(self):
        logger.info("初始化法律图RAG检索系统...")
        try:
            self.driver = GraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_user, self.config.neo4j_password),
            )
            with self.driver.session(database=self.config.neo4j_database) as session:
                session.run("RETURN 1")
            self._build_graph_index()
            logger.info("法律图RAG检索系统初始化完成")
        except Exception as e:
            logger.error("初始化图RAG检索系统失败: %s", e)

    def _build_graph_index(self):
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                entity_query = """
                MATCH (n)
                WHERE n:LawDocument OR n:Article OR n:RiskScenario OR n:ComplianceStep
                WITH n, COUNT { (n)--() } AS degree
                RETURN
                    COALESCE(toString(n.nodeId), elementId(n)) AS node_id,
                    labels(n) AS labels,
                    COALESCE(n.name, n.title, n.articleId, '') AS name,
                    COALESCE(n.category, '') AS category,
                    degree
                ORDER BY degree DESC
                LIMIT 2000
                """
                for record in session.run(entity_query):
                    self.entity_cache[record["node_id"]] = {
                        "labels": record["labels"],
                        "name": record["name"],
                        "category": record["category"],
                        "degree": record["degree"],
                    }

                relation_query = """
                MATCH ()-[r]->()
                RETURN type(r) AS rel_type, count(r) AS frequency
                ORDER BY frequency DESC
                """
                for record in session.run(relation_query):
                    self.relation_cache[record["rel_type"]] = record["frequency"]
        except Exception as e:
            logger.error("构建图索引失败: %s", e)

    def understand_graph_query(self, query: str) -> GraphQuery:
        query = sanitize_query_text(query)
        if not query:
            return self._rule_based_query("")

        prompt = f"""
        你是法律图谱查询规划器。请将问题映射到图查询参数。

        可用实体: LawDocument, Article, LegalDomain, RiskScenario, ComplianceStep
        可用关系: HAS_ARTICLE, BELONGS_TO_DOMAIN, CITES, RELATES_TO, APPLIES_TO, REQUIRES_STEP, PRECEDES

        问题: {query}

        返回JSON:
        {{
          "query_type": "multi_hop|entity_relation|subgraph|path_finding|clustering",
          "source_entities": ["实体1"],
          "target_entities": ["实体2"],
          "relation_types": ["CITES", "RELATES_TO"],
          "max_depth": 2,
          "constraints": {{}}
        }}
        """
        try:
            response = self._assist_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            data = self._safe_json_loads(response.choices[0].message.content.strip())
            return GraphQuery(
                query_type=QueryType(data.get("query_type", "multi_hop")),
                source_entities=data.get("source_entities", []),
                target_entities=data.get("target_entities", []),
                relation_types=data.get("relation_types", []) or getattr(self.config, "graph_relation_types", []),
                source_node_ids=[],
                target_node_ids=[],
                max_depth=max(1, min(int(data.get("max_depth", 2)), 4)),
                max_nodes=50,
                constraints=data.get("constraints", {}),
                grounding_meta={},
            )
        except Exception as e:
            logger.error("查询意图理解失败，使用规则降级: %s", e)
            return self._rule_based_query(query)

    def _rule_based_query(self, query: str) -> GraphQuery:
        query = sanitize_query_text(query)
        relation_types = getattr(self.config, "graph_relation_types", [])
        if any(x in query for x in ["路径", "链路", "从", "到"]):
            qtype = QueryType.PATH_FINDING
        elif any(x in query for x in ["关联", "引用", "关系"]):
            qtype = QueryType.ENTITY_RELATION
        elif any(x in query for x in ["涉及", "依据", "责任", "如何"]):
            qtype = QueryType.MULTI_HOP
        else:
            qtype = QueryType.SUBGRAPH
        return GraphQuery(
            query_type=qtype,
            source_entities=[query[:24]],
            target_entities=[],
            relation_types=relation_types,
            source_node_ids=[],
            target_node_ids=[],
            max_depth=min(getattr(self.config, "max_graph_depth", 2), 4),
            constraints={},
            grounding_meta={},
        )

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _normalize_entity_term(self, term: str) -> str:
        term = sanitize_query_text(term)
        term = term.strip().strip("“”\"'[]()（）")
        if term.startswith("《") and term.endswith("》") and len(term) > 2:
            term = term[1:-1].strip()
        return term

    def _get_graph_entity_max_len(self, strict_whitelist: bool = True) -> int:
        try:
            strict_limit = max(8, int(getattr(self.config, "graph_entity_max_len", 20)))
            if strict_whitelist:
                return strict_limit
            relaxed_limit = int(getattr(self.config, "graph_entity_max_len_relaxed", 32))
            return max(strict_limit, max(8, relaxed_limit))
        except Exception:
            return 20

    def _is_article_ref(self, term: str) -> bool:
        return bool(re.fullmatch(r"第[0-9一二三四五六七八九十百千万〇零两]+条", term))

    def _is_law_like_term(self, term: str) -> bool:
        if any(term.endswith(suffix) for suffix in self.LEGAL_NAME_SUFFIXES):
            return True
        if term in self.LAW_CORE_TERMS:
            return True
        return False

    def _is_whitelisted_entity_term(self, term: str) -> bool:
        if self._is_article_ref(term):
            return True
        if self._is_law_like_term(term):
            return True
        if re.fullmatch(r"[一-龥]{2,30}罪", term):
            return True
        if term in self.LAW_CORE_TERMS:
            return True
        if term in self.ENTITY_BEHAVIOR_TERMS:
            return True
        if term in self.ENTITY_ALIAS_MAP or term in self.ENTITY_ALIAS_MAP.values():
            return True
        return False

    def _is_valid_entity_term(self, term: str, strict_whitelist: bool = True) -> bool:
        normalized = self._normalize_entity_term(term)
        if not normalized:
            return False
        if self._is_generic_label_token(normalized):
            return False
        if len(normalized) > self._get_graph_entity_max_len(strict_whitelist=strict_whitelist):
            return False
        if strict_whitelist:
            if not self._is_whitelisted_entity_term(normalized):
                return False
            return True

        if self._is_whitelisted_entity_term(normalized):
            return True
        min_len = max(2, int(getattr(self.config, "graph_relaxed_min_term_len", 2)))
        if len(normalized) < min_len:
            return False
        if re.fullmatch(r"[0-9]+", normalized):
            return False
        return True

    def _is_generic_label_token(self, token: str) -> bool:
        normalized = self._normalize_entity_term(token)
        if not normalized:
            return True
        compact = normalized.replace("_", "").replace("-", "").replace(" ", "").lower()
        return compact in self.GENERIC_LABEL_TOKENS

    def _fallback_extract_entity_terms(self, query: str) -> List[str]:
        query = sanitize_query_text(query)
        if not query:
            return []

        terms: List[str] = []
        law_refs = re.findall(r"《([^》]{2,40})》", query)
        for law in law_refs:
            terms.append(law.strip())

        for law in self.LAW_CORE_TERMS:
            if law in query:
                terms.append(law)

        article_refs = re.findall(r"第[0-9一二三四五六七八九十百千万〇零两]+条", query)
        terms.extend(article_refs)
        terms.extend(re.findall(r"[一-龥]{2,30}罪", query))

        for behavior in self.ENTITY_BEHAVIOR_TERMS:
            if behavior in query:
                terms.append(behavior)

        for alias, canonical in self.ENTITY_ALIAS_MAP.items():
            if alias in query:
                terms.append(canonical)

        if not terms:
            cleaned = query
            for pat in [
                "请问",
                "对于",
                "关于",
                "如何",
                "怎么",
                "怎样",
                "是否",
                "能否",
                "可以",
                "怎么办",
                "依据",
                "根据",
                "认定",
                "处理",
                "量刑",
                "规定",
                "条件",
                "程序",
                "吗",
                "呢",
                "的",
            ]:
                cleaned = cleaned.replace(pat, " ")
            chunks = [x.strip() for x in re.split(r"[^一-龥0-9A-Za-z]+", cleaned) if x.strip()]
            terms.extend([x for x in chunks if 2 <= len(x) <= 12][:2])
        deduped: List[str] = []
        seen = set()
        for term in terms:
            normalized = self._normalize_entity_term(term)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _extract_target_hint_terms(self, query: str) -> List[str]:
        query = sanitize_query_text(query)
        hints: List[str] = []
        hints.extend(re.findall(r"《([^》]{2,40})》", query))
        hints.extend(re.findall(r"第[0-9一二三四五六七八九十百千万〇零两]+条", query))

        for term in ["刑法", "民法典", "劳动合同法", "个人信息保护法", "正当防卫", "故意伤害", "未成年人"]:
            if term in query:
                hints.append(term)
        return [self._normalize_entity_term(x) for x in hints if x]

    def _has_legal_query_signal(self, query: str, terms: Optional[List[str]] = None) -> bool:
        query = sanitize_query_text(query)
        if not query:
            return False
        if re.search(r"《[^》]{2,40}》", query):
            return True
        if re.search(r"第[0-9一二三四五六七八九十百千万〇零两]+条", query):
            return True
        if any(term in query for term in self.LAW_CORE_TERMS):
            return True
        for term in terms or []:
            normalized = self._normalize_entity_term(term)
            if self._is_article_ref(normalized) or self._is_law_like_term(normalized):
                return True
        return False

    def _should_use_contains_fallback(self, query: str, terms: List[str]) -> bool:
        if not bool(getattr(self.config, "graph_grounding_contains_enabled", False)):
            return False
        require_signal = bool(getattr(self.config, "graph_grounding_contains_require_legal_signal", True))
        if not require_signal:
            return True
        return self._has_legal_query_signal(query, terms=terms)

    def _lookup_grounded_nodes(self, terms: List[str], query: str = "", per_term_limit: int = 3) -> List[Dict[str, Any]]:
        if not self.driver or not terms:
            return []

        merged_hits: Dict[str, Dict[str, Any]] = {}
        index_name = getattr(self.config, "neo4j_legal_fulltext_index", "legal_fulltext_idx")

        exact_query = """
        UNWIND $terms AS term
        MATCH (n)
        WHERE (n:LawDocument OR n:Article OR n:LegalDomain OR n:RiskScenario OR n:ComplianceStep)
          AND (
                COALESCE(n.name, n.title, n.articleId, '') = term
             OR COALESCE(n.articleId, '') = term
          )
        RETURN term,
               COALESCE(toString(n.nodeId), elementId(n)) AS node_id,
               COALESCE(n.name, n.title, n.articleId, '') AS name,
               2.0 AS score
        LIMIT 300
        """

        fulltext_query = """
        UNWIND $terms AS term
        CALL db.index.fulltext.queryNodes($index_name, term) YIELD node, score
        RETURN term,
               COALESCE(toString(node.nodeId), elementId(node)) AS node_id,
               COALESCE(node.name, node.title, node.articleId, '') AS name,
               score
        LIMIT 800
        """
        contains_query = """
        UNWIND $terms AS term
        MATCH (n)
        WHERE (n:LawDocument OR n:Article OR n:LegalDomain OR n:RiskScenario OR n:ComplianceStep)
          AND size(term) >= 2
          AND COALESCE(n.name, n.title, n.articleId, '') CONTAINS term
        RETURN term,
               COALESCE(toString(n.nodeId), elementId(n)) AS node_id,
               COALESCE(n.name, n.title, n.articleId, '') AS name,
               0.6 AS score
        LIMIT 600
        """

        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(exact_query, {"terms": terms}):
                    key = f"{record['term']}::{record['node_id']}"
                    merged_hits[key] = {
                        "term": record["term"],
                        "node_id": record["node_id"],
                        "name": record["name"],
                        "score": float(record["score"]),
                    }
        except Exception as e:
            logger.warning("实体精确匹配失败: %s", e)

        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(
                    fulltext_query,
                    {"terms": terms, "index_name": index_name},
                ):
                    score = float(record["score"])
                    if score <= 0:
                        continue
                    key = f"{record['term']}::{record['node_id']}"
                    existing = merged_hits.get(key)
                    if existing is None or score > existing["score"]:
                        merged_hits[key] = {
                            "term": record["term"],
                            "node_id": record["node_id"],
                            "name": record["name"],
                            "score": score,
                        }
        except Exception as e:
            logger.warning("实体fulltext匹配失败（可能索引不存在）: %s", e)

        # 在开关开启且命中法律信号时，才执行 CONTAINS 兜底（默认保守关闭）。
        if (not merged_hits) and self._should_use_contains_fallback(query, terms):
            try:
                with self.driver.session(database=self.config.neo4j_database) as session:
                    for record in session.run(contains_query, {"terms": terms}):
                        key = f"{record['term']}::{record['node_id']}"
                        score = float(record["score"])
                        if score <= 0:
                            continue
                        existing = merged_hits.get(key)
                        if existing is None or score > existing["score"]:
                            merged_hits[key] = {
                                "term": record["term"],
                                "node_id": record["node_id"],
                                "name": record["name"],
                                "score": score,
                            }
            except Exception as e:
                logger.warning("实体CONTAINS兜底匹配失败: %s", e)

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in merged_hits.values():
            grouped.setdefault(item["term"], []).append(item)

        final_hits: List[Dict[str, Any]] = []
        for term, term_hits in grouped.items():
            ranked = sorted(term_hits, key=lambda x: x["score"], reverse=True)[:per_term_limit]
            for hit in ranked:
                final_hits.append(hit)
        return final_hits

    def _ground_entities(
        self,
        query: str,
        raw_entities: List[str],
        allow_query_fallback: bool = True,
        strict_whitelist: bool = True,
    ) -> Dict[str, Any]:
        terms: List[str] = []
        for term in raw_entities or []:
            normalized = self._normalize_entity_term(term)
            if not normalized:
                continue
            if not self._is_valid_entity_term(normalized, strict_whitelist=strict_whitelist):
                continue
            terms.append(normalized)
            alias = self.ENTITY_ALIAS_MAP.get(normalized)
            if alias and self._is_valid_entity_term(alias, strict_whitelist=strict_whitelist):
                terms.append(alias)

        if not terms and allow_query_fallback:
            fallback_terms = self._fallback_extract_entity_terms(query)
            terms = [
                term
                for term in fallback_terms
                if self._is_valid_entity_term(term, strict_whitelist=strict_whitelist)
            ]

        dedup_terms: List[str] = []
        seen_terms = set()
        for term in terms:
            normalized = self._normalize_entity_term(term)
            if not normalized:
                continue
            if not self._is_valid_entity_term(normalized, strict_whitelist=strict_whitelist):
                continue
            if normalized in seen_terms:
                continue
            seen_terms.add(normalized)
            dedup_terms.append(normalized)

        hits = self._lookup_grounded_nodes(dedup_terms, query=query, per_term_limit=3)
        source_node_ids: List[str] = []
        source_entities: List[str] = []
        seen_ids = set()
        seen_names = set()
        for hit in sorted(hits, key=lambda x: x["score"], reverse=True):
            node_id = hit["node_id"]
            name = hit["name"]
            if node_id and node_id not in seen_ids:
                seen_ids.add(node_id)
                source_node_ids.append(node_id)
            if name and name not in seen_names:
                seen_names.add(name)
                source_entities.append(name)

        return {
            "candidate_terms": dedup_terms,
            "hits": hits,
            "source_node_ids": source_node_ids,
            "source_entities": source_entities,
            "grounding_mode": "strict" if strict_whitelist else "relaxed",
        }

    def _apply_entity_grounding(self, graph_query: GraphQuery, query: str) -> GraphQuery:
        source_ground = self._ground_entities(
            query,
            graph_query.source_entities,
            allow_query_fallback=True,
            strict_whitelist=True,
        )
        source_mode = "strict"
        relax_enabled = bool(getattr(self.config, "graph_grounding_relax_enabled", True))
        if relax_enabled and not source_ground["source_node_ids"]:
            relaxed_source_ground = self._ground_entities(
                query,
                graph_query.source_entities,
                allow_query_fallback=True,
                strict_whitelist=False,
            )
            if relaxed_source_ground["candidate_terms"]:
                source_ground = relaxed_source_ground
                source_mode = "relaxed"

        target_seed = graph_query.target_entities
        if graph_query.query_type == QueryType.PATH_FINDING and not target_seed:
            target_seed = self._extract_target_hint_terms(query)

        if target_seed:
            target_ground = self._ground_entities(
                query,
                target_seed,
                allow_query_fallback=(graph_query.query_type == QueryType.PATH_FINDING),
                strict_whitelist=True,
            )
            target_mode = "strict"
            if relax_enabled and not target_ground["source_node_ids"]:
                relaxed_target_ground = self._ground_entities(
                    query,
                    target_seed,
                    allow_query_fallback=(graph_query.query_type == QueryType.PATH_FINDING),
                    strict_whitelist=False,
                )
                if relaxed_target_ground["candidate_terms"]:
                    target_ground = relaxed_target_ground
                    target_mode = "relaxed"
        else:
            target_ground = {
                "candidate_terms": [],
                "hits": [],
                "source_node_ids": [],
                "source_entities": [],
                "grounding_mode": "none",
            }
            target_mode = "none"

        graph_query.source_node_ids = source_ground["source_node_ids"]
        graph_query.target_node_ids = target_ground["source_node_ids"]
        # 收紧闭环：仅允许“已落地命中”的实体名进入后续图检索，
        # 禁止将未命中候选词直接回填到 source/target 查询条件。
        graph_query.source_entities = source_ground["source_entities"]
        graph_query.target_entities = target_ground["source_entities"]
        graph_query.grounding_meta = {
            "source_candidates": source_ground["candidate_terms"],
            "source_candidate_count": len(source_ground["candidate_terms"]),
            "source_hit_count": len(source_ground["source_node_ids"]),
            "target_candidates": target_ground["candidate_terms"],
            "target_candidate_count": len(target_ground["candidate_terms"]),
            "target_hit_count": len(target_ground["source_node_ids"]),
            "source_grounding_mode": source_mode,
            "target_grounding_mode": target_mode,
            "relax_enabled": relax_enabled,
        }
        return graph_query

    def multi_hop_traversal(self, graph_query: GraphQuery) -> List[GraphPath]:
        logger.info(
            "执行多跳遍历: source_entities=%s source_node_ids=%s",
            graph_query.source_entities,
            graph_query.source_node_ids,
        )
        paths: List[GraphPath] = []
        if not self.driver:
            return paths

        if graph_query.query_type == QueryType.ENTITY_RELATION:
            return self._find_entity_relations(graph_query)
        if graph_query.query_type == QueryType.PATH_FINDING:
            return self._find_shortest_paths(graph_query)

        max_depth = max(1, min(int(graph_query.max_depth), 4))
        relation_filter = ""
        params: Dict[str, Any] = {}
        if graph_query.relation_types:
            relation_filter = "AND ALL(rel IN relationships(path) WHERE type(rel) IN $relation_types)"
            params["relation_types"] = graph_query.relation_types

        source_match = ""
        if graph_query.source_node_ids:
            source_match = """
            UNWIND $source_node_ids AS source_id
            MATCH (source)
            WHERE COALESCE(toString(source.nodeId), elementId(source)) = source_id
            """
            params["source_node_ids"] = graph_query.source_node_ids
        else:
            source_match = """
            UNWIND $source_entities AS source_name
            MATCH (source)
            WHERE COALESCE(source.name, source.title, source.articleId, '') CONTAINS source_name
            """
            params["source_entities"] = graph_query.source_entities

        target_filter = ""
        if graph_query.target_node_ids:
            target_filter = """
            AND COALESCE(toString(target.nodeId), elementId(target)) IN $target_node_ids
            """
            params["target_node_ids"] = graph_query.target_node_ids
        elif graph_query.target_entities:
            target_filter = """
            AND ANY(kw IN $target_entities WHERE
                COALESCE(target.name, target.title, target.articleId, '') CONTAINS kw
            )
            """
            params["target_entities"] = graph_query.target_entities

        query = f"""
        {source_match}
        MATCH path = (source)-[*1..{max_depth}]-(target)
        WHERE source <> target
          {relation_filter}
          {target_filter}
        WITH path, length(path) AS path_len
        RETURN path, path_len, relationships(path) AS rels, nodes(path) AS path_nodes,
               (1.0 / toFloat(path_len)) AS relevance
        ORDER BY relevance DESC
        LIMIT 25
        """

        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(query, params):
                    parsed = self._parse_neo4j_path(record, path_type="multi_hop")
                    if parsed:
                        paths.append(parsed)
        except Exception as e:
            logger.error("多跳遍历失败: %s", e)
        return paths

    def _find_entity_relations(self, graph_query: GraphQuery) -> List[GraphPath]:
        """补齐实体关系查询，禁止空占位实现。"""
        paths: List[GraphPath] = []
        relation_filter = ""
        params: Dict[str, Any] = {}
        if graph_query.relation_types:
            relation_filter = "AND type(r) IN $relation_types"
            params["relation_types"] = graph_query.relation_types

        source_match = ""
        if graph_query.source_node_ids:
            source_match = """
            UNWIND $source_node_ids AS source_id
            MATCH (source)
            WHERE COALESCE(toString(source.nodeId), elementId(source)) = source_id
            """
            params["source_node_ids"] = graph_query.source_node_ids
        else:
            source_match = """
            UNWIND $source_entities AS source_name
            MATCH (source)
            WHERE COALESCE(source.name, source.title, source.articleId, '') CONTAINS source_name
            """
            params["source_entities"] = graph_query.source_entities

        query = f"""
        {source_match}
        MATCH (source)-[r]-(target)
        WHERE 1=1
          AND source <> target
          {relation_filter}
        RETURN
          [source, target] AS path_nodes,
          [r] AS rels,
          1 AS path_len,
          0.95 AS relevance
        LIMIT 30
        """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(query, params):
                    parsed = self._parse_neo4j_path(record, path_type="entity_relation")
                    if parsed:
                        paths.append(parsed)
        except Exception as e:
            logger.error("实体关系查询失败: %s", e)
        return paths

    def _find_shortest_paths(self, graph_query: GraphQuery) -> List[GraphPath]:
        """补齐最短路径查询，禁止空占位实现。"""
        paths: List[GraphPath] = []
        if not graph_query.target_entities and not graph_query.target_node_ids:
            logger.warning("PATH_FINDING 缺少目标实体，跳过最短路径查询")
            return []

        max_depth = max(2, min(int(graph_query.max_depth), 4))
        params = {"max_depth": max_depth}
        relation_filter = ""
        relation_types = graph_query.relation_types or getattr(self.config, "graph_relation_types", [])
        if relation_types:
            params["relation_types"] = relation_types
            relation_filter = "AND ALL(rel IN relationships(path) WHERE type(rel) IN $relation_types)"

        if graph_query.source_node_ids and graph_query.target_node_ids:
            params["source_node_ids"] = graph_query.source_node_ids
            params["target_node_ids"] = graph_query.target_node_ids
            query = f"""
            UNWIND $source_node_ids AS source_id
            UNWIND $target_node_ids AS target_id
            MATCH (source), (target)
            WHERE COALESCE(toString(source.nodeId), elementId(source)) = source_id
              AND COALESCE(toString(target.nodeId), elementId(target)) = target_id
              AND source <> target
            MATCH path = shortestPath((source)-[*..{max_depth}]-(target))
            WHERE length(path) <= $max_depth
              {relation_filter}
            RETURN path, length(path) AS path_len, relationships(path) AS rels, nodes(path) AS path_nodes,
                   (1.0 / toFloat(length(path))) AS relevance
            LIMIT 20
            """
        else:
            params["sources"] = graph_query.source_entities
            params["targets"] = graph_query.target_entities
            query = f"""
            UNWIND $sources AS source_kw
            UNWIND $targets AS target_kw
            MATCH (source), (target)
            WHERE COALESCE(source.name, source.title, source.articleId, '') CONTAINS source_kw
              AND COALESCE(target.name, target.title, target.articleId, '') CONTAINS target_kw
              AND source <> target
            MATCH path = shortestPath((source)-[*..{max_depth}]-(target))
            WHERE length(path) <= $max_depth
              {relation_filter}
            RETURN path, length(path) AS path_len, relationships(path) AS rels, nodes(path) AS path_nodes,
                   (1.0 / toFloat(length(path))) AS relevance
            LIMIT 20
            """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                for record in session.run(query, params):
                    parsed = self._parse_neo4j_path(record, path_type="path_finding")
                    if parsed:
                        paths.append(parsed)
        except Exception as e:
            logger.error("最短路径查询失败: %s", e)
        return paths

    def extract_knowledge_subgraph(self, graph_query: GraphQuery) -> KnowledgeSubgraph:
        if not self.driver:
            return self._fallback_subgraph_extraction()
        source_match = ""
        params: Dict[str, Any] = {"max_nodes": graph_query.max_nodes}
        if graph_query.source_node_ids:
            source_match = """
            UNWIND $source_node_ids AS source_id
            MATCH (source)
            WHERE COALESCE(toString(source.nodeId), elementId(source)) = source_id
            """
            params["source_node_ids"] = graph_query.source_node_ids
        else:
            source_match = """
            UNWIND $source_entities AS source_kw
            MATCH (source)
            WHERE COALESCE(source.name, source.title, source.articleId, '') CONTAINS source_kw
            """
            params["source_entities"] = graph_query.source_entities

        query = f"""
        {source_match}
        MATCH (source)-[r*1..{graph_query.max_depth}]-(neighbor)
        WITH source, collect(DISTINCT neighbor) AS neighbors, collect(DISTINCT r) AS rels
        RETURN
          source,
          neighbors[0..$max_nodes] AS nodes,
          rels[0..$max_nodes] AS rel_groups
        LIMIT 1
        """
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                record = session.run(
                    query,
                    params,
                ).single()
            if not record:
                return self._fallback_subgraph_extraction()

            central = [self._serialize_node(record["source"])]
            connected = [self._serialize_node(n) for n in record["nodes"]]

            rels: List[Dict[str, Any]] = []
            for group in record["rel_groups"]:
                for rel in group:
                    rels.append(
                        {
                            "type": self._relationship_type(rel),
                            "properties": dict(rel),
                        }
                    )
            node_count = len(connected)
            rel_count = len(rels)
            density = (
                float(rel_count) / (node_count * (node_count - 1) / 2)
                if node_count > 1
                else 0.0
            )
            return KnowledgeSubgraph(
                central_nodes=central,
                connected_nodes=connected,
                relationships=rels,
                graph_metrics={
                    "node_count": node_count,
                    "relationship_count": rel_count,
                    "density": density,
                },
                reasoning_chains=[],
            )
        except Exception as e:
            logger.error("子图提取失败: %s", e)
            return self._fallback_subgraph_extraction()

    def graph_structure_reasoning(self, subgraph: KnowledgeSubgraph, query: str) -> List[str]:
        if not subgraph.connected_nodes:
            return []
        return [
            f"围绕问题“{query}”共关联 {len(subgraph.connected_nodes)} 个节点。",
            f"关系边数量为 {len(subgraph.relationships)}，图密度 {subgraph.graph_metrics.get('density', 0.0):.3f}。",
        ]

    def graph_rag_search(self, query: str, top_k: int = 5) -> List[Document]:
        query = sanitize_query_text(query)
        self.last_empty_reason = ""
        self.last_grounding_stats = {}
        self.last_graph_trace = {}
        if not query:
            self.last_empty_reason = "empty_query"
            return []

        if not self.driver:
            logger.warning("Neo4j连接未建立，返回空结果")
            self.last_empty_reason = "no_driver"
            return []
        graph_query = self.understand_graph_query(query)
        graph_query = self._apply_entity_grounding(graph_query, query)
        self.last_grounding_stats = graph_query.grounding_meta
        self.last_graph_trace = {
            "query_type": graph_query.query_type.value,
            "reason": "",
            "source_candidate_count": int(graph_query.grounding_meta.get("source_candidate_count", 0)),
            "source_hit_count": int(graph_query.grounding_meta.get("source_hit_count", 0)),
            "target_candidate_count": int(graph_query.grounding_meta.get("target_candidate_count", 0)),
            "target_hit_count": int(graph_query.grounding_meta.get("target_hit_count", 0)),
            "result_count": 0,
        }

        if not graph_query.source_entities and not graph_query.source_node_ids:
            self.last_empty_reason = "no_grounded_nodes"
            self.last_graph_trace["reason"] = self.last_empty_reason
            src_cand = int(graph_query.grounding_meta.get("source_candidate_count", 0))
            src_hit = int(graph_query.grounding_meta.get("source_hit_count", 0))
            tgt_cand = int(graph_query.grounding_meta.get("target_candidate_count", 0))
            tgt_hit = int(graph_query.grounding_meta.get("target_hit_count", 0))
            log_func = logger.info if src_cand == 0 else logger.warning
            log_func(
                "GraphRAG实体未落地，跳过图检索: reason=%s source_candidates=%s source_hits=%s target_candidates=%s target_hits=%s",
                self.last_empty_reason,
                src_cand,
                src_hit,
                tgt_cand,
                tgt_hit,
            )
            return []
        if graph_query.query_type == QueryType.PATH_FINDING and not (
            graph_query.target_entities or graph_query.target_node_ids
        ):
            self.last_empty_reason = "path_target_not_grounded"
            self.last_graph_trace["reason"] = self.last_empty_reason
            tgt_cand = int(graph_query.grounding_meta.get("target_candidate_count", 0))
            log_func = logger.info if tgt_cand == 0 else logger.warning
            log_func(
                "PATH_FINDING目标实体未落地，回退传统检索: reason=%s target_candidates=%s target_hits=%s",
                self.last_empty_reason,
                tgt_cand,
                int(graph_query.grounding_meta.get("target_hit_count", 0)),
            )
            return []

        results: List[Document] = []

        try:
            if graph_query.query_type in {QueryType.MULTI_HOP, QueryType.ENTITY_RELATION, QueryType.PATH_FINDING}:
                paths = self.multi_hop_traversal(graph_query)
                results.extend(self._paths_to_documents(paths))
            else:
                subgraph = self.extract_knowledge_subgraph(graph_query)
                reasoning_chains = self.graph_structure_reasoning(subgraph, query)
                results.extend(self._subgraph_to_documents(subgraph, reasoning_chains))
            if not results:
                self.last_empty_reason = "no_paths_found"
                self.last_graph_trace["reason"] = self.last_empty_reason
                logger.info(
                    "GraphRAG返回空结果: reason=%s query_type=%s source_hits=%s",
                    self.last_empty_reason,
                    graph_query.query_type.value,
                    int(graph_query.grounding_meta.get("source_hit_count", 0)),
                )
            results = sorted(
                results,
                key=lambda x: x.metadata.get("relevance_score", 0.0),
                reverse=True,
            )
            final_results = results[:top_k]
            self.last_graph_trace["result_count"] = len(final_results)
            return final_results
        except Exception as e:
            logger.error("图RAG检索失败: %s", e)
            self.last_empty_reason = "graph_query_exception"
            self.last_graph_trace["reason"] = self.last_empty_reason
            return []

    def _parse_neo4j_path(self, record, path_type: str) -> Optional[GraphPath]:
        try:
            nodes = [self._serialize_node(node) for node in record["path_nodes"]]
            relationships = [
                {"type": self._relationship_type(rel), "properties": dict(rel)}
                for rel in record["rels"]
            ]
            return GraphPath(
                nodes=nodes,
                relationships=relationships,
                path_length=int(record["path_len"]),
                relevance_score=float(record["relevance"]),
                path_type=path_type,
            )
        except Exception as e:
            logger.error("路径解析失败: %s", e)
            return None

    def _serialize_node(self, node) -> Dict[str, Any]:
        return {
            "id": node.get("nodeId", ""),
            "name": node.get("name", node.get("title", node.get("articleId", ""))),
            "labels": list(node.labels),
            "properties": dict(node),
        }

    def _relationship_type(self, rel) -> str:
        rel_type = getattr(rel, "type", None) or getattr(rel, "_type", None)
        if isinstance(rel_type, str) and rel_type:
            return rel_type
        return "RELATED"

    def _normalize_law_name(self, value: Any) -> str:
        raw = self._normalize_entity_term(str(value or ""))
        if not raw:
            return ""
        if raw in self.LAW_ALIAS_MAP:
            return self.LAW_ALIAS_MAP[raw]
        compact = re.sub(r"\s+", "", raw)
        for alias, canonical in self.LAW_ALIAS_MAP.items():
            if re.sub(r"\s+", "", alias) == compact:
                return canonical
        if self._is_law_like_term(raw):
            return raw
        return ""

    def _zh_to_int(self, value: str) -> int:
        text = str(value or "").strip()
        if not text:
            raise ValueError("empty zh number")
        if text.isdigit():
            return int(text)
        total = 0
        section = 0
        number = 0
        for ch in text:
            if ch in self.ZH_DIGIT:
                number = self.ZH_DIGIT[ch]
                continue
            if ch in self.ZH_UNIT:
                unit = self.ZH_UNIT[ch]
                if unit == 10000:
                    section = (section + number) * unit
                    total += section
                    section = 0
                    number = 0
                else:
                    if number == 0:
                        number = 1
                    section += number * unit
                    number = 0
                continue
            raise ValueError(f"unsupported zh number char: {ch}")
        return total + section + number

    def _normalize_article_id(self, value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        compact = raw.replace(" ", "")
        match = re.search(r"第?\s*([0-9零一二三四五六七八九十百千万两〇]+)\s*条", compact)
        token = ""
        if match:
            token = match.group(1)
        else:
            digits = re.findall(r"\d+", compact)
            if digits:
                return f"第{int(digits[0])}条"
            return ""
        try:
            number = self._zh_to_int(token)
        except Exception:
            digits = re.findall(r"\d+", token)
            if not digits:
                return ""
            number = int(digits[0])
        return f"第{number}条"

    def _extract_standard_fields_from_nodes(self, nodes: List[Dict[str, Any]]) -> Dict[str, str]:
        node_infos: List[Dict[str, Any]] = []
        for node in nodes or []:
            properties = node.get("properties", {}) or {}
            labels = set(node.get("labels", []) or [])
            node_name = self._normalize_entity_term(node.get("name", ""))

            law_candidates = [
                properties.get("law_name", ""),
                properties.get("lawName", ""),
                properties.get("name", "") if "LawDocument" in labels else "",
                node_name if "LawDocument" in labels else "",
            ]
            article_candidates = [
                properties.get("article_id", ""),
                properties.get("articleId", ""),
                node_name if self._is_article_ref(node_name) else "",
            ]
            law_hint_candidates = [
                properties.get("belongs_to_law", ""),
                properties.get("belongLaw", ""),
                properties.get("law_name", ""),
                properties.get("lawName", ""),
            ]

            law_name_norm = ""
            article_id_norm = ""
            article_law_hint = ""

            for candidate in law_candidates:
                normalized = self._normalize_law_name(candidate)
                if normalized:
                    law_name_norm = normalized
                    break
            for candidate in article_candidates:
                normalized = self._normalize_article_id(candidate)
                if normalized:
                    article_id_norm = normalized
                    break
            for candidate in law_hint_candidates:
                normalized = self._normalize_law_name(candidate)
                if normalized:
                    article_law_hint = normalized
                    break

            node_infos.append(
                {
                    "labels": labels,
                    "law_name": law_name_norm,
                    "article_id": article_id_norm,
                    "article_law_hint": article_law_hint,
                }
            )

        # 同节点可同时提取法规名与条号时，优先作为高置信标准字段。
        for info in node_infos:
            if info["law_name"] and info["article_id"]:
                return {"law_name_std": info["law_name"], "article_id_std": info["article_id"]}

        # 条文节点自身带法规归属提示时，可安全配对。
        for info in node_infos:
            if info["article_id"] and info["article_law_hint"]:
                return {"law_name_std": info["article_law_hint"], "article_id_std": info["article_id"]}

        # 路径中相邻的 LawDocument + Article 组合，作为次高置信配对。
        for idx, info in enumerate(node_infos):
            if not info["article_id"]:
                continue
            for neighbor_idx in (idx - 1, idx + 1):
                if neighbor_idx < 0 or neighbor_idx >= len(node_infos):
                    continue
                neighbor = node_infos[neighbor_idx]
                if ("LawDocument" in neighbor["labels"]) and neighbor["law_name"]:
                    return {"law_name_std": neighbor["law_name"], "article_id_std": info["article_id"]}

        law_name_fallback = ""
        article_id_fallback = ""
        for info in node_infos:
            if not law_name_fallback and ("LawDocument" in info["labels"]) and info["law_name"]:
                law_name_fallback = info["law_name"]
            if not article_id_fallback and ("Article" in info["labels"]) and info["article_id"]:
                article_id_fallback = info["article_id"]
        if not law_name_fallback:
            for info in node_infos:
                if info["law_name"]:
                    law_name_fallback = info["law_name"]
                    break
        if not article_id_fallback:
            for info in node_infos:
                if info["article_id"]:
                    article_id_fallback = info["article_id"]
                    break

        # 保守策略：无法证明同一法规上下文时，不把法名与条号强行拼对。
        if law_name_fallback and article_id_fallback:
            return {"law_name_std": law_name_fallback, "article_id_std": ""}
        return {"law_name_std": law_name_fallback, "article_id_std": article_id_fallback}

    def _paths_to_documents(self, paths: List[GraphPath]) -> List[Document]:
        docs: List[Document] = []
        for path in paths:
            path_desc = self._build_path_description(path)
            path_relations = [r["type"] for r in path.relationships]
            reasoning_path = " -> ".join([node.get("name", "") for node in path.nodes])
            normalized_fields = self._extract_standard_fields_from_nodes(path.nodes)
            law_name_std = normalized_fields.get("law_name_std", "")
            article_id_std = normalized_fields.get("article_id_std", "")
            primary_node_id = ""
            for node in path.nodes:
                candidate = str(node.get("id", "") or "").strip()
                if candidate:
                    primary_node_id = candidate
                    break
            if not primary_node_id:
                primary_node_id = f"graph_path_{abs(hash(reasoning_path))}"
            docs.append(
                Document(
                    page_content=path_desc,
                    metadata={
                        "node_id": primary_node_id,
                        "search_type": "graph_path",
                        "relevance_score": path.relevance_score,
                        "path_type": path.path_type,
                        "path_length": path.path_length,
                        "path_depth": path.path_length,
                        "path_relations": path_relations,
                        "reasoning_path": reasoning_path,
                        "display_title": path.nodes[0].get("name", "图路径结果") if path.nodes else "图路径结果",
                        "law_name_std": law_name_std,
                        "article_id_std": article_id_std,
                        # 强制回填主字段，保证评测口径直接读取 law_name/article_id 即可。
                        "law_name": law_name_std,
                        "article_id": article_id_std,
                    },
                )
            )
        return docs

    def _subgraph_to_documents(
        self, subgraph: KnowledgeSubgraph, reasoning_chains: List[str]
    ) -> List[Document]:
        center_name = subgraph.central_nodes[0].get("name", "未知中心实体") if subgraph.central_nodes else "未知中心实体"
        normalized_fields = self._extract_standard_fields_from_nodes(
            (subgraph.central_nodes or []) + (subgraph.connected_nodes or [])
        )
        law_name_std = normalized_fields.get("law_name_std", "")
        article_id_std = normalized_fields.get("article_id_std", "")
        center_node_id = str(subgraph.central_nodes[0].get("id", "") or "").strip() if subgraph.central_nodes else ""
        if not center_node_id:
            center_node_id = f"knowledge_subgraph_{abs(hash(center_name))}"
        has_evidence = bool(subgraph.central_nodes and subgraph.connected_nodes and subgraph.relationships)
        relevance = 0.8 if has_evidence else 0.15
        content = (
            f"中心实体: {center_name}\n"
            f"节点数: {len(subgraph.connected_nodes)}\n"
            f"关系数: {len(subgraph.relationships)}\n"
            f"推理说明: {' | '.join(reasoning_chains)}"
        )
        if not has_evidence:
            content += "\n证据状态: 当前子图证据不足，建议回退传统检索或扩展检索范围。"
        return [
            Document(
                page_content=content,
                metadata={
                    "node_id": center_node_id,
                    "search_type": "knowledge_subgraph",
                    "relevance_score": relevance,
                    "reasoning_path": center_name,
                    "path_relations": [r.get("type", "") for r in subgraph.relationships[:8]],
                    "display_title": center_name,
                    "law_name_std": law_name_std,
                    "article_id_std": article_id_std,
                    # 强制回填主字段，避免仅有 *_std 而评测口径读不到。
                    "law_name": law_name_std,
                    "article_id": article_id_std,
                    "evidence_insufficient": not has_evidence,
                },
            )
        ]

    def _build_path_description(self, path: GraphPath) -> str:
        if not path.nodes:
            return "空路径"
        parts: List[str] = []
        for i, node in enumerate(path.nodes):
            parts.append(node.get("name", f"节点{i}"))
            if i < len(path.relationships):
                parts.append(f" --{path.relationships[i].get('type', 'RELATED')}--> ")
        return "".join(parts)

    def _fallback_subgraph_extraction(self) -> KnowledgeSubgraph:
        return KnowledgeSubgraph(
            central_nodes=[],
            connected_nodes=[],
            relationships=[],
            graph_metrics={},
            reasoning_chains=[],
        )

    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("图RAG检索系统已关闭")
