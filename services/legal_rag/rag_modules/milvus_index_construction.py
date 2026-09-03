# =============================================================
# 文件介绍：Milvus 索引构建模块（MilvusIndexConstructionModule）
# 目标：替换 C8 的 FAISS 本地索引，改用 Milvus 分布式向量数据库构建生产级向量索引。
# 思路：
#   C8 用 FAISS（本地文件），C9 改用 Milvus（需运行 Docker 服务）：
#     - Milvus 支持更大规模数据、更多索引类型、分布式部署
#     - 同样使用 BGE 嵌入模型，向量化逻辑与 C8 一致
#   Collection 的生命周期管理（创建/加载/释放/删除）是 Milvus 工程化的重要知识点。
# =============================================================
"""
Milvus索引构建模块
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set

from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
import numpy as np

from .text_safety import sanitize_query_text

logger = logging.getLogger(__name__)

class MilvusIndexConstructionModule:
    """Milvus索引构建模块 - 负责向量化和Milvus索引构建"""

    def __init__(self, 
                 host: str = "localhost", 
                 port: int = 19530,
                 collection_name: str = "legal_knowledge",
                 dimension: int = 512,
                 model_name: str = "BAAI/bge-small-zh-v1.5"):
        """
        初始化Milvus索引构建模块

        Args:
            host: Milvus服务器地址
            port: Milvus服务器端口
            collection_name: 集合名称
            dimension: 向量维度
            model_name: 嵌入模型名称
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.dimension = dimension
        self.model_name = model_name
        
        self.client = None
        self.embeddings = None
        self.collection_created = False
        
        self._setup_client()
        self._setup_embeddings()
    
    def _safe_truncate(self, text: str, max_length: int) -> str:
        """
        安全截取字符串，处理None值
        
        Args:
            text: 输入文本
            max_length: 最大长度
            
        Returns:
            截取后的字符串
        """
        if text is None:
            return ""
        return str(text)[:max_length]
    
    def _setup_client(self):
        """初始化Milvus客户端"""
        try:
            self.client = MilvusClient(
                uri=f"http://{self.host}:{self.port}"
            )
            logger.info(f"已连接到Milvus服务器: {self.host}:{self.port}")
            
            # 测试连接
            collections = self.client.list_collections()
            logger.info(f"连接成功，当前集合: {collections}")
            
        except Exception as e:
            logger.error(f"连接Milvus失败: {e}")
            raise
    
    def _setup_embeddings(self):
        """初始化嵌入模型"""
        logger.info(f"正在初始化嵌入模型: {self.model_name}")
        
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        logger.info("嵌入模型初始化完成")

    def _get_collection_field_names(self) -> Optional[Set[str]]:
        try:
            desc = self.client.describe_collection(self.collection_name)
        except Exception as exc:
            logger.warning("获取集合字段失败，过滤兼容模式降级: %s", exc)
            return None

        fields = []
        if isinstance(desc, dict):
            if isinstance(desc.get("fields"), list):
                fields = desc.get("fields", [])
            elif isinstance(desc.get("schema"), dict) and isinstance(desc["schema"].get("fields"), list):
                fields = desc["schema"]["fields"]

        names = set()
        for field in fields:
            if isinstance(field, dict) and field.get("name"):
                names.add(str(field["name"]))
        return names or None
    
    def _create_collection_schema(self) -> CollectionSchema:
        """
        创建集合模式
        
        Returns:
            集合模式对象
        """
        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=150, is_primary=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.dimension),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=15000),
            FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="law_name", dtype=DataType.VARCHAR, max_length=300),
            FieldSchema(name="article_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="article_title", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="node_type", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="legal_domain", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="citation_count", dtype=DataType.INT64),
            FieldSchema(name="relation_count", dtype=DataType.INT64),
            FieldSchema(name="risk_scenarios", dtype=DataType.VARCHAR, max_length=1000),
            FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=50),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=150),
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=100)
        ]
        
        # 创建集合模式
        schema = CollectionSchema(
            fields=fields,
            description="法律法规图谱向量集合"
        )
        
        return schema
    
    def create_collection(self, force_recreate: bool = False) -> bool:
        """
        创建Milvus集合
        
        Args:
            force_recreate: 是否强制重新创建集合
        
        Returns:
            是否创建成功
        """
        try:
            # 检查集合是否存在
            if self.client.has_collection(self.collection_name):
                if force_recreate:
                    logger.info(f"删除已存在的集合: {self.collection_name}")
                    self.client.drop_collection(self.collection_name)
                else:
                    logger.info(f"集合 {self.collection_name} 已存在")
                    self.collection_created = True
                    return True
            
            # 创建集合
            schema = self._create_collection_schema()
            
            self.client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                metric_type="COSINE",  # 使用余弦相似度
                consistency_level="Strong"
            )
            
            logger.info(f"成功创建集合: {self.collection_name}")
            self.collection_created = True
            
            return True
            
        except Exception as e:
            logger.error(f"创建集合失败: {e}")
            return False
    
    def create_index(self) -> bool:
        """
        创建向量索引
        
        Returns:
            是否创建成功
        """
        try:
            if not self.collection_created:
                raise ValueError("请先创建集合")
            
            # 使用prepare_index_params创建正确的IndexParams对象
            index_params = self.client.prepare_index_params()
            
            # 添加向量字段索引
            index_params.add_index(
                field_name="vector",
                index_type="HNSW",
                metric_type="COSINE",
                params={
                    "M": 16,
                    "efConstruction": 200
                }
            )
            
            self.client.create_index(
                collection_name=self.collection_name,
                index_params=index_params
            )
            
            logger.info("向量索引创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            return False
    
    def build_vector_index(self, chunks: List[Document]) -> bool:
        """
        构建向量索引
        
        Args:
            chunks: 文档块列表
            
        Returns:
            是否构建成功
        """
        logger.info(f"正在构建Milvus向量索引，文档数量: {len(chunks)}...")
        
        if not chunks:
            raise ValueError("文档块列表不能为空")
        
        try:
            # 1. 创建集合（如果schema不兼容则强制重新创建）
            if not self.create_collection(force_recreate=True):
                return False
            
            # 2. 准备数据
            logger.info("正在生成向量embeddings...")
            texts = [chunk.page_content for chunk in chunks]
            vectors = self.embeddings.embed_documents(texts)
            
            # 3. 准备插入数据
            entities = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                entity = {
                    "id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "vector": vector,
                    "text": self._safe_truncate(chunk.page_content, 15000),
                    "node_id": self._safe_truncate(chunk.metadata.get("node_id", ""), 100),
                    "law_name": self._safe_truncate(
                        chunk.metadata.get("law_name", chunk.metadata.get("recipe_name", "")), 300
                    ),
                    "article_id": self._safe_truncate(chunk.metadata.get("article_id", ""), 100),
                    "article_title": self._safe_truncate(chunk.metadata.get("article_title", ""), 500),
                    "node_type": self._safe_truncate(chunk.metadata.get("node_type", ""), 100),
                    "legal_domain": self._safe_truncate(
                        chunk.metadata.get("legal_domain", chunk.metadata.get("category", "")), 200
                    ),
                    "citation_count": int(chunk.metadata.get("citation_count", 0)),
                    "relation_count": int(chunk.metadata.get("relation_count", 0)),
                    "risk_scenarios": self._safe_truncate(
                        ",".join(chunk.metadata.get("risk_scenarios", []))
                        if isinstance(chunk.metadata.get("risk_scenarios", []), list)
                        else str(chunk.metadata.get("risk_scenarios", "")),
                        1000,
                    ),
                    "doc_type": self._safe_truncate(chunk.metadata.get("doc_type", ""), 50),
                    "chunk_id": self._safe_truncate(chunk.metadata.get("chunk_id", f"chunk_{i}"), 150),
                    "parent_id": self._safe_truncate(chunk.metadata.get("parent_id", ""), 100)
                }
                entities.append(entity)
            
            # 4. 批量插入数据
            logger.info("正在插入向量数据...")
            batch_size = 100
            for i in range(0, len(entities), batch_size):
                batch = entities[i:i + batch_size]
                self.client.insert(
                    collection_name=self.collection_name,
                    data=batch
                )
                logger.info(f"已插入 {min(i + batch_size, len(entities))}/{len(entities)} 条数据")
            
            # 5. 创建索引
            if not self.create_index():
                return False
            
            # 6. 加载集合到内存
            self.client.load_collection(self.collection_name)
            logger.info("集合已加载到内存")
            
            # 7. 等待索引构建完成
            logger.info("等待索引构建完成...")
            time.sleep(2)
            
            logger.info(f"向量索引构建完成，包含 {len(chunks)} 个向量")
            return True
            
        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False
    
    def add_documents(self, new_chunks: List[Document]) -> bool:
        """
        向现有索引添加新文档
        
        Args:
            new_chunks: 新的文档块列表
            
        Returns:
            是否添加成功
        """
        if not self.collection_created:
            raise ValueError("请先构建向量索引")
        
        logger.info(f"正在添加 {len(new_chunks)} 个新文档到索引...")
        
        try:
            # 生成向量
            texts = [chunk.page_content for chunk in new_chunks]
            vectors = self.embeddings.embed_documents(texts)
            
            # 准备插入数据
            entities = []
            for i, (chunk, vector) in enumerate(zip(new_chunks, vectors)):
                entity = {
                    "id": self._safe_truncate(chunk.metadata.get("chunk_id", f"new_chunk_{i}_{int(time.time())}"), 150),
                    "vector": vector,
                    "text": self._safe_truncate(chunk.page_content, 15000),
                    "node_id": self._safe_truncate(chunk.metadata.get("node_id", ""), 100),
                    "law_name": self._safe_truncate(
                        chunk.metadata.get("law_name", chunk.metadata.get("recipe_name", "")), 300
                    ),
                    "article_id": self._safe_truncate(chunk.metadata.get("article_id", ""), 100),
                    "article_title": self._safe_truncate(chunk.metadata.get("article_title", ""), 500),
                    "node_type": self._safe_truncate(chunk.metadata.get("node_type", ""), 100),
                    "legal_domain": self._safe_truncate(
                        chunk.metadata.get("legal_domain", chunk.metadata.get("category", "")), 200
                    ),
                    "citation_count": int(chunk.metadata.get("citation_count", 0)),
                    "relation_count": int(chunk.metadata.get("relation_count", 0)),
                    "risk_scenarios": self._safe_truncate(
                        ",".join(chunk.metadata.get("risk_scenarios", []))
                        if isinstance(chunk.metadata.get("risk_scenarios", []), list)
                        else str(chunk.metadata.get("risk_scenarios", "")),
                        1000,
                    ),
                    "doc_type": self._safe_truncate(chunk.metadata.get("doc_type", ""), 50),
                    "chunk_id": self._safe_truncate(chunk.metadata.get("chunk_id", f"new_chunk_{i}_{int(time.time())}"), 150),
                    "parent_id": self._safe_truncate(chunk.metadata.get("parent_id", ""), 100)
                }
                entities.append(entity)
            
            # 插入数据
            self.client.insert(
                collection_name=self.collection_name,
                data=entities
            )
            
            logger.info("新文档添加完成")
            return True
            
        except Exception as e:
            logger.error(f"添加新文档失败: {e}")
            return False
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        _allow_recover: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        相似度搜索
        
        Args:
            query: 查询文本
            k: 返回结果数量
            filters: 过滤条件
            
        Returns:
            搜索结果列表
        """
        if not self.collection_created:
            logger.warning("Milvus集合未标记为已加载，尝试自动加载: %s", self.collection_name)
            if not self.load_collection():
                logger.warning("Milvus集合自动加载失败，跳过向量检索并返回空结果")
                return []
        
        try:
            query = sanitize_query_text(query)
            if not query:
                logger.warning("相似度搜索收到空查询（可能由非法字符清洗后为空），返回空结果")
                return []

            # 生成查询向量
            query_vector = self.embeddings.embed_query(query)
            
            available_fields = self._get_collection_field_names()

            # 构建过滤表达式
            filter_expr = ""
            if filters:
                filter_conditions = []
                for key, value in filters.items():
                    if available_fields is not None and key not in available_fields:
                        logger.info("跳过不存在的Milvus过滤字段: %s", key)
                        continue
                    if isinstance(value, str):
                        filter_conditions.append(f'{key} == "{value}"')
                    elif isinstance(value, (int, float)):
                        filter_conditions.append(f'{key} == {value}')
                    elif isinstance(value, list):
                        # 支持IN操作
                        if all(isinstance(v, str) for v in value):
                            value_str = '", "'.join(value)
                            filter_conditions.append(f'{key} in ["{value_str}"]')
                        else:
                            value_str = ', '.join(map(str, value))
                            filter_conditions.append(f'{key} in [{value_str}]')
                
                if filter_conditions:
                    filter_expr = " and ".join(filter_conditions)
            
            # 执行搜索 - 保证 ef >= k，避免 Milvus 抛出参数越界错误
            limit_k = max(1, int(k))
            search_ef = max(64, limit_k)
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": search_ef}
            }
            
            # 构建搜索参数，避免重复传递
            base_output_fields = [
                "text",
                "node_id",
                "node_type",
                "law_name",
                "article_id",
                "article_title",
                "legal_domain",
                "citation_count",
                "relation_count",
                "risk_scenarios",
                "doc_type",
                "chunk_id",
                "parent_id",
                "chat_id",
                "file_id",
            ]
            if available_fields is None:
                output_fields = [
                    "text",
                    "node_id",
                    "node_type",
                    "law_name",
                    "article_id",
                    "article_title",
                    "legal_domain",
                    "citation_count",
                    "relation_count",
                    "risk_scenarios",
                    "doc_type",
                    "chunk_id",
                    "parent_id",
                ]
            else:
                output_fields = [name for name in base_output_fields if name in available_fields]

            search_kwargs = {
                "collection_name": self.collection_name,
                "data": [query_vector],
                "anns_field": "vector",
                "limit": limit_k,
                "output_fields": output_fields,
                "search_params": search_params
            }
            
            # 只在有过滤条件时添加filter参数
            if filter_expr:
                search_kwargs["filter"] = filter_expr
                
            results = self.client.search(**search_kwargs)
            
            # 处理结果
            formatted_results = []
            if results and len(results) > 0:
                for hit in results[0]:  # results[0]因为我们只发送了一个查询向量
                    entity = hit.get("entity", {}) if isinstance(hit, dict) else {}
                    result = {
                        "id": hit["id"],
                        "score": hit["distance"],  # 注意：在COSINE距离中，值越大相似度越高
                        "text": entity.get("text", ""),
                        "metadata": {
                            "node_id": entity.get("node_id", ""),
                            "law_name": entity.get("law_name", ""),
                            "article_id": entity.get("article_id", ""),
                            "article_title": entity.get("article_title", ""),
                            "node_type": entity.get("node_type", ""),
                            "legal_domain": entity.get("legal_domain", ""),
                            "citation_count": entity.get("citation_count", 0),
                            "relation_count": entity.get("relation_count", 0),
                            "risk_scenarios": entity.get("risk_scenarios", ""),
                            "doc_type": entity.get("doc_type", ""),
                            "chunk_id": entity.get("chunk_id", ""),
                            "parent_id": entity.get("parent_id", ""),
                            "chat_id": entity.get("chat_id", ""),
                            "file_id": entity.get("file_id", ""),
                        }
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            if _allow_recover:
                logger.warning("Milvus检索异常，尝试重载集合后重试一次: %s", self.collection_name)
                # 运行期异常时强制重置状态并重载，避免后续请求持续空检索。
                self.collection_created = False
                if self.load_collection():
                    return self.similarity_search(
                        query=query,
                        k=k,
                        filters=filters,
                        _allow_recover=False,
                    )
                logger.warning("Milvus重载失败，自动恢复结束并返回空结果: %s", self.collection_name)
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Returns:
            统计信息字典
        """
        try:
            if not self.collection_created:
                return {"error": "集合未创建"}
            
            stats = self.client.get_collection_stats(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "row_count": stats.get("row_count", 0),
                "index_building_progress": stats.get("index_building_progress", 0),
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"获取集合统计信息失败: {e}")
            return {"error": str(e)}
    
    def delete_collection(self) -> bool:
        """
        删除集合
        
        Returns:
            是否删除成功
        """
        try:
            if self.client.has_collection(self.collection_name):
                self.client.drop_collection(self.collection_name)
                logger.info(f"集合 {self.collection_name} 已删除")
                self.collection_created = False
                return True
            else:
                logger.info(f"集合 {self.collection_name} 不存在")
                return True
                
        except Exception as e:
            logger.error(f"删除集合失败: {e}")
            return False
    
    def has_collection(self) -> bool:
        """
        检查集合是否存在
        
        Returns:
            集合是否存在
        """
        try:
            return self.client.has_collection(self.collection_name)
        except Exception as e:
            logger.error(f"检查集合存在性失败: {e}")
            return False
    
    def load_collection(self) -> bool:
        """
        加载集合到内存
        
        Returns:
            是否加载成功
        """
        try:
            if not self.client.has_collection(self.collection_name):
                logger.error(f"集合 {self.collection_name} 不存在")
                return False
            
            self.client.load_collection(self.collection_name)
            self.collection_created = True
            logger.info(f"集合 {self.collection_name} 已加载到内存")
            return True
            
        except Exception as e:
            logger.error(f"加载集合失败: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if hasattr(self, 'client') and self.client:
            # Milvus客户端不需要显式关闭
            logger.info("Milvus连接已关闭")
    
    def __del__(self):
        """析构函数"""
        self.close() 
