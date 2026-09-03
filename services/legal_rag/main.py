import os
import sys
import time
import logging
import re
from contextlib import nullcontext
from typing import List, Optional, Any, Dict

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from config import DEFAULT_CONFIG, GraphRAGConfig
from rag_modules import (
    GraphDataPreparationModule,
    MilvusIndexConstructionModule, 
    GenerationIntegrationModule,
    MultiLLMDispatcher,
)
from rag_modules.hybrid_retrieval import HybridRetrievalModule
from rag_modules.graph_rag_retrieval import GraphRAGRetrieval
from rag_modules.intelligent_query_router import IntelligentQueryRouter, QueryAnalysis, SearchStrategy
from rag_modules.query_intent_template import rule_based_parse_query_intent
from rag_modules.text_safety import sanitize_query_text, has_surrogates

# 加载环境变量
load_dotenv()


def _env_or_default(name: str, default: Any, caster):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return caster(value)
    except Exception:
        logger.warning("环境变量 %s 值非法，使用默认值: %s", name, default)
        return default


def _to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _langsmith_enabled() -> bool:
    return str(os.getenv("LANGSMITH_TRACING", "")).strip().lower() in _TRUE_VALUES


def _trace_context(
    name: str,
    *,
    inputs: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
):
    if not _langsmith_enabled():
        return nullcontext(None)
    try:
        from langsmith.run_helpers import trace

        return trace(
            name,
            run_type="chain",
            inputs=inputs or {},
            metadata=metadata or {},
            tags=tags or [],
        )
    except Exception as exc:
        logger.warning("LangSmith trace 初始化失败，继续执行主流程: %s", exc)
        return nullcontext(None)


def build_runtime_config() -> GraphRAGConfig:
    base: Dict[str, Any] = DEFAULT_CONFIG.to_dict()
    str_fields = {
        "NEO4J_URI": "neo4j_uri",
        "NEO4J_USER": "neo4j_user",
        "NEO4J_PASSWORD": "neo4j_password",
        "NEO4J_DATABASE": "neo4j_database",
        "MILVUS_HOST": "milvus_host",
        "MILVUS_COLLECTION_NAME": "milvus_collection_name",
        "EMBEDDING_MODEL": "embedding_model",
        "LLM_MODEL": "llm_model",
        "LLM_GENERATION_PRIMARY_PROVIDER": "llm_generation_primary_provider",
        "LLM_GENERATION_PRIMARY_MODEL": "llm_generation_primary_model",
        "LLM_GENERATION_BACKUP_PROVIDER": "llm_generation_backup_provider",
        "LLM_GENERATION_BACKUP_MODEL": "llm_generation_backup_model",
        "LLM_ASSIST_PRIMARY_PROVIDER": "llm_assist_primary_provider",
        "LLM_ASSIST_PRIMARY_MODEL": "llm_assist_primary_model",
        "LLM_ASSIST_BACKUP_PROVIDER": "llm_assist_backup_provider",
        "LLM_ASSIST_BACKUP_MODEL": "llm_assist_backup_model",
        "RERANKER_MODEL_NAME": "reranker_model_name",
        "RERANKER_DEVICE": "reranker_device",
    }
    int_fields = {
        "MILVUS_PORT": "milvus_port",
        "MILVUS_DIMENSION": "milvus_dimension",
        "TOP_K": "top_k",
        "RECALL_POOL_K": "recall_pool_k",
        "ANSWER_TOP_K": "answer_top_k",
        "MAX_TOKENS": "max_tokens",
        "CHUNK_SIZE": "chunk_size",
        "CHUNK_OVERLAP": "chunk_overlap",
        "MAX_GRAPH_DEPTH": "max_graph_depth",
        "LLM_REQUEST_TIMEOUT_SECONDS": "llm_request_timeout_seconds",
        "GRAPH_ENTITY_MAX_LEN": "graph_entity_max_len",
        "GRAPH_ENTITY_MAX_LEN_RELAXED": "graph_entity_max_len_relaxed",
        "GRAPH_RELAXED_MIN_TERM_LEN": "graph_relaxed_min_term_len",
        "GRAPH_LOW_QUALITY_MAX_KEEP": "graph_low_quality_max_keep",
        "EVIDENCE_GATE_TOP_N": "evidence_gate_top_n",
        "RERANKER_BATCH_SIZE": "reranker_batch_size",
        "RERANKER_MAX_LENGTH": "reranker_max_length",
        "RERANKER_RETRY_COOLDOWN_SECONDS": "reranker_retry_cooldown_seconds",
    }
    float_fields = {
        "TEMPERATURE": "temperature",
        "EVIDENCE_SOFT_THRESHOLD": "evidence_soft_threshold",
        "EVIDENCE_HARD_THRESHOLD": "evidence_hard_threshold",
        "EVIDENCE_HIGH_CONFIDENCE_THRESHOLD": "evidence_high_confidence_threshold",
        "GRAPH_QUALITY_MIN_RELEVANCE": "graph_quality_min_relevance",
        "GRAPH_LOW_QUALITY_PENALTY": "graph_low_quality_penalty",
    }
    bool_fields = {
        "INTENT_ENABLED": "intent_enabled",
        "RERANK_ENABLED": "rerank_enabled",
        "TRUE_RERANK_ENABLED": "true_rerank_enabled",
        "EVIDENCE_GATE_ENABLED": "evidence_gate_enabled",
        "GRAPH_GROUNDING_RELAX_ENABLED": "graph_grounding_relax_enabled",
        "GRAPH_GROUNDING_CONTAINS_ENABLED": "graph_grounding_contains_enabled",
        "GRAPH_GROUNDING_CONTAINS_REQUIRE_LEGAL_SIGNAL": "graph_grounding_contains_require_legal_signal",
        "GRAPH_QUALITY_GATE_ENABLED": "graph_quality_gate_enabled",
    }

    for env_name, key in str_fields.items():
        base[key] = _env_or_default(env_name, base[key], str)
    for env_name, key in int_fields.items():
        base[key] = _env_or_default(env_name, base[key], int)
    for env_name, key in float_fields.items():
        base[key] = _env_or_default(env_name, base[key], float)
    for env_name, key in bool_fields.items():
        base[key] = _env_or_default(env_name, base[key], _to_bool)

    # 历史兼容：若仅设置了 LLM_MODEL，则视为生成主模型配置。
    legacy_llm_model = os.getenv("LLM_MODEL")
    new_generation_model = os.getenv("LLM_GENERATION_PRIMARY_MODEL")
    if legacy_llm_model and not new_generation_model:
        base["llm_generation_primary_model"] = legacy_llm_model
        base["llm_model"] = legacy_llm_model
    elif new_generation_model:
        base["llm_model"] = base["llm_generation_primary_model"]

    return GraphRAGConfig.from_dict(base)

class AdvancedGraphRAGSystem:
    """
    法律法规图RAG系统
    
    核心特性：
    1. 智能路由：自动选择最适合的检索策略
    2. 双引擎检索：传统混合检索 + 图RAG检索
    3. 图结构推理：多跳遍历、子图提取、关系推理
    4. 查询复杂度分析：深度理解用户意图
    5. 自适应学习：基于反馈优化系统性能
    """
    
    def __init__(self, config: Optional[GraphRAGConfig] = None):
        self.config = config or build_runtime_config()
        
        # 核心模块
        self.data_module = None
        self.index_module = None
        self.generation_module = None
        self.llm_dispatcher = None
        
        # 检索引擎
        self.traditional_retrieval = None
        self.graph_rag_retrieval = None
        self.query_router = None
        
        # 系统状态
        self.system_ready = False

    def _get_recall_pool_k(self) -> int:
        return max(1, int(getattr(self.config, "recall_pool_k", getattr(self.config, "top_k", 6))))

    def _get_answer_top_k(self) -> int:
        return max(1, int(getattr(self.config, "answer_top_k", getattr(self.config, "top_k", 6))))
        
    def initialize_system(self):
        """初始化高级图RAG系统"""
        logger.info("启动高级图RAG系统...")
        
        try:
            # 1. 数据准备模块
            print("初始化数据准备模块...")
            self.data_module = GraphDataPreparationModule(
                uri=self.config.neo4j_uri,
                user=self.config.neo4j_user,
                password=self.config.neo4j_password,
                database=self.config.neo4j_database
            )
            
            # 2. 向量索引模块
            print("初始化Milvus向量索引...")
            self.index_module = MilvusIndexConstructionModule(
                host=self.config.milvus_host,
                port=self.config.milvus_port,
                collection_name=self.config.milvus_collection_name,
                dimension=self.config.milvus_dimension,
                model_name=self.config.embedding_model
            )
            
            # 3. 生成模块
            print("初始化LLM调度层...")
            try:
                self.llm_dispatcher = MultiLLMDispatcher(self.config)
            except Exception as dispatcher_error:
                self.llm_dispatcher = None
                logger.warning("LLM调度层初始化失败，回退单通道: %s", dispatcher_error)

            print("初始化生成模块...")
            self.generation_module = GenerationIntegrationModule(
                model_name=self.config.llm_generation_primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                enable_legal_disclaimer=self.config.enable_legal_disclaimer,
                risk_notice_level=self.config.risk_notice_level,
                llm_dispatcher=self.llm_dispatcher,
            )
            
            # 4. 传统混合检索模块
            print("初始化传统混合检索...")
            self.traditional_retrieval = HybridRetrievalModule(
                config=self.config,
                milvus_module=self.index_module,
                data_module=self.data_module,
                llm_client=self.generation_module.client,
                llm_dispatcher=self.llm_dispatcher,
            )
            
            # 5. 图RAG检索模块
            print("初始化图RAG检索引擎...")
            self.graph_rag_retrieval = GraphRAGRetrieval(
                config=self.config,
                llm_client=self.generation_module.client,
                llm_dispatcher=self.llm_dispatcher,
            )
            
            # 6. 智能查询路由器
            print("初始化智能查询路由器...")
            self.query_router = IntelligentQueryRouter(
                traditional_retrieval=self.traditional_retrieval,
                graph_rag_retrieval=self.graph_rag_retrieval,
                llm_client=self.generation_module.client,
                config=self.config,
                llm_dispatcher=self.llm_dispatcher,
            )
            
            print("✅ 高级图RAG系统初始化完成！")
            
        except Exception as e:
            logger.error(f"系统初始化失败: {e}")
            raise
    
    def build_knowledge_base(self, allow_rebuild: bool = True):
        """加载或构建知识库。

        Deer 迁入服务必须传 allow_rebuild=False：集合缺失或加载失败时只让 readiness 失败，
        不得 create/drop/重建 legal_knowledge。源仓 CLI 默认仍保持原行为。
        """
        print("\n检查知识库状态...")
        
        try:
            # 检查Milvus集合是否存在
            if self.index_module.has_collection():
                print("✅ 发现已存在的知识库，尝试加载...")
                if self.index_module.load_collection():
                    print("知识库加载成功！")
                    
                    # 重要：即使从已存在的知识库加载，也需要加载图数据以支持图索引
                    print("加载图数据以支持图检索...")
                    self.data_module.load_graph_data()
                    print("构建法律法规文档...")
                    self._build_domain_documents()
                    print("进行文档分块...")
                    chunks = self.data_module.chunk_documents(
                        chunk_size=self.config.chunk_size,
                        chunk_overlap=self.config.chunk_overlap
                    )
                    
                    self._initialize_retrievers(chunks)
                    return
                if not allow_rebuild:
                    raise RuntimeError(
                        "existing legal_knowledge collection failed to load; refusing to rebuild"
                    )
                print("❌ 知识库加载失败，开始重建...")
            elif not allow_rebuild:
                raise RuntimeError(
                    "existing legal_knowledge collection is required; refusing to rebuild"
                )
            
            print("未找到已存在的集合，开始构建新的知识库...")
            
            # 从Neo4j加载图数据
            print("从Neo4j加载图数据...")
            self.data_module.load_graph_data()
            
            # 构建法律文档
            print("构建法律法规文档...")
            self._build_domain_documents()
            
            # 进行文档分块
            print("进行文档分块...")
            chunks = self.data_module.chunk_documents(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )
            
            # 构建Milvus向量索引
            print("构建Milvus向量索引...")
            if not self.index_module.build_vector_index(chunks):
                raise Exception("构建向量索引失败")
            
            # 初始化检索器
            self._initialize_retrievers(chunks)
            
            # 显示统计信息
            self._show_knowledge_base_stats()
            
            print("✅ 知识库构建完成！")
            
        except Exception as e:
            logger.error(f"知识库构建失败: {e}")
            raise

    def _build_domain_documents(self):
        """构建领域文档，兼容新旧方法命名。"""
        if hasattr(self.data_module, "build_legal_documents"):
            self.data_module.build_legal_documents()
            return
        # 兼容旧版方法名，避免主流程断裂
        self.data_module.build_recipe_documents()

    def _initialize_retrievers(self, chunks: List = None):
        """初始化检索器"""
        print("初始化检索引擎...")
        
        # 如果没有chunks，从数据模块获取
        if chunks is None:
            chunks = self.data_module.chunks or []
        
        # 初始化传统检索器
        self.traditional_retrieval.initialize(chunks)
        
        # 初始化图RAG检索器
        self.graph_rag_retrieval.initialize()
        
        self.system_ready = True
        print("✅ 检索引擎初始化完成！")
    
    def _show_knowledge_base_stats(self):
        """显示知识库统计信息"""
        print(f"\n知识库统计:")
        
        # 数据统计
        stats = self.data_module.get_statistics()
        print(f"   法规文档数: {stats.get('total_law_documents', stats.get('total_recipes', 0))}")
        print(f"   条文数量: {stats.get('total_articles', stats.get('total_ingredients', 0))}")
        print(f"   风险场景数: {stats.get('total_risk_scenarios', 0)}")
        print(f"   合规步骤数: {stats.get('total_compliance_steps', stats.get('total_cooking_steps', 0))}")
        print(f"   文档数量: {stats.get('total_documents', 0)}")
        print(f"   文本块数: {stats.get('total_chunks', 0)}")
        
        # Milvus统计
        milvus_stats = self.index_module.get_collection_stats()
        print(f"   向量索引: {milvus_stats.get('row_count', 0)} 条记录")
        
        # 图RAG统计
        route_stats = self.query_router.get_route_statistics()
        print(f"   路由统计: 总查询 {route_stats.get('total_queries', 0)} 次")
        
        domains = stats.get("legal_domains", stats.get("categories", {}))
        if domains:
            top_domains = list(domains.keys())[:10]
            print(f"   主要法律领域: {', '.join(top_domains)}")

    @staticmethod
    def _document_snippet(text: str, limit: int = 180) -> str:
        compact = " ".join(str(text or "").split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit]}..."

    @staticmethod
    def _analysis_to_dict(analysis: QueryAnalysis) -> Dict[str, Any]:
        return {
            "strategy": analysis.recommended_strategy.value,
            "query_complexity": round(float(analysis.query_complexity), 4),
            "relationship_intensity": round(float(analysis.relationship_intensity), 4),
            "confidence": round(float(analysis.confidence), 4),
            "reasoning_required": bool(analysis.reasoning_required),
            "reasoning": analysis.reasoning,
        }

    @staticmethod
    def _analysis_from_dict(data: Dict[str, Any]) -> QueryAnalysis:
        strategy_value = str(data.get("strategy", SearchStrategy.HYBRID_TRADITIONAL.value) or "")
        try:
            strategy = SearchStrategy(strategy_value)
        except Exception:
            strategy = SearchStrategy.HYBRID_TRADITIONAL
        return QueryAnalysis(
            query_complexity=_safe_float(data.get("query_complexity", 0.0)),
            relationship_intensity=_safe_float(data.get("relationship_intensity", 0.0)),
            reasoning_required=bool(data.get("reasoning_required", False)),
            entity_count=int(data.get("entity_count", 0) or 0),
            recommended_strategy=strategy,
            confidence=_safe_float(data.get("confidence", 0.0)),
            reasoning=str(data.get("reasoning", "") or ""),
        )

    def _documents_to_payload(self, documents: List) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for doc in documents or []:
            metadata = doc.metadata or {}
            payload.append(
                {
                    "display_title": (
                        metadata.get("display_title")
                        or metadata.get("law_name")
                        or metadata.get("article_title")
                        or metadata.get("recipe_name")
                        or "未知内容"
                    ),
                    "law_name": str(metadata.get("law_name", metadata.get("law_name_std", "")) or ""),
                    "article_id": str(metadata.get("article_id", metadata.get("article_id_std", "")) or ""),
                    "article_title": str(metadata.get("article_title", "") or ""),
                    "snippet": self._document_snippet(doc.page_content),
                    "score": round(
                        _safe_float(
                            metadata.get(
                                "rerank_score",
                                metadata.get("final_score", metadata.get("relevance_score", 0.0)),
                            )
                        ),
                        4,
                    ),
                    "search_type": str(metadata.get("search_type", "") or ""),
                    "route_strategy": str(metadata.get("route_strategy", "") or ""),
                    "search_source": str(metadata.get("search_source", "") or ""),
                    "route_fallback": str(metadata.get("route_fallback", "") or ""),
                    "rerank_model": str(metadata.get("rerank_model", "") or ""),
                    "rerank_latency_ms": int(metadata.get("rerank_latency_ms", 0) or 0),
                    "rerank_fallback_reason": str(metadata.get("rerank_fallback_reason", "") or ""),
                }
            )
        return payload

    @staticmethod
    def _merge_documents(prefetched_documents: List[Any], retrieved_documents: List[Any], limit: int = 10) -> List[Any]:
        merged: List[Any] = []
        seen = set()
        for doc in (prefetched_documents or []) + (retrieved_documents or []):
            metadata = getattr(doc, "metadata", {}) or {}
            chunk_id = str(metadata.get("chunk_id", "") or "")
            key = chunk_id or str(hash(str(getattr(doc, "page_content", ""))[:200]))
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
            if len(merged) >= max(1, limit):
                break
        return merged

    def _evaluate_evidence_mode(self, documents: List, question: str) -> Dict[str, Any]:
        gate_top_n = max(1, int(getattr(self.config, "evidence_gate_top_n", 3)))

        def _normalize_terms(terms: List[str]) -> List[str]:
            normalized: List[str] = []
            seen = set()
            for term in terms or []:
                value = str(term).strip().lower()
                if not value or value in seen:
                    continue
                seen.add(value)
                normalized.append(value)
            return normalized

        def _is_explicit_legal_term(term: str) -> bool:
            value = str(term or "").strip()
            if not value:
                return False
            if re.fullmatch(r"第[0-9一二三四五六七八九十百千万〇零两]+条", value):
                return True
            return value.endswith(("法", "法典", "条例", "规定", "办法", "解释"))

        def _collect_doc_must_terms(candidate_docs: List) -> List[str]:
            terms: List[str] = []
            for doc in candidate_docs[:gate_top_n]:
                md = doc.metadata or {}
                raw_terms = md.get("must_terms", [])
                if isinstance(raw_terms, str):
                    terms.append(raw_terms)
                elif isinstance(raw_terms, (list, tuple, set)):
                    terms.extend([str(x) for x in raw_terms if str(x).strip()])
            return _normalize_terms(terms)

        def _build_doc_match_text(doc) -> str:
            md = doc.metadata or {}
            return " ".join(
                [
                    str(doc.page_content or ""),
                    str(md.get("display_title", "") or ""),
                    str(md.get("law_name", "") or ""),
                    str(md.get("article_title", "") or ""),
                    str(md.get("article_id", "") or ""),
                ]
            ).lower()

        def _derive_must_signal_from_question(candidate_docs: List) -> Dict[str, Any]:
            doc_terms = _collect_doc_must_terms(candidate_docs)
            if doc_terms:
                must_terms = doc_terms
            else:
                intent = rule_based_parse_query_intent(question)
                must_terms = _normalize_terms(intent.must_terms or [])
            if not must_terms:
                return {
                    "has_signal": False,
                    "hit_count": 0,
                    "hit_ratio": 0.0,
                    "must_terms": [],
                    "explicit_term_detected": False,
                }

            gate_docs = candidate_docs[:gate_top_n]
            joined_text = "\n".join(_build_doc_match_text(doc) for doc in gate_docs)
            hit_count = sum(1 for term in must_terms if term and term in joined_text)
            hit_ratio = (hit_count / float(len(must_terms))) if must_terms else 0.0
            return {
                "has_signal": True,
                "hit_count": int(hit_count),
                "hit_ratio": float(hit_ratio),
                "must_terms": must_terms,
                "explicit_term_detected": any(_is_explicit_legal_term(term) for term in must_terms),
            }

        default = {
            "mode": "strong",
            "reason": "gate_disabled_or_sufficient",
            "top_rerank_score": 0.0,
            "top_must_hit_count": 0,
        }
        if not documents:
            default.update({"mode": "insufficient", "reason": "empty_documents"})
            return default
        if not bool(getattr(self.config, "evidence_gate_enabled", True)):
            return default

        top_doc = documents[0]
        metadata = top_doc.metadata or {}
        top_rerank_score = float(
            metadata.get(
                "rerank_score",
                metadata.get("final_score", metadata.get("relevance_score", 0.0)),
            )
            or 0.0
        )
        derived = _derive_must_signal_from_question(documents)
        has_must_signal = bool(derived.get("has_signal", False))
        top_must_hit_count = int(derived.get("hit_count", 0))
        top_must_total = len(derived.get("must_terms", []) or [])
        explicit_term_detected = bool(derived.get("explicit_term_detected", False))
        metadata["must_terms_hit_count"] = top_must_hit_count
        metadata["must_terms_hit_ratio"] = round(float(derived.get("hit_ratio", 0.0)), 4)
        metadata["must_terms"] = derived.get("must_terms", [])
        metadata["evidence_gate_top_n"] = gate_top_n
        top_doc.metadata = metadata
        soft_threshold = float(getattr(self.config, "evidence_soft_threshold", 0.5))
        hard_threshold = float(getattr(self.config, "evidence_hard_threshold", 0.5))
        high_conf_threshold = float(getattr(self.config, "evidence_high_confidence_threshold", 0.65))

        if not has_must_signal:
            return {
                "mode": "weak",
                "reason": "missing_must_signal_no_terms",
                "top_rerank_score": round(top_rerank_score, 4),
                "top_must_hit_count": top_must_hit_count,
            }

        # 高分豁免：只要存在至少1个 must_term 命中且重排分足够高，直接给 strong。
        if top_rerank_score >= high_conf_threshold and top_must_hit_count >= 1:
            return {
                "mode": "strong",
                "reason": "high_score_with_min_must_hit",
                "top_rerank_score": round(top_rerank_score, 4),
                "top_must_hit_count": top_must_hit_count,
                "question": question,
            }

        if top_must_hit_count == 0 and top_rerank_score < hard_threshold:
            return {
                "mode": "insufficient",
                "reason": "hard_gate_no_must_hit_and_low_rerank",
                "top_rerank_score": round(top_rerank_score, 4),
                "top_must_hit_count": top_must_hit_count,
            }
        required_hits = 2 if (explicit_term_detected and top_must_total > 1) else 1
        if top_must_hit_count < required_hits:
            reason = "soft_gate_low_must_hit"
            if top_rerank_score < soft_threshold:
                reason = "soft_gate_low_must_hit_and_low_rerank"
            return {
                "mode": "weak",
                "reason": reason,
                "top_rerank_score": round(top_rerank_score, 4),
                "top_must_hit_count": top_must_hit_count,
            }
        return {
            "mode": "strong",
            "reason": "sufficient_hits",
            "top_rerank_score": round(top_rerank_score, 4),
            "top_must_hit_count": top_must_hit_count,
            "question": question,
        }

    def ask_question_payload(
        self,
        question: str,
        explain_routing: bool = False,
        chat_id: Optional[str] = None,
        active_file_ids: Optional[List[str]] = None,
        prefetched_documents: Optional[List[Any]] = None,
        eval_fast_mode: bool = False,
    ) -> Dict[str, Any]:
        """Structured chat result for API/UI consumers."""
        if not self.system_ready:
            raise ValueError("系统未就绪，请先构建知识库")

        safe_question = sanitize_query_text(question)
        if not safe_question:
            raise ValueError("输入问题包含无效字符或为空，请重新输入。")

        if isinstance(question, str) and has_surrogates(question):
            logger.warning("检测到输入包含 surrogate 字符，已自动清洗后继续处理")

        start_time = time.time()
        relevant_docs: List[Any] = []
        draft_claims: List[str] = []
        refined_claims: List[Dict[str, Any]] = []
        evidence_state: Dict[str, Any] = {
            "mode": "insufficient",
            "reason": "uninitialized",
            "top_rerank_score": 0.0,
            "top_must_hit_count": 0,
        }
        routing_explanation = ""
        route_metrics: Dict[str, Any] = {}
        retrieval_scope: Optional[Dict[str, Any]] = None
        if chat_id:
            retrieval_scope = {
                "chat_id": str(chat_id).strip(),
                "active_file_ids": [str(file_id).strip() for file_id in (active_file_ids or []) if str(file_id).strip()],
            }

        try:
            analysis = None
            recall_pool_k = self._get_recall_pool_k()
            answer_top_k = self._get_answer_top_k()
            if eval_fast_mode and not explain_routing:
                analysis = self.query_router._rule_based_analysis(safe_question)
                analysis.recommended_strategy = SearchStrategy.HYBRID_TRADITIONAL
                analysis.reasoning = (
                    f"{analysis.reasoning}|eval_fast_force_traditional"
                    if analysis.reasoning
                    else "eval_fast_force_traditional"
                )
            elif explain_routing:
                try:
                    analysis = self.query_router.analyze_query(safe_question)
                    routing_explanation = self.query_router.format_routing_explanation(safe_question, analysis)
                except Exception:
                    logger.exception("生成路由解释失败")
            with _trace_context(
                "main.route_query",
                inputs={
                    "question": safe_question,
                    "recall_pool_k": recall_pool_k,
                    "answer_top_k": answer_top_k,
                    "retrieval_scope": retrieval_scope or {},
                    "eval_fast_mode": bool(eval_fast_mode),
                },
                metadata={
                    "component": "main",
                    "stage": "route_query",
                },
                tags=["phase:retrieval"],
            ) as route_run:
                relevant_docs, analysis = self.query_router.route_query(
                    safe_question,
                    recall_pool_k,
                    analysis=analysis,
                    retrieval_scope=retrieval_scope,
                    apply_rerank=False,
                    force_rule_intent=bool(eval_fast_mode),
                )
                route_metrics = self.query_router.get_last_route_trace()
                if route_run is not None:
                    analysis_dict = self._analysis_to_dict(analysis)
                    route_run.end(
                        outputs={
                            "strategy": analysis_dict.get("strategy", ""),
                            "query_complexity": analysis_dict.get("query_complexity", 0.0),
                            "confidence": analysis_dict.get("confidence", 0.0),
                            "documents_count": len(relevant_docs or []),
                        }
                    )
            if prefetched_documents:
                merge_limit = max(recall_pool_k * 2, len(prefetched_documents) + recall_pool_k)
                relevant_docs = self._merge_documents(prefetched_documents, relevant_docs, limit=merge_limit)
            if not relevant_docs:
                elapsed = round(time.time() - start_time, 4)
                return {
                    "answer": "抱歉，没有找到相关的法律法规信息。请尝试换一种问法。",
                    "analysis": self._analysis_to_dict(analysis),
                    "evidence": {
                        "mode": "insufficient",
                        "reason": "empty_documents",
                        "top_rerank_score": 0.0,
                        "top_must_hit_count": 0,
                    },
                    "documents": [],
                    "refine": {
                        "draft_claim_count": 0,
                        "refined_claim_count": 0,
                        "supported_count": 0,
                        "weak_count": 0,
                        "unsupported_count": 0,
                        "claims": [],
                    },
                    "elapsed_seconds": elapsed,
                    "route_fallback": "",
                    "routing_explanation": routing_explanation,
                    "route_metrics": route_metrics,
                }

            with _trace_context(
                "main.rerank_documents",
                inputs={
                    "question": safe_question,
                    "pool_count": len(relevant_docs),
                    "answer_top_k": answer_top_k,
                },
                metadata={
                    "component": "main",
                    "stage": "rerank_documents",
                    "reranker_model": getattr(self.config, "reranker_model_name", ""),
                },
                tags=["phase:retrieval", "phase:rerank"],
            ) as rerank_run:
                reranked_docs = self.traditional_retrieval.rerank_documents(
                    safe_question,
                    relevant_docs,
                    top_k=answer_top_k,
                )
                if reranked_docs:
                    relevant_docs = reranked_docs
                else:
                    relevant_docs = relevant_docs[:answer_top_k]
                if rerank_run is not None:
                    top_score = 0.0
                    if relevant_docs:
                        top_score = _safe_float((relevant_docs[0].metadata or {}).get("rerank_score", 0.0))
                    rerank_run.end(
                        outputs={
                            "reranked_count": len(relevant_docs),
                            "top_rerank_score": round(top_score, 4),
                        }
                    )

            evidence_state = self._evaluate_evidence_mode(relevant_docs, safe_question)
            with _trace_context(
                "main.generate_answer",
                inputs={
                    "question": safe_question,
                    "answer_mode": evidence_state.get("mode", "strong"),
                    "documents_count": len(relevant_docs),
                },
                metadata={
                    "component": "main",
                    "stage": "generate_answer",
                    "evidence_mode": evidence_state.get("mode", "strong"),
                },
                tags=["phase:generation"],
            ) as gen_run:
                refined_payload = self.generation_module.generate_refined_answer(
                    safe_question,
                    relevant_docs,
                    answer_mode=evidence_state.get("mode", "strong"),
                )
                answer = str(refined_payload.get("answer", "") or "")
                draft_claims = [str(item) for item in (refined_payload.get("draft_claims", []) or [])]
                refined_claims = list(refined_payload.get("refined_claims", []) or [])
                if gen_run is not None:
                    gen_run.end(
                        outputs={
                            "answer_preview": str(answer)[:300],
                            "answer_mode": evidence_state.get("mode", "strong"),
                            "draft_claim_count": len(draft_claims),
                            "refined_claim_count": len(refined_claims),
                        }
                    )
            elapsed = round(time.time() - start_time, 4)
            route_fallback = ""
            for doc in relevant_docs:
                fallback = str((doc.metadata or {}).get("route_fallback", "") or "")
                if fallback:
                    route_fallback = fallback
                    break
            return {
                "answer": answer,
                "analysis": self._analysis_to_dict(analysis),
                "evidence": {
                    "mode": str(evidence_state.get("mode", "strong")),
                    "reason": str(evidence_state.get("reason", "unknown")),
                    "top_rerank_score": round(_safe_float(evidence_state.get("top_rerank_score", 0.0)), 4),
                    "top_must_hit_count": int(evidence_state.get("top_must_hit_count", 0) or 0),
                },
                "documents": self._documents_to_payload(relevant_docs),
                "refine": {
                    "draft_claim_count": len(draft_claims),
                    "refined_claim_count": len(refined_claims),
                    "supported_count": sum(1 for x in refined_claims if str(x.get("verdict", "")) == "supported"),
                    "weak_count": sum(1 for x in refined_claims if str(x.get("verdict", "")) == "weak"),
                    "unsupported_count": sum(
                        1 for x in refined_claims if str(x.get("verdict", "")) == "unsupported"
                    ),
                    "claims": refined_claims,
                },
                "elapsed_seconds": elapsed,
                "route_fallback": route_fallback,
                "routing_explanation": routing_explanation,
                "route_metrics": route_metrics,
            }
        except Exception:
            logger.exception("结构化问答执行失败")
            raise
    
    def ask_question_with_routing(self, question: str, stream: bool = False, explain_routing: bool = False):
        """
        智能问答：自动选择最佳检索策略
        """
        if not self.system_ready:
            raise ValueError("系统未就绪，请先构建知识库")

        if not stream:
            payload = self.ask_question_payload(question, explain_routing=explain_routing)
            analysis_data = payload.get("analysis", {})
            evidence_state = payload.get("evidence", {})
            documents = payload.get("documents", [])
            answer = payload.get("answer", "")
            analysis = self._analysis_from_dict(analysis_data)

            print(f"\n❓ 用户问题: {sanitize_query_text(question)}")
            strategy = analysis_data.get("strategy", "unknown")
            strategy_icons = {
                "hybrid_traditional": "🔍",
                "graph_rag": "🕸️",
                "combined": "🔄",
            }
            print(f"{strategy_icons.get(strategy, '❓')} 使用策略: {strategy}")
            print(
                "📊 复杂度: %.2f, 关系密集度: %.2f"
                % (
                    _safe_float(analysis_data.get("query_complexity", 0.0)),
                    _safe_float(analysis_data.get("relationship_intensity", 0.0)),
                )
            )
            if documents:
                doc_info = []
                for doc in documents:
                    display_title = doc.get("display_title", "未知内容")
                    article_id = doc.get("article_id", "")
                    search_type = doc.get("search_type", "unknown")
                    score = _safe_float(doc.get("score", 0.0))
                    id_suffix = f"#{article_id}" if article_id else ""
                    doc_info.append(f"{display_title}{id_suffix}({search_type}, {score:.3f})")
                print(f"📋 找到 {len(documents)} 个相关文档: {', '.join(doc_info[:3])}")
                if len(documents) > 3:
                    print(f"    等 {len(documents)} 个结果...")
            else:
                return answer, analysis
            print(
                "🧪 证据评估: mode=%s, reason=%s, rerank=%.3f, must_hit=%s"
                % (
                    evidence_state.get("mode", "strong"),
                    evidence_state.get("reason", "unknown"),
                    _safe_float(evidence_state.get("top_rerank_score", 0.0)),
                    evidence_state.get("top_must_hit_count", 0),
                )
            )
            print("🎯 智能生成回答...")
            print("\n⏱️ 问答完成，耗时: %.2f秒" % _safe_float(payload.get("elapsed_seconds", 0.0)))
            return answer, analysis

        safe_question = sanitize_query_text(question)
        if not safe_question:
            return "输入问题包含无效字符或为空，请重新输入。", None

        if isinstance(question, str) and has_surrogates(question):
            logger.warning("检测到输入包含 surrogate 字符，已自动清洗后继续处理")

        print(f"\n❓ 用户问题: {safe_question}")
        
        # 显示路由决策解释（可选）
        analysis = None
        if explain_routing:
            analysis = self.query_router.analyze_query(safe_question)
            explanation = self.query_router.format_routing_explanation(safe_question, analysis)
            print(explanation)
        
        start_time = time.time()
        recall_pool_k = self._get_recall_pool_k()
        answer_top_k = self._get_answer_top_k()
        
        try:
            # 1. 智能路由检索
            print("执行智能查询路由...")
            relevant_docs, analysis = self.query_router.route_query(
                safe_question,
                recall_pool_k,
                analysis=analysis,
                retrieval_scope=None,
                apply_rerank=False,
            )
            
            # 2. 显示路由信息
            strategy_icons = {
                "hybrid_traditional": "🔍",
                "graph_rag": "🕸️", 
                "combined": "🔄"
            }
            strategy_icon = strategy_icons.get(analysis.recommended_strategy.value, "❓")
            print(f"{strategy_icon} 使用策略: {analysis.recommended_strategy.value}")
            print(f"📊 复杂度: {analysis.query_complexity:.2f}, 关系密集度: {analysis.relationship_intensity:.2f}")
            
            # 3. 显示检索结果信息
            if relevant_docs:
                reranked_docs = self.traditional_retrieval.rerank_documents(
                    safe_question,
                    relevant_docs,
                    top_k=answer_top_k,
                )
                if reranked_docs:
                    relevant_docs = reranked_docs
                else:
                    relevant_docs = relevant_docs[:answer_top_k]
                doc_info = []
                for doc in relevant_docs:
                    display_title = (
                        doc.metadata.get("display_title")
                        or doc.metadata.get("law_name")
                        or doc.metadata.get("article_title")
                        or doc.metadata.get("recipe_name")
                        or "未知内容"
                    )
                    article_id = doc.metadata.get("article_id", "")
                    search_type = doc.metadata.get('search_type', doc.metadata.get('route_strategy', 'unknown'))
                    score = doc.metadata.get('final_score', doc.metadata.get('relevance_score', 0))
                    id_suffix = f"#{article_id}" if article_id else ""
                    doc_info.append(f"{display_title}{id_suffix}({search_type}, {score:.3f})")
                
                print(f"📋 找到 {len(relevant_docs)} 个相关文档: {', '.join(doc_info[:3])}")
                if len(doc_info) > 3:
                    print(f"    等 {len(relevant_docs)} 个结果...")
            else:
                # 保持返回值签名一致：始终返回 (result, analysis)
                return "抱歉，没有找到相关的法律法规信息。请尝试换一种问法。", analysis

            evidence_state = self._evaluate_evidence_mode(relevant_docs, safe_question)
            print(
                "🧪 证据评估: mode=%s, reason=%s, rerank=%.3f, must_hit=%s"
                % (
                    evidence_state.get("mode", "strong"),
                    evidence_state.get("reason", "unknown"),
                    float(evidence_state.get("top_rerank_score", 0.0)),
                    evidence_state.get("top_must_hit_count", 0),
                )
            )
            
            # 4. 生成回答
            print("🎯 智能生成回答...")
            
            if stream:
                try:
                    for chunk_text in self.generation_module.generate_adaptive_answer_stream(
                        safe_question,
                        relevant_docs,
                        answer_mode=evidence_state.get("mode", "strong"),
                    ):
                        print(chunk_text, end="", flush=True)
                    print("\n")
                    result = "流式输出完成"
                except Exception as stream_error:
                    logger.error(f"流式输出过程中出现错误: {stream_error}")
                    print(f"\n⚠️ 流式输出中断，切换到标准模式...")
                    # 使用非流式作为后备
                    result = self.generation_module.generate_adaptive_answer(
                        safe_question,
                        relevant_docs,
                        answer_mode=evidence_state.get("mode", "strong"),
                    )
            else:
                result = self.generation_module.generate_adaptive_answer(
                    safe_question,
                    relevant_docs,
                    answer_mode=evidence_state.get("mode", "strong"),
                )
            
            # 5. 性能统计
            end_time = time.time()
            print(f"\n⏱️ 问答完成，耗时: {end_time - start_time:.2f}秒")
            
            return result, analysis
            
        except Exception as e:
            logger.error(f"问答处理失败: {e}")
            return f"抱歉，处理问题时出现错误：{str(e)}", None
    

    

    
    def run_interactive(self):
        """运行交互式问答"""
        if not self.system_ready:
            print("❌ 系统未就绪，请先构建知识库")
            return
            
        print("\n欢迎使用法律法规 GraphRAG 咨询助手！")
        print("可用功能：")
        print("   - 'stats' : 查看系统统计")
        print("   - 'rebuild' : 重建知识库")
        print("   - 'quit' : 退出系统")
        print("\n" + "="*50)
        
        while True:
            try:
                user_input = input("\n您的问题: ").strip()

                if not user_input:
                    continue

                safe_input = sanitize_query_text(user_input)
                if not safe_input:
                    print("⚠️ 输入包含无效字符，请重新输入。")
                    continue

                if has_surrogates(user_input):
                    logger.warning("交互输入检测到 surrogate 字符，已自动清洗")

                if safe_input.lower() == 'quit':
                    break
                elif safe_input.lower() == 'stats':
                    self._show_system_stats()
                    continue
                elif safe_input.lower() == 'rebuild':
                    self._rebuild_knowledge_base()
                    continue
                
                # 普通问答 - 使用默认设置
                use_stream = True  # 默认使用流式输出
                explain_routing = False  # 默认不显示路由决策

                print("\n回答:")
                
                result, analysis = self.ask_question_with_routing(
                    safe_input,
                    stream=use_stream, 
                    explain_routing=explain_routing
                )
                
                if not use_stream and result:
                    print(f"{result}\n")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"处理问题时出错: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n👋 感谢使用法律法规 GraphRAG 咨询助手！")
        self._cleanup()
    
    def _show_system_stats(self):
        """显示系统统计信息"""
        print("\n系统运行统计")
        print("=" * 40)
        
        # 路由统计
        route_stats = self.query_router.get_route_statistics()
        total_queries = route_stats.get('total_queries', 0)
        
        if total_queries > 0:
            print(f"总查询次数: {total_queries}")
            print(f"传统检索: {route_stats.get('traditional_count', 0)} ({route_stats.get('traditional_ratio', 0):.1%})")
            print(f"图RAG检索: {route_stats.get('graph_rag_count', 0)} ({route_stats.get('graph_rag_ratio', 0):.1%})")
            print(f"组合策略: {route_stats.get('combined_count', 0)} ({route_stats.get('combined_ratio', 0):.1%})")
        else:
            print("暂无查询记录")
        
        # 知识库统计
        self._show_knowledge_base_stats()
    
    def _rebuild_knowledge_base(self):
        """重建知识库"""
        print("\n准备重建知识库...")
        
        # 确认操作
        confirm = input("⚠️  这将删除现有的向量数据并重新构建，是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 重建操作已取消")
            return
        
        try:
            print("删除现有的Milvus集合...")
            if self.index_module.delete_collection():
                print("✅ 现有集合已删除")
            else:
                print("删除集合时出现问题，继续重建...")
            
            # 重新构建知识库
            print("开始重建知识库...")
            self.build_knowledge_base()
            
            print("✅ 知识库重建完成！")
            
        except Exception as e:
            logger.error(f"重建知识库失败: {e}")
            print(f"❌ 重建失败: {e}")
            print("建议：请检查Milvus服务状态后重试")
    
    def _cleanup(self):
        """清理资源"""
        if self.data_module:
            self.data_module.close()
        if self.traditional_retrieval:
            self.traditional_retrieval.close()
        if self.graph_rag_retrieval:
            self.graph_rag_retrieval.close()
        if self.index_module:
            self.index_module.close()

def main():
    """主函数"""
    try:
        print("启动高级图RAG系统...")
        
        # 创建高级图RAG系统
        rag_system = AdvancedGraphRAGSystem()
        
        # 初始化系统
        rag_system.initialize_system()
        
        # 构建知识库
        rag_system.build_knowledge_base()
        
        # 运行交互式问答
        rag_system.run_interactive()
        
    except Exception as e:
        logger.error(f"系统运行失败: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n❌ 系统错误: {e}")

if __name__ == "__main__":
    main() 
