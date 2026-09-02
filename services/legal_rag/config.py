"""
基于图数据库的RAG系统配置文件
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List

@dataclass
class GraphRAGConfig:
    """基于图数据库的RAG系统配置类"""

    # Neo4j数据库配置
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "all-in-rag"
    neo4j_database: str = "neo4j"

    # Milvus配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection_name: str = "legal_knowledge"
    milvus_dimension: int = 512  # BGE-small-zh-v1.5的向量维度

    # 模型配置
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    llm_model: str = "kimi-k2-0711-preview"
    llm_request_timeout_seconds: int = 60

    # 多模型分流配置（固定分流 + 主备切换）
    llm_generation_primary_provider: str = "kimi"
    llm_generation_primary_model: str = "kimi-k2-0711-preview"
    llm_generation_backup_provider: str = "deepseek"
    llm_generation_backup_model: str = "deepseek-chat"
    llm_assist_primary_provider: str = "deepseek"
    llm_assist_primary_model: str = "deepseek-chat"
    llm_assist_backup_provider: str = "kimi"
    llm_assist_backup_model: str = "kimi-k2-0711-preview"

    # 检索配置（LightRAG Round-robin策略）
    top_k: int = 6
    recall_pool_k: int = 50
    answer_top_k: int = 5
    intent_enabled: bool = True
    rerank_enabled: bool = True
    true_rerank_enabled: bool = True
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: str = "auto"
    reranker_batch_size: int = 8
    reranker_max_length: int = 512
    reranker_retry_cooldown_seconds: int = 60
    evidence_gate_enabled: bool = True
    evidence_soft_threshold: float = 0.4
    evidence_hard_threshold: float = 0.35
    evidence_high_confidence_threshold: float = 0.65
    evidence_gate_top_n: int = 3
    graph_entity_max_len: int = 20
    graph_grounding_relax_enabled: bool = True
    graph_entity_max_len_relaxed: int = 32
    graph_relaxed_min_term_len: int = 2
    graph_grounding_contains_enabled: bool = False
    graph_grounding_contains_require_legal_signal: bool = True
    graph_quality_gate_enabled: bool = True
    graph_quality_min_relevance: float = 0.55
    graph_low_quality_max_keep: int = 1
    graph_low_quality_penalty: float = 0.35

    # 生成配置
    temperature: float = 0.1
    max_tokens: int = 2048

    # 图数据处理配置
    chunk_size: int = 500
    chunk_overlap: int = 50
    max_graph_depth: int = 2  # 图遍历最大深度
    neo4j_legal_fulltext_index: str = "legal_fulltext_idx"

    # 法律实体标签配置
    law_document_label: str = "LawDocument"
    article_label: str = "Article"
    domain_label: str = "LegalDomain"
    risk_scenario_label: str = "RiskScenario"
    compliance_step_label: str = "ComplianceStep"

    # 法律图关系白名单
    graph_relation_types: List[str] = field(default_factory=lambda: [
        "HAS_ARTICLE",
        "BELONGS_TO_DOMAIN",
        "CITES",
        "RELATES_TO",
        "APPLIES_TO",
        "REQUIRES_STEP",
        "PRECEDES",
    ])

    # 法律安全输出控制
    enable_legal_disclaimer: bool = True
    risk_notice_level: str = "light"

    def __post_init__(self):
        """初始化后的处理"""
        # 向后兼容：仅在缺失时互相回填，避免静默覆盖用户显式配置。
        if not self.llm_generation_primary_model and self.llm_model:
            self.llm_generation_primary_model = self.llm_model
        if not self.llm_model and self.llm_generation_primary_model:
            self.llm_model = self.llm_generation_primary_model
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'GraphRAGConfig':
        """从字典创建配置对象"""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'neo4j_uri': self.neo4j_uri,
            'neo4j_user': self.neo4j_user,
            'neo4j_password': self.neo4j_password,
            'neo4j_database': self.neo4j_database,
            'milvus_host': self.milvus_host,
            'milvus_port': self.milvus_port,
            'milvus_collection_name': self.milvus_collection_name,
            'milvus_dimension': self.milvus_dimension,
            'embedding_model': self.embedding_model,
            'llm_model': self.llm_model,
            'llm_request_timeout_seconds': self.llm_request_timeout_seconds,
            'llm_generation_primary_provider': self.llm_generation_primary_provider,
            'llm_generation_primary_model': self.llm_generation_primary_model,
            'llm_generation_backup_provider': self.llm_generation_backup_provider,
            'llm_generation_backup_model': self.llm_generation_backup_model,
            'llm_assist_primary_provider': self.llm_assist_primary_provider,
            'llm_assist_primary_model': self.llm_assist_primary_model,
            'llm_assist_backup_provider': self.llm_assist_backup_provider,
            'llm_assist_backup_model': self.llm_assist_backup_model,
            'top_k': self.top_k,
            'recall_pool_k': self.recall_pool_k,
            'answer_top_k': self.answer_top_k,
            'intent_enabled': self.intent_enabled,
            'rerank_enabled': self.rerank_enabled,
            'true_rerank_enabled': self.true_rerank_enabled,
            'reranker_model_name': self.reranker_model_name,
            'reranker_device': self.reranker_device,
            'reranker_batch_size': self.reranker_batch_size,
            'reranker_max_length': self.reranker_max_length,
            'reranker_retry_cooldown_seconds': self.reranker_retry_cooldown_seconds,
            'evidence_gate_enabled': self.evidence_gate_enabled,
            'evidence_soft_threshold': self.evidence_soft_threshold,
            'evidence_hard_threshold': self.evidence_hard_threshold,
            'evidence_high_confidence_threshold': self.evidence_high_confidence_threshold,
            'evidence_gate_top_n': self.evidence_gate_top_n,
            'graph_entity_max_len': self.graph_entity_max_len,
            'graph_grounding_relax_enabled': self.graph_grounding_relax_enabled,
            'graph_entity_max_len_relaxed': self.graph_entity_max_len_relaxed,
            'graph_relaxed_min_term_len': self.graph_relaxed_min_term_len,
            'graph_grounding_contains_enabled': self.graph_grounding_contains_enabled,
            'graph_grounding_contains_require_legal_signal': self.graph_grounding_contains_require_legal_signal,
            'graph_quality_gate_enabled': self.graph_quality_gate_enabled,
            'graph_quality_min_relevance': self.graph_quality_min_relevance,
            'graph_low_quality_max_keep': self.graph_low_quality_max_keep,
            'graph_low_quality_penalty': self.graph_low_quality_penalty,

            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'max_graph_depth': self.max_graph_depth,
            'neo4j_legal_fulltext_index': self.neo4j_legal_fulltext_index,
            'law_document_label': self.law_document_label,
            'article_label': self.article_label,
            'domain_label': self.domain_label,
            'risk_scenario_label': self.risk_scenario_label,
            'compliance_step_label': self.compliance_step_label,
            'graph_relation_types': self.graph_relation_types,
            'enable_legal_disclaimer': self.enable_legal_disclaimer,
            'risk_notice_level': self.risk_notice_level,
        }

# 默认配置实例
DEFAULT_CONFIG = GraphRAGConfig() 
