# =============================================================
# 文件介绍：图数据准备模块（GraphDataPreparationModule）
# 目标：从 Neo4j 读取法律法规图谱，构建可供检索的结构化文档。
# =============================================================
"""
图数据库数据准备模块（法律场景）
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass

from neo4j import GraphDatabase
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """图节点数据结构"""

    node_id: str
    labels: List[str]
    name: str
    properties: Dict[str, Any]


@dataclass
class GraphRelation:
    """图关系数据结构"""

    start_node_id: str
    end_node_id: str
    relation_type: str
    properties: Dict[str, Any]


class GraphDataPreparationModule:
    """图数据库数据准备模块 - 从 Neo4j 读取法律图数据并转换为文档"""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = None

        self.documents: List[Document] = []
        self.chunks: List[Document] = []

        # 法律领域核心集合
        self.law_documents: List[GraphNode] = []
        self.articles: List[GraphNode] = []
        self.compliance_steps: List[GraphNode] = []
        self.risk_scenarios: List[GraphNode] = []

        # 向后兼容（供现有模块过渡）
        self.recipes: List[GraphNode] = self.law_documents
        self.ingredients: List[GraphNode] = self.articles
        self.cooking_steps: List[GraphNode] = self.compliance_steps

        self._connect()

    def _connect(self):
        """建立 Neo4j 连接"""
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            logger.info(f"已连接到Neo4j数据库: {self.uri}")

            with self.driver.session(database=self.database) as session:
                if session.run("RETURN 1 AS test").single():
                    logger.info("Neo4j连接测试成功")
        except Exception as e:
            logger.error(f"连接Neo4j失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, "driver") and self.driver:
            self.driver.close()
            logger.info("Neo4j连接已关闭")

    def _load_nodes(self, label: str, order_field: str = "nodeId") -> List[GraphNode]:
        """按标签读取节点，若无 nodeId 则回退到 elementId。"""
        query = f"""
        MATCH (n:{label})
        RETURN
            COALESCE(toString(n.nodeId), elementId(n)) AS nodeId,
            labels(n) AS labels,
            COALESCE(n.name, n.title, n.articleId, '{label}') AS name,
            properties(n) AS properties
        ORDER BY COALESCE(toString(n.{order_field}), toString(n.nodeId), elementId(n))
        """

        nodes: List[GraphNode] = []
        with self.driver.session(database=self.database) as session:
            for record in session.run(query):
                nodes.append(
                    GraphNode(
                        node_id=record["nodeId"],
                        labels=record["labels"],
                        name=record["name"],
                        properties=dict(record["properties"]),
                    )
                )
        return nodes

    def load_graph_data(self) -> Dict[str, Any]:
        """从 Neo4j 加载法律图数据。"""
        logger.info("正在从Neo4j加载法律图数据...")

        self.law_documents = self._load_nodes("LawDocument")
        self.articles = self._load_nodes("Article", order_field="articleId")
        self.compliance_steps = self._load_nodes("ComplianceStep")
        self.risk_scenarios = self._load_nodes("RiskScenario")

        # 兼容旧模块字段名
        self.recipes = self.law_documents
        self.ingredients = self.articles
        self.cooking_steps = self.compliance_steps

        logger.info(
            "法律图数据加载完成：law_documents=%s, articles=%s, risk_scenarios=%s, compliance_steps=%s",
            len(self.law_documents),
            len(self.articles),
            len(self.risk_scenarios),
            len(self.compliance_steps),
        )

        return {
            "law_documents": len(self.law_documents),
            "articles": len(self.articles),
            "risk_scenarios": len(self.risk_scenarios),
            "compliance_steps": len(self.compliance_steps),
            # 兼容旧统计键
            "recipes": len(self.law_documents),
            "ingredients": len(self.articles),
            "cooking_steps": len(self.compliance_steps),
        }

    def build_legal_documents(self) -> List[Document]:
        """构建法规条文文档，集成法规、领域、引用关系、风险场景信息。"""
        logger.info("正在构建法律法规文档...")
        documents: List[Document] = []

        article_detail_query = """
        MATCH (a:Article)
        WHERE COALESCE(toString(a.nodeId), elementId(a)) = $article_node_id

        OPTIONAL MATCH (law:LawDocument)-[:HAS_ARTICLE]->(a)
        OPTIONAL MATCH (a)-[:BELONGS_TO_DOMAIN]->(domain:LegalDomain)
        OPTIONAL MATCH (a)-[:CITES]->(cited:Article)
        OPTIONAL MATCH (a)-[:RELATES_TO]->(related:Article)
        OPTIONAL MATCH (a)-[:APPLIES_TO]->(risk:RiskScenario)

        RETURN
            law,
            a,
            collect(DISTINCT domain.name) AS domains,
            collect(DISTINCT cited.articleId) AS cited_article_ids,
            collect(DISTINCT related.articleId) AS related_article_ids,
            collect(DISTINCT risk.name) AS risk_scenarios
        """

        with self.driver.session(database=self.database) as session:
            for article in self.articles:
                try:
                    result = session.run(
                        article_detail_query,
                        {"article_node_id": article.node_id},
                    ).single()
                    if not result:
                        continue

                    law = result.get("law")
                    article_node = result.get("a")
                    domains = [d for d in result.get("domains", []) if d]
                    cited_article_ids = [x for x in result.get("cited_article_ids", []) if x]
                    related_article_ids = [x for x in result.get("related_article_ids", []) if x]
                    risk_scenarios = [x for x in result.get("risk_scenarios", []) if x]

                    law_name = (
                        law.get("name") if law else article.properties.get("lawName", "未知法规")
                    )
                    law_id = (
                        str(law.get("nodeId"))
                        if law and law.get("nodeId") is not None
                        else article.properties.get("lawId", "")
                    )
                    article_id = (
                        article_node.get("articleId")
                        if article_node and article_node.get("articleId")
                        else article.properties.get("articleId", article.node_id)
                    )
                    article_title = (
                        article_node.get("title")
                        if article_node and article_node.get("title")
                        else article.properties.get("title", article.name)
                    )
                    article_content = (
                        article_node.get("content")
                        if article_node and article_node.get("content")
                        else article.properties.get("content", "")
                    )

                    content_parts = [f"# {law_name} {article_id}"]
                    if article_title:
                        content_parts.append(f"\n## 条文标题\n{article_title}")
                    if article_content:
                        content_parts.append(f"\n## 条文内容\n{article_content}")
                    if domains:
                        content_parts.append(f"\n## 所属领域\n{', '.join(domains)}")
                    if cited_article_ids:
                        content_parts.append(f"\n## 引用条款\n{', '.join(cited_article_ids)}")
                    if related_article_ids:
                        content_parts.append(f"\n## 关联条款\n{', '.join(related_article_ids)}")
                    if risk_scenarios:
                        content_parts.append(f"\n## 适用风险场景\n{', '.join(risk_scenarios)}")

                    full_content = "\n".join(content_parts).strip()
                    metadata = {
                        "node_id": article.node_id,
                        "node_type": "Article",
                        "doc_type": "legal_article",
                        "law_id": str(law_id) if law_id is not None else "",
                        "law_name": law_name,
                        "article_id": str(article_id) if article_id is not None else "",
                        "article_title": article_title,
                        "legal_domain": ", ".join(domains) if domains else "未分类",
                        "citation_count": len(cited_article_ids),
                        "relation_count": len(related_article_ids),
                        "risk_scenarios": risk_scenarios,
                        "content_length": len(full_content),
                    }

                    documents.append(Document(page_content=full_content, metadata=metadata))

                except Exception as e:
                    logger.warning("构建法律文档失败 article=%s, error=%s", article.node_id, e)

        self.documents = documents
        logger.info("成功构建 %s 个法律文档", len(documents))
        return documents

    def build_recipe_documents(self) -> List[Document]:
        """兼容旧调用：统一走法律文档构建。"""
        return self.build_legal_documents()

    def chunk_documents(self, chunk_size: int = 500, chunk_overlap: int = 50) -> List[Document]:
        """对文档进行分块处理。"""
        logger.info(f"正在进行文档分块，块大小: {chunk_size}, 重叠: {chunk_overlap}")
        if not self.documents:
            raise ValueError("请先构建文档")

        chunks: List[Document] = []
        chunk_id = 0
        for doc in self.documents:
            content = doc.page_content
            if len(content) <= chunk_size:
                chunks.append(
                    Document(
                        page_content=content,
                        metadata={
                            **doc.metadata,
                            "chunk_id": f"{doc.metadata['node_id']}_chunk_{chunk_id}",
                            "parent_id": doc.metadata["node_id"],
                            "chunk_index": 0,
                            "total_chunks": 1,
                            "chunk_size": len(content),
                            "doc_type": "chunk",
                        },
                    )
                )
                chunk_id += 1
                continue

            sections = content.split("\n## ")
            if len(sections) <= 1:
                total_chunks = (len(content) - 1) // (chunk_size - chunk_overlap) + 1
                for i in range(total_chunks):
                    start = i * (chunk_size - chunk_overlap)
                    end = min(start + chunk_size, len(content))
                    chunk_content = content[start:end]
                    chunks.append(
                        Document(
                            page_content=chunk_content,
                            metadata={
                                **doc.metadata,
                                "chunk_id": f"{doc.metadata['node_id']}_chunk_{chunk_id}",
                                "parent_id": doc.metadata["node_id"],
                                "chunk_index": i,
                                "total_chunks": total_chunks,
                                "chunk_size": len(chunk_content),
                                "doc_type": "chunk",
                            },
                        )
                    )
                    chunk_id += 1
                continue

            total_chunks = len(sections)
            for i, section in enumerate(sections):
                chunk_content = section if i == 0 else f"## {section}"
                chunks.append(
                    Document(
                        page_content=chunk_content,
                        metadata={
                            **doc.metadata,
                            "chunk_id": f"{doc.metadata['node_id']}_chunk_{chunk_id}",
                            "parent_id": doc.metadata["node_id"],
                            "chunk_index": i,
                            "total_chunks": total_chunks,
                            "chunk_size": len(chunk_content),
                            "doc_type": "chunk",
                            "section_title": section.split("\n")[0] if i > 0 else "主标题",
                        },
                    )
                )
                chunk_id += 1

        self.chunks = chunks
        logger.info(f"文档分块完成，共生成 {len(chunks)} 个块")
        return chunks

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息。"""
        stats = {
            "total_law_documents": len(self.law_documents),
            "total_articles": len(self.articles),
            "total_risk_scenarios": len(self.risk_scenarios),
            "total_compliance_steps": len(self.compliance_steps),
            "total_documents": len(self.documents),
            "total_chunks": len(self.chunks),
            # 兼容旧字段名
            "total_recipes": len(self.law_documents),
            "total_ingredients": len(self.articles),
            "total_cooking_steps": len(self.compliance_steps),
        }

        if not self.documents:
            return stats

        legal_domains: Dict[str, int] = {}
        for doc in self.documents:
            domain = doc.metadata.get("legal_domain", "未分类")
            legal_domains[domain] = legal_domains.get(domain, 0) + 1

        stats.update(
            {
                "legal_domains": legal_domains,
                "avg_content_length": sum(
                    doc.metadata.get("content_length", 0) for doc in self.documents
                )
                / len(self.documents),
                "avg_chunk_size": (
                    sum(chunk.metadata.get("chunk_size", 0) for chunk in self.chunks)
                    / len(self.chunks)
                    if self.chunks
                    else 0
                ),
            }
        )
        return stats

    def __del__(self):
        """析构函数，确保关闭连接"""
        self.close()
