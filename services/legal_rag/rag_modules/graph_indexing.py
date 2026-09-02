# =============================================================
# 文件介绍：图索引模块（GraphIndexing）
# 目标：将法律图谱中的实体和关系构建为 K-V 索引，支撑快速检索。
# =============================================================
"""
法律图索引模块
"""

import json
import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class EntityKeyValue:
    """实体键值对"""

    entity_name: str
    index_keys: List[str]
    value_content: str
    entity_type: str
    metadata: Dict[str, Any]


@dataclass
class RelationKeyValue:
    """关系键值对"""

    relation_id: str
    index_keys: List[str]
    value_content: str
    relation_type: str
    source_entity: str
    target_entity: str
    metadata: Dict[str, Any]


class GraphIndexingModule:
    """法律图索引模块"""

    def __init__(self, config, llm_client, llm_dispatcher: Optional[object] = None):
        self.config = config
        self.llm_client = llm_client
        self.llm_dispatcher = llm_dispatcher

        self.entity_kv_store: Dict[str, EntityKeyValue] = {}
        self.relation_kv_store: Dict[str, RelationKeyValue] = {}
        self.key_to_entities: Dict[str, List[str]] = defaultdict(list)
        self.key_to_relations: Dict[str, List[str]] = defaultdict(list)

    def _assist_chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 200):
        if self.llm_dispatcher is not None:
            response, provider, model = self.llm_dispatcher.create_chat_completion(
                role="assist",
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            logger.info("辅助调用通道(图索引增强): provider=%s model=%s", provider, model)
            return response
        return self.llm_client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )

    def create_entity_key_values(
        self,
        law_documents: List[Any],
        articles: List[Any],
        compliance_steps: List[Any],
        risk_scenarios: List[Any] | None = None,
    ) -> Dict[str, EntityKeyValue]:
        """为法律实体构建键值索引。"""
        self.entity_kv_store.clear()
        self.key_to_entities.clear()
        risk_scenarios = risk_scenarios or []

        self._register_nodes(law_documents, "LawDocument")
        self._register_nodes(articles, "Article")
        self._register_nodes(compliance_steps, "ComplianceStep")
        self._register_nodes(risk_scenarios, "RiskScenario")

        logger.info("实体键值对创建完成，共 %s 个实体", len(self.entity_kv_store))
        return self.entity_kv_store

    def _register_nodes(self, nodes: List[Any], entity_type: str):
        for node in nodes:
            node_id = str(getattr(node, "node_id", ""))
            props = getattr(node, "properties", {}) or {}
            name = str(getattr(node, "name", "") or props.get("name") or node_id)
            if not node_id:
                continue

            index_keys = self._build_entity_keys(name, props, entity_type)
            value_content = self._build_entity_content(name, props, entity_type)

            entity_kv = EntityKeyValue(
                entity_name=name,
                index_keys=index_keys,
                value_content=value_content,
                entity_type=entity_type,
                metadata={"node_id": node_id, "properties": props},
            )
            self.entity_kv_store[node_id] = entity_kv
            for key in index_keys:
                self.key_to_entities[key].append(node_id)

    def _build_entity_keys(self, name: str, props: Dict[str, Any], entity_type: str) -> List[str]:
        keys = {name.strip()}

        aliases = props.get("aliases") or props.get("alias") or []
        if isinstance(aliases, str):
            aliases = [x.strip() for x in aliases.split(",") if x.strip()]
        for alias in aliases:
            keys.add(str(alias).strip())

        if entity_type == "Article":
            article_id = props.get("articleId") or props.get("article_id")
            title = props.get("title")
            if article_id:
                normalized_article_id = self._normalize_article_id(str(article_id))
                keys.add(str(article_id))
                if normalized_article_id:
                    keys.add(normalized_article_id)
            if title:
                keys.add(str(title))

        if entity_type == "LawDocument":
            short_name = props.get("shortName") or props.get("short_name")
            if short_name:
                keys.add(str(short_name))

        if entity_type == "RiskScenario":
            keywords = props.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [x.strip() for x in keywords.split(",") if x.strip()]
            for kw in keywords:
                keys.add(str(kw))

        return [k for k in keys if k]

    def _normalize_article_id(self, raw_article_id: str) -> str:
        """标准化条文编号，避免出现“第第39条条”一类异常键。"""
        text = raw_article_id.strip()
        if not text:
            return ""

        match = re.search(r"([0-9]+)", text)
        if match:
            return f"第{match.group(1)}条"

        # 中文数字兜底：若已含“第...条”结构则直接规范化返回
        if text.startswith("第") and text.endswith("条") and len(text) > 2:
            core = text[1:-1].strip()
            if core:
                return f"第{core}条"

        # 普通尾缀“条”场景
        if text.endswith("条"):
            core = text[:-1].strip()
            if core:
                if core.startswith("第"):
                    core = core[1:].strip()
                return f"第{core}条"

        return f"第{text}条"

    def _build_entity_content(self, name: str, props: Dict[str, Any], entity_type: str) -> str:
        content_parts = [f"实体名称: {name}", f"实体类型: {entity_type}"]
        if entity_type == "LawDocument":
            for field, label in [
                ("docType", "文档类型"),
                ("effectiveDate", "生效日期"),
                ("status", "状态"),
            ]:
                if props.get(field):
                    content_parts.append(f"{label}: {props[field]}")
        elif entity_type == "Article":
            for field, label in [
                ("articleId", "条文编号"),
                ("title", "条文标题"),
                ("content", "条文内容"),
            ]:
                if props.get(field):
                    content_parts.append(f"{label}: {props[field]}")
        elif entity_type == "RiskScenario":
            if props.get("description"):
                content_parts.append(f"场景描述: {props['description']}")
        elif entity_type == "ComplianceStep":
            if props.get("description"):
                content_parts.append(f"步骤描述: {props['description']}")
            if props.get("order") is not None:
                content_parts.append(f"顺序: {props['order']}")
        return "\n".join(content_parts)

    def create_relation_key_values(self, relationships: List[Tuple[str, str, str]]) -> Dict[str, RelationKeyValue]:
        """为关系构建键值索引。"""
        self.relation_kv_store.clear()
        self.key_to_relations.clear()

        for i, (source_id, relation_type, target_id) in enumerate(relationships):
            source_entity = self.entity_kv_store.get(str(source_id))
            target_entity = self.entity_kv_store.get(str(target_id))
            if not source_entity or not target_entity:
                continue

            relation_id = f"rel_{i}_{source_id}_{target_id}"
            index_keys = self._generate_relation_index_keys(source_entity, target_entity, relation_type)
            value_content = (
                f"关系类型: {relation_type}\n"
                f"源实体: {source_entity.entity_name} ({source_entity.entity_type})\n"
                f"目标实体: {target_entity.entity_name} ({target_entity.entity_type})"
            )

            relation_kv = RelationKeyValue(
                relation_id=relation_id,
                index_keys=index_keys,
                value_content=value_content,
                relation_type=relation_type,
                source_entity=str(source_id),
                target_entity=str(target_id),
                metadata={
                    "source_name": source_entity.entity_name,
                    "target_name": target_entity.entity_name,
                },
            )
            self.relation_kv_store[relation_id] = relation_kv
            for key in index_keys:
                self.key_to_relations[key].append(relation_id)

        logger.info("关系键值对创建完成，共 %s 个关系", len(self.relation_kv_store))
        return self.relation_kv_store

    def _generate_relation_index_keys(
        self,
        source_entity: EntityKeyValue,
        target_entity: EntityKeyValue,
        relation_type: str,
    ) -> List[str]:
        keys = {
            relation_type,
            source_entity.entity_name,
            target_entity.entity_name,
            f"{source_entity.entity_name}_{relation_type}",
            f"{target_entity.entity_name}_{relation_type}",
        }

        if relation_type == "CITES":
            keys.add("引用关系")
            keys.add("法条引用")
        elif relation_type == "RELATES_TO":
            keys.add("关联条款")
            keys.add("主题关联")
        elif relation_type == "APPLIES_TO":
            keys.add("风险场景")
            keys.add("适用关系")

        if getattr(self.config, "enable_llm_relation_keys", False):
            keys.update(self._llm_enhance_relation_keys(source_entity, target_entity, relation_type))
        return [k for k in keys if k]

    def _llm_enhance_relation_keys(
        self,
        source_entity: EntityKeyValue,
        target_entity: EntityKeyValue,
        relation_type: str,
    ) -> List[str]:
        prompt = f"""
        你是法律知识图谱索引助手。请基于以下关系生成 3-5 个检索关键词。
        源实体: {source_entity.entity_name} ({source_entity.entity_type})
        目标实体: {target_entity.entity_name} ({target_entity.entity_type})
        关系类型: {relation_type}
        返回 JSON: {{"keywords": ["关键词1", "关键词2"]}}
        """
        try:
            response = self._assist_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            result = json.loads(response.choices[0].message.content.strip())
            return result.get("keywords", [])
        except Exception as e:
            logger.error("LLM增强关系索引键失败: %s", e)
            return []

    def deduplicate_entities_and_relations(self):
        """去重实体和关系，重建键映射。"""
        name_to_entity_ids: Dict[str, List[str]] = defaultdict(list)
        for entity_id, entity in self.entity_kv_store.items():
            name_to_entity_ids[entity.entity_name].append(entity_id)

        entities_to_remove: List[str] = []
        for _, entity_ids in name_to_entity_ids.items():
            if len(entity_ids) <= 1:
                continue
            primary_id = entity_ids[0]
            for duplicate_id in entity_ids[1:]:
                self.entity_kv_store[primary_id].value_content += (
                    f"\n\n补充信息: {self.entity_kv_store[duplicate_id].value_content}"
                )
                entities_to_remove.append(duplicate_id)

        for entity_id in entities_to_remove:
            self.entity_kv_store.pop(entity_id, None)

        relation_signature_to_ids: Dict[str, List[str]] = defaultdict(list)
        for relation_id, relation in self.relation_kv_store.items():
            signature = f"{relation.source_entity}_{relation.target_entity}_{relation.relation_type}"
            relation_signature_to_ids[signature].append(relation_id)

        relations_to_remove: List[str] = []
        for _, relation_ids in relation_signature_to_ids.items():
            relations_to_remove.extend(relation_ids[1:])
        for relation_id in relations_to_remove:
            self.relation_kv_store.pop(relation_id, None)

        self._rebuild_key_mappings()
        logger.info(
            "去重完成 - 删除 %s 个重复实体，%s 个重复关系",
            len(entities_to_remove),
            len(relations_to_remove),
        )

    def _rebuild_key_mappings(self):
        self.key_to_entities.clear()
        self.key_to_relations.clear()
        for entity_id, entity in self.entity_kv_store.items():
            for key in entity.index_keys:
                self.key_to_entities[key].append(entity_id)
        for relation_id, relation in self.relation_kv_store.items():
            for key in relation.index_keys:
                self.key_to_relations[key].append(relation_id)

    def get_entities_by_key(self, key: str) -> List[EntityKeyValue]:
        return [self.entity_kv_store[eid] for eid in self.key_to_entities.get(key, []) if eid in self.entity_kv_store]

    def get_relations_by_key(self, key: str) -> List[RelationKeyValue]:
        return [self.relation_kv_store[rid] for rid in self.key_to_relations.get(key, []) if rid in self.relation_kv_store]

    def search_entities(self, keyword: str, limit: int = 10) -> List[EntityKeyValue]:
        """模糊检索实体键。"""
        if not keyword:
            return []
        keyword_lower = keyword.lower()
        hit_ids: List[str] = []
        for key, entity_ids in self.key_to_entities.items():
            if keyword_lower in key.lower() or key.lower() in keyword_lower:
                hit_ids.extend(entity_ids)
        seen = set()
        results = []
        for entity_id in hit_ids:
            if entity_id in seen or entity_id not in self.entity_kv_store:
                continue
            seen.add(entity_id)
            results.append(self.entity_kv_store[entity_id])
            if len(results) >= limit:
                break
        return results

    def search_relations(self, keyword: str, limit: int = 10) -> List[RelationKeyValue]:
        """模糊检索关系键。"""
        if not keyword:
            return []
        keyword_lower = keyword.lower()
        hit_ids: List[str] = []
        for key, relation_ids in self.key_to_relations.items():
            if keyword_lower in key.lower() or key.lower() in keyword_lower:
                hit_ids.extend(relation_ids)
        seen = set()
        results = []
        for relation_id in hit_ids:
            if relation_id in seen or relation_id not in self.relation_kv_store:
                continue
            seen.add(relation_id)
            results.append(self.relation_kv_store[relation_id])
            if len(results) >= limit:
                break
        return results

    def get_statistics(self) -> Dict[str, Any]:
        entity_type_count: Dict[str, int] = defaultdict(int)
        for kv in self.entity_kv_store.values():
            entity_type_count[kv.entity_type] += 1
        return {
            "total_entities": len(self.entity_kv_store),
            "total_relations": len(self.relation_kv_store),
            "total_entity_keys": sum(len(kv.index_keys) for kv in self.entity_kv_store.values()),
            "total_relation_keys": sum(len(kv.index_keys) for kv in self.relation_kv_store.values()),
            "entity_types": dict(entity_type_count),
        }
