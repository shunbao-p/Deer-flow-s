"""
查询意图模板：将自然语言问题转成结构化检索意图。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .text_safety import sanitize_query_text

logger = logging.getLogger(__name__)


QUESTION_TYPE_HINTS = {
    "处罚": ["处罚", "判刑", "量刑", "怎么判", "刑期", "罚款", "惩罚"],
    "依据": ["依据", "根据", "法条", "条款", "参照", "引用"],
    "程序": ["程序", "流程", "步骤", "立案", "起诉", "举证", "申诉", "复议"],
    "责任": ["责任", "赔偿", "承担", "后果", "连带", "赔付"],
}

LEGAL_DOMAIN_HINTS = {
    "刑法": ["刑法", "犯罪", "判刑", "量刑", "故意", "过失", "正当防卫", "未成年人犯罪"],
    "民法": ["民法典", "侵权", "合同", "违约", "损害赔偿", "民事责任"],
    "劳动法": ["劳动法", "劳动合同法", "试用期", "辞退", "社保", "工资", "工伤"],
    "数据合规": ["个人信息保护法", "数据安全法", "隐私", "数据处理", "网络安全法"],
}

COMMON_LAWS = [
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
]

ACTION_HINTS = [
    "伤害",
    "盗窃",
    "诈骗",
    "量刑",
    "定罪",
    "取保候审",
    "拖欠工资",
    "辞退",
    "泄露信息",
    "侵权",
    "违约",
    "正当防卫",
    "紧急避险",
    "非法经营罪",
    "帮助信息网络犯罪活动罪",
    "劳动争议",
    "故意伤害",
]

FALLBACK_TOPIC_TERMS = [
    "劳动争议",
    "非法经营罪",
    "帮助信息网络犯罪活动罪",
    "取保候审",
    "正当防卫",
    "紧急避险",
    "未成年人犯罪",
    "故意伤害",
    "拖欠工资",
    "辞退",
]


@dataclass
class QueryIntent:
    question_type: str = "依据"
    legal_domain: str = "通用"
    subject: str = ""
    action: str = ""
    law_candidates: List[str] = field(default_factory=list)
    article_candidates: List[str] = field(default_factory=list)
    must_terms: List[str] = field(default_factory=list)
    exclude_terms: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "question_type": self.question_type,
            "legal_domain": self.legal_domain,
            "subject": self.subject,
            "action": self.action,
            "law_candidates": list(self.law_candidates),
            "article_candidates": list(self.article_candidates),
            "must_terms": list(self.must_terms),
            "exclude_terms": list(self.exclude_terms),
        }


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _dedup_terms(terms: Any, max_len: int = 10) -> List[str]:
    if terms is None:
        return []
    if isinstance(terms, str):
        source_terms = [terms]
    elif isinstance(terms, (list, tuple, set)):
        source_terms = list(terms)
    else:
        source_terms = [terms]

    output: List[str] = []
    seen = set()
    for term in source_terms:
        normalized = sanitize_query_text(str(term or "")).strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if len(output) >= max_len:
            break
    return output


def _extract_laws(query: str) -> List[str]:
    laws: List[str] = []
    quoted = re.findall(r"《([^》]{2,40})》", query)
    laws.extend(quoted)
    for law in COMMON_LAWS:
        if law in query:
            laws.append(law)
    return _dedup_terms(laws, max_len=6)


def _extract_articles(query: str) -> List[str]:
    return _dedup_terms(
        re.findall(r"第[0-9一二三四五六七八九十百千万〇零两]+条", query),
        max_len=6,
    )


def _guess_question_type(query: str) -> str:
    for qtype, hints in QUESTION_TYPE_HINTS.items():
        if any(h in query for h in hints):
            return qtype
    return "依据"


def _guess_legal_domain(query: str) -> str:
    for domain, hints in LEGAL_DOMAIN_HINTS.items():
        if any(h in query for h in hints):
            return domain
    return "通用"


def _guess_action(query: str) -> str:
    matched = [action for action in ACTION_HINTS if action in query]
    if matched:
        matched.sort(key=len, reverse=True)
        return matched[0]
    return ""


def _extract_subject(query: str) -> str:
    people = ["未成年人", "孩童", "劳动者", "用人单位", "公司", "个人", "员工", "雇主"]
    for item in people:
        if item in query:
            return "未成年人" if item in {"孩童"} else item
    return ""


def _fallback_must_terms_from_query(query: str) -> List[str]:
    query = sanitize_query_text(query)
    if not query:
        return []

    strong_candidates: List[str] = []
    strong_candidates.extend(_extract_laws(query))
    strong_candidates.extend(_extract_articles(query))
    strong_candidates.extend(re.findall(r"[一-龥]{2,30}罪", query))

    for term in FALLBACK_TOPIC_TERMS:
        if term in query:
            strong_candidates.append(term)

    cleaned = query
    stop_patterns = [
        "请问",
        "对于",
        "关于",
        "如何",
        "怎么",
        "怎样",
        "是什么",
        "怎么办",
        "依据",
        "处理办法",
        "处理",
        "处罚",
        "量刑",
        "认定",
        "规定",
        "吗",
        "呢",
        "的",
    ]
    for pat in stop_patterns:
        cleaned = cleaned.replace(pat, " ")
    chunks = [x.strip() for x in re.split(r"[^一-龥0-9A-Za-z]+", cleaned) if x.strip()]

    # 优先使用“高置信实体词”，避免把复合短语并入 must_terms 触发保守化。
    primary_terms = _dedup_terms(strong_candidates, max_len=6)
    if primary_terms:
        return primary_terms
    # 仅在完全没有高置信词时才回退到切分短语兜底。
    chunk_terms = [x for x in chunks if 2 <= len(x) <= 12][:2]
    return _dedup_terms(chunk_terms, max_len=2)


def rule_based_parse_query_intent(query: str) -> QueryIntent:
    query = sanitize_query_text(query)
    if not query:
        return QueryIntent()

    laws = _extract_laws(query)
    articles = _extract_articles(query)
    qtype = _guess_question_type(query)
    domain = _guess_legal_domain(query)
    action = _guess_action(query)
    subject = _extract_subject(query)

    base_terms = _dedup_terms(laws + articles + ([action] if action else []), max_len=6)
    must_terms = base_terms if base_terms else _fallback_must_terms_from_query(query)
    if not must_terms:
        must_terms = _dedup_terms([query[:8]], max_len=1)

    return QueryIntent(
        question_type=qtype,
        legal_domain=domain,
        subject=subject,
        action=action,
        law_candidates=laws,
        article_candidates=articles,
        must_terms=must_terms,
        exclude_terms=[],
    )


def parse_query_intent(
    query: str,
    llm_dispatcher: Optional[object] = None,
    llm_client: Optional[object] = None,
    model_name: str = "",
    max_tokens: int = 500,
) -> QueryIntent:
    query = sanitize_query_text(query)
    if not query:
        return QueryIntent()

    prompt = f"""
你是法律检索意图解析器。请把用户问题转成JSON槽位，不要输出其他文字。

问题：{query}

JSON格式：
{{
  "question_type": "处罚|依据|程序|责任",
  "legal_domain": "刑法|民法|劳动法|数据合规|通用",
  "subject": "主体（可空）",
  "action": "行为（可空）",
  "law_candidates": ["法规名"],
  "article_candidates": ["第XX条"],
  "must_terms": ["必须命中词"],
  "exclude_terms": ["排除词"]
}}

要求：
1. must_terms尽量具体，避免大类词。
2. law_candidates/article_candidates尽量从问题中抽取，不编造。
3. 字段缺失时给空字符串或空数组。
"""

    try:
        response = None
        if llm_dispatcher is not None:
            response, provider, model = llm_dispatcher.create_chat_completion(
                role="assist",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            logger.info("辅助调用通道(意图模板): provider=%s model=%s", provider, model)
        elif llm_client is not None:
            response = llm_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )

        if response is None:
            return rule_based_parse_query_intent(query)

        payload = _safe_json_loads(response.choices[0].message.content.strip())
        intent = QueryIntent(
            question_type=str(payload.get("question_type", "")) or _guess_question_type(query),
            legal_domain=str(payload.get("legal_domain", "")) or _guess_legal_domain(query),
            subject=str(payload.get("subject", "")),
            action=str(payload.get("action", "")),
            law_candidates=_dedup_terms(payload.get("law_candidates", []), max_len=6),
            article_candidates=_dedup_terms(payload.get("article_candidates", []), max_len=6),
            must_terms=_dedup_terms(payload.get("must_terms", []), max_len=10),
            exclude_terms=_dedup_terms(payload.get("exclude_terms", []), max_len=8),
        )
        if not intent.must_terms:
            fallback = rule_based_parse_query_intent(query)
            intent.must_terms = fallback.must_terms
        return intent
    except Exception as e:
        logger.warning("意图模板解析失败，使用规则降级: %s", e)
        return rule_based_parse_query_intent(query)


def intent_to_keywords(intent: QueryIntent, query: str) -> Dict[str, List[str]]:
    query = sanitize_query_text(query)
    if not query:
        return {"entity_keywords": [], "topic_keywords": []}

    entity_keywords = _dedup_terms(
        intent.law_candidates + intent.article_candidates + ([intent.subject] if intent.subject else []),
        max_len=6,
    )
    topic_seed = [intent.legal_domain, intent.question_type, intent.action]
    topic_keywords = _dedup_terms([x for x in topic_seed if x and x != "通用"], max_len=6)

    if not entity_keywords:
        fallback = _extract_articles(query) + _extract_laws(query)
        if not fallback:
            fallback = [query[:12]]
        entity_keywords = _dedup_terms(fallback, max_len=5)
    if not topic_keywords:
        topic_keywords = _dedup_terms([intent.question_type, intent.action, query[:12]], max_len=5)

    return {
        "entity_keywords": entity_keywords,
        "topic_keywords": topic_keywords,
    }
