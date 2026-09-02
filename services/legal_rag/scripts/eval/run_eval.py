#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import requests

LAW_ALIAS_MAP = {
    "中华人民共和国刑法": "刑法",
    "刑法": "刑法",
    "中华人民共和国民法典": "民法典",
    "民法典": "民法典",
    "中华人民共和国劳动合同法": "劳动合同法",
    "劳动合同法": "劳动合同法",
    "中华人民共和国未成年人保护法": "未成年人保护法",
    "未成年人保护法": "未成年人保护法",
    "中华人民共和国道路交通安全法": "道路交通安全法",
    "道路交通安全法": "道路交通安全法",
    "中华人民共和国消费者权益保护法": "消费者权益保护法",
    "消费者权益保护法": "消费者权益保护法",
}

PUNCT_PATTERN = re.compile(r"[，。！？、；：“”‘’（）()《》〈〉【】\[\],.!?;:'\"`~@#$%^&*_+=|\\/\-]+")
SPACE_PATTERN = re.compile(r"\s+")
ARTICLE_PATTERN = re.compile(r"第?\s*([0-9零一二三四五六七八九十百千万两〇]+)\s*条")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed-contract RAG evaluation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument(
        "--api-mode",
        choices=["augment", "chat"],
        default="augment",
        help="augment=POST /v1/augment（默认，无会话）；chat=先 /chats 再 /chat（仅对照独立 Legal 源服务）",
    )
    parser.add_argument("--dataset", default="data/eval/eval_questions_v1.jsonl")
    parser.add_argument("--output-dir", default="data/eval/results")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument(
        "--warmup-mode",
        choices=["light", "full"],
        default="light",
        help="warmup模式：light=仅健康检查，full=发送完整评测请求",
    )
    parser.add_argument("--timeout", type=float, default=240.0, help="正式评测请求超时（秒）")
    parser.add_argument("--warmup-timeout", type=float, default=300.0, help="预热请求超时（秒）")
    parser.add_argument("--health-timeout", type=float, default=15.0, help="启动健康检查超时（秒）")
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument(
        "--eval-fast-mode",
        choices=["on", "off"],
        default="off",
        help="评测请求是否启用快速模式（默认off，on=减少额外LLM调用）",
    )
    parser.add_argument(
        "--allow-reranker-not-ready",
        action="store_true",
        help="允许健康检查时 reranker 未就绪（默认不允许）",
    )
    parser.add_argument("--allow-warmup-fail", action="store_true", help="允许预热失败后继续评测")
    parser.add_argument("--eval-batch-id", default="")
    parser.add_argument("--skip-db-validate", action="store_true")
    return parser


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = PUNCT_PATTERN.sub("", text)
    text = SPACE_PATTERN.sub("", text)
    return text


def zh_to_int(value: str) -> int:
    text = value.strip()
    if not text:
        raise ValueError("empty zh number")
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in ZH_DIGIT:
            number = ZH_DIGIT[ch]
            continue
        if ch in ZH_UNIT:
            unit = ZH_UNIT[ch]
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
        raise ValueError(f"unsupported char: {ch}")
    return total + section + number


def normalize_law_name(name: Any) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    if raw in LAW_ALIAS_MAP:
        return LAW_ALIAS_MAP[raw]
    compact = normalize_text(raw)
    for alias, canonical in LAW_ALIAS_MAP.items():
        if normalize_text(alias) == compact:
            return canonical
    return raw


def normalize_article(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = raw.replace(" ", "")
    match = ARTICLE_PATTERN.search(compact)
    if not match:
        digits = re.findall(r"\d+", compact)
        if digits:
            return f"第{int(digits[0])}条"
        return compact
    token = match.group(1)
    try:
        num = zh_to_int(token)
    except Exception:
        digits = re.findall(r"\d+", token)
        if not digits:
            return compact
        num = int(digits[0])
    return f"第{num}条"


def normalize_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        items = re.split(r"[;,，；|]+", text)
    result: list[str] = []
    for item in items:
        norm = normalize_text(item)
        if norm:
            result.append(norm)
    return result


def normalize_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        items = re.split(r"[;,，；|]+", text)
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        v = str(item or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def get_expected_law_primary(row: dict[str, Any]) -> str:
    return str(row.get("expected_law_primary") or row.get("expected_law") or "").strip()


def get_expected_law_acceptable(row: dict[str, Any]) -> list[str]:
    values = normalize_str_list(row.get("expected_law_acceptable", []))
    primary = get_expected_law_primary(row)
    return [v for v in values if v and v != primary]


def get_expected_article_primary(row: dict[str, Any]) -> str:
    return str(row.get("expected_article_primary") or row.get("expected_article") or "").strip()


def get_expected_article_acceptable(row: dict[str, Any]) -> list[str]:
    values = normalize_str_list(row.get("expected_article_acceptable", []))
    primary = get_expected_article_primary(row)
    return [v for v in values if v and v != primary]


def get_expected_article_required_all(row: dict[str, Any]) -> list[str]:
    values = normalize_str_list(row.get("expected_article_required_all", []))
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_law_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        norm = normalize_law_name(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def normalize_article_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        norm = normalize_article(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def parse_law_article_pairs(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        items = [x for x in re.split(r"[;\n]+", text) if str(x).strip()]

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        law = ""
        article = ""
        if isinstance(item, dict):
            law = str(item.get("law") or item.get("law_name") or item.get("expected_law") or "").strip()
            article = str(item.get("article") or item.get("article_id") or item.get("expected_article") or "").strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            law = str(item[0] or "").strip()
            article = str(item[1] or "").strip()
        else:
            raw = str(item or "").strip()
            if "|" in raw:
                left, right = raw.split("|", 1)
                law = left.strip()
                article = right.strip()
        if not law or not article:
            continue
        pair = (law, article)
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def pair_to_jsonable(pair: tuple[str, str] | None) -> dict[str, str] | None:
    if not pair:
        return None
    return {"law": pair[0], "article": pair[1]}


def pairs_to_jsonable(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"law": law, "article": article} for law, article in pairs]


def get_expected_law_article_pair_primary(row: dict[str, Any]) -> tuple[str, str] | None:
    pair_field = row.get("expected_law_article_pair_primary")
    parsed = parse_law_article_pairs(pair_field)
    if parsed:
        return parsed[0]
    return None


def get_expected_law_article_pairs_acceptable(row: dict[str, Any]) -> list[tuple[str, str]]:
    pairs = parse_law_article_pairs(row.get("expected_law_article_pairs_acceptable", []))
    primary = get_expected_law_article_pair_primary(row)
    return [pair for pair in pairs if pair != primary]


def get_expected_law_article_pairs_required_all(row: dict[str, Any]) -> list[tuple[str, str]]:
    return parse_law_article_pairs(row.get("expected_law_article_pairs_required_all", []))


def has_pair_schema_input(row: dict[str, Any]) -> bool:
    keys = (
        "expected_law_article_pair_primary",
        "expected_law_article_pairs_acceptable",
        "expected_law_article_pairs_required_all",
    )
    for key in keys:
        value = row.get(key)
        if isinstance(value, (list, dict, tuple)):
            if len(value) > 0:
                return True
            continue
        if str(value or "").strip():
            return True
    return False


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    rank = max(1, math.ceil(len(data) * p))
    return float(data[rank - 1])


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def resolve_versioned_output_paths(output_dir: Path) -> tuple[Path, Path, int]:
    summary_base = output_dir / "metrics_summary_v1.json"
    detail_base = output_dir / "metrics_detail_v1.csv"

    if (not summary_base.exists()) and (not detail_base.exists()):
        return summary_base, detail_base, 1

    version = 2
    while True:
        summary_path = output_dir / f"metrics_summary_v1_{version}.json"
        detail_path = output_dir / f"metrics_detail_v1_{version}.csv"
        if (not summary_path.exists()) and (not detail_path.exists()):
            return summary_path, detail_path, version
        version += 1


def load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"dataset line {lineno} is invalid json: {exc}") from exc
            question = str(row.get("question", "")).strip()
            if not question:
                raise ValueError(f"dataset line {lineno} missing question")
            rows.append(row)
    if not rows:
        raise ValueError("dataset is empty")
    return rows


def validate_dataset_against_neo4j(rows: list[dict[str, Any]]) -> tuple[bool, dict[str, list[dict[str, Any]]]]:
    try:
        from dotenv import load_dotenv
        from neo4j import GraphDatabase
    except Exception as exc:
        return False, {
            "runtime": [
                {
                    "type": "dependency_error",
                    "message": f"无法执行数据库校验，缺少依赖: {exc}",
                }
            ]
        }

    load_dotenv(".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "all-in-rag")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
    except Exception as exc:
        return False, {
            "runtime": [
                {
                    "type": "connect_error",
                    "message": f"连接Neo4j失败: {exc}",
                }
            ]
        }

    issues: dict[str, list[dict[str, Any]]] = {
        "missing_law": [],
        "missing_article": [],
        "missing_pair": [],
        "invalid_schema": [],
    }
    pair_q = "MATCH (l:LawDocument {name:$law})-[:HAS_ARTICLE]->(a:Article {articleId:$art}) RETURN count(*) AS c"
    pair_cache: dict[tuple[str, str], bool] = {}
    try:
        with driver.session(database=database) as session:
            law_set = {
                (record["name"] or "").strip()
                for record in session.run("MATCH (l:LawDocument) RETURN DISTINCT toString(l.name) AS name")
                if (record["name"] or "").strip()
            }
            article_set = {
                (record["aid"] or "").strip()
                for record in session.run("MATCH (a:Article) RETURN DISTINCT toString(a.articleId) AS aid")
                if (record["aid"] or "").strip()
            }

            for index, row in enumerate(rows, start=1):
                question = str(row.get("question", "")).strip()
                law_primary = get_expected_law_primary(row)
                law_acceptable = get_expected_law_acceptable(row)
                article_primary = get_expected_article_primary(row)
                article_acceptable = get_expected_article_acceptable(row)
                article_required_all = get_expected_article_required_all(row)
                pair_schema_present = has_pair_schema_input(row)
                pair_primary = get_expected_law_article_pair_primary(row)
                pair_acceptable = get_expected_law_article_pairs_acceptable(row)
                pair_required_all = get_expected_law_article_pairs_required_all(row)
                pair_targets = ([pair_primary] if pair_primary else []) + pair_acceptable + pair_required_all

                law_candidates = [law_primary] + law_acceptable
                article_candidates = [article_primary] + article_acceptable + article_required_all
                for law, article in pair_targets:
                    if law:
                        law_candidates.append(law)
                    if article:
                        article_candidates.append(article)
                law_candidates = [x for i, x in enumerate(law_candidates) if x and x not in law_candidates[:i]]
                article_candidates = [x for i, x in enumerate(article_candidates) if x and x not in article_candidates[:i]]

                for law in law_candidates:
                    if law and law not in law_set:
                        issues["missing_law"].append(
                            {"index": index, "expected_law": law, "question": question}
                        )
                for article in article_candidates:
                    if article and article not in article_set:
                        issues["missing_article"].append(
                            {"index": index, "expected_article": article, "question": question}
                        )

                if pair_schema_present and (not pair_targets):
                    issues["invalid_schema"].append(
                        {
                            "index": index,
                            "question": question,
                            "message": "成对标注字段存在，但未解析出有效 law/article 对",
                        }
                    )
                    continue

                if (not pair_targets) and (not law_primary) and any(article_candidates):
                    issues["invalid_schema"].append(
                        {
                            "index": index,
                            "question": question,
                            "message": "存在条号标注但缺少 expected_law_primary",
                        }
                    )
                    continue

                if pair_targets:
                    for law, article in pair_targets:
                        key = (law, article)
                        if key not in pair_cache:
                            count = session.run(pair_q, law=law, art=article).single()["c"]
                            pair_cache[key] = int(count) > 0
                        if not pair_cache[key]:
                            issues["missing_pair"].append(
                                {
                                    "index": index,
                                    "expected_law": law,
                                    "expected_article": article,
                                    "question": question,
                                }
                            )
                else:
                    law_scope = [law_primary] + law_acceptable
                    if law_scope:
                        for article in article_candidates:
                            if not article:
                                continue
                            pair_ok = False
                            for law in law_scope:
                                if not law:
                                    continue
                                key = (law, article)
                                if key not in pair_cache:
                                    count = session.run(pair_q, law=law, art=article).single()["c"]
                                    pair_cache[key] = int(count) > 0
                                if pair_cache[key]:
                                    pair_ok = True
                                    break
                            if not pair_ok:
                                issues["missing_pair"].append(
                                    {
                                        "index": index,
                                        "expected_law_scope": law_scope,
                                        "expected_article": article,
                                        "question": question,
                                    }
                                )
    except Exception as exc:
        driver.close()
        return False, {
            "runtime": [
                {
                    "type": "query_error",
                    "message": f"执行Neo4j校验查询失败: {exc}",
                }
            ]
        }

    driver.close()
    has_error = any(issues[key] for key in ("missing_law", "missing_article", "missing_pair", "invalid_schema"))
    return (not has_error), issues


def _milvus_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def validate_dataset_against_milvus(rows: list[dict[str, Any]]) -> tuple[bool, dict[str, list[dict[str, Any]]]]:
    try:
        from dotenv import load_dotenv
        from pymilvus import MilvusClient
    except Exception as exc:
        return False, {
            "runtime": [
                {
                    "type": "dependency_error",
                    "message": f"无法执行Milvus校验，缺少依赖: {exc}",
                }
            ]
        }

    load_dotenv(".env")
    host = os.getenv("MILVUS_HOST", "localhost").strip() or "localhost"
    port = int(os.getenv("MILVUS_PORT", "19530"))
    collection_name = os.getenv("MILVUS_COLLECTION_NAME", "legal_knowledge").strip() or "legal_knowledge"

    try:
        client = MilvusClient(uri=f"http://{host}:{port}")
    except Exception as exc:
        return False, {
            "runtime": [
                {
                    "type": "connect_error",
                    "message": f"连接Milvus失败: {exc}",
                }
            ]
        }

    issues: dict[str, list[dict[str, Any]]] = {
        "missing_law": [],
        "missing_article": [],
        "missing_pair": [],
        "invalid_schema": [],
    }
    exists_cache: dict[str, bool] = {}

    def exists(filter_expr: str) -> bool:
        if filter_expr in exists_cache:
            return exists_cache[filter_expr]
        try:
            rows_ = client.query(
                collection_name=collection_name,
                filter=filter_expr,
                output_fields=["id"],
                limit=1,
            )
        except TypeError:
            # 兼容旧参数名
            rows_ = client.query(
                collection_name=collection_name,
                expr=filter_expr,
                output_fields=["id"],
                limit=1,
            )
        exists_cache[filter_expr] = bool(rows_)
        return exists_cache[filter_expr]

    try:
        if not client.has_collection(collection_name=collection_name):
            return False, {
                "runtime": [
                    {
                        "type": "collection_not_found",
                        "message": f"Milvus集合不存在: {collection_name}",
                    }
                ]
            }

        for index, row in enumerate(rows, start=1):
            question = str(row.get("question", "")).strip()
            law_primary = get_expected_law_primary(row)
            law_acceptable = get_expected_law_acceptable(row)
            article_primary = get_expected_article_primary(row)
            article_acceptable = get_expected_article_acceptable(row)
            article_required_all = get_expected_article_required_all(row)
            pair_schema_present = has_pair_schema_input(row)
            pair_primary = get_expected_law_article_pair_primary(row)
            pair_acceptable = get_expected_law_article_pairs_acceptable(row)
            pair_required_all = get_expected_law_article_pairs_required_all(row)
            pair_targets = ([pair_primary] if pair_primary else []) + pair_acceptable + pair_required_all

            law_candidates = [law_primary] + law_acceptable
            article_candidates = [article_primary] + article_acceptable + article_required_all
            for law, article in pair_targets:
                if law:
                    law_candidates.append(law)
                if article:
                    article_candidates.append(article)
            law_candidates = [x for i, x in enumerate(law_candidates) if x and x not in law_candidates[:i]]
            article_candidates = [x for i, x in enumerate(article_candidates) if x and x not in article_candidates[:i]]

            for law in law_candidates:
                if not law:
                    continue
                filter_expr = f'law_name == "{_milvus_escape(law)}"'
                if not exists(filter_expr):
                    issues["missing_law"].append(
                        {"index": index, "expected_law": law, "question": question}
                    )

            for article in article_candidates:
                if not article:
                    continue
                filter_expr = f'article_id == "{_milvus_escape(article)}"'
                if not exists(filter_expr):
                    issues["missing_article"].append(
                        {"index": index, "expected_article": article, "question": question}
                    )

            if pair_schema_present and (not pair_targets):
                issues["invalid_schema"].append(
                    {
                        "index": index,
                        "question": question,
                        "message": "成对标注字段存在，但未解析出有效 law/article 对",
                    }
                )
                continue

            if (not pair_targets) and (not law_primary) and any(article_candidates):
                issues["invalid_schema"].append(
                    {
                        "index": index,
                        "question": question,
                        "message": "存在条号标注但缺少 expected_law_primary",
                    }
                )
                continue

            if pair_targets:
                for law, article in pair_targets:
                    filter_expr = (
                        f'law_name == "{_milvus_escape(law)}" and '
                        f'article_id == "{_milvus_escape(article)}"'
                    )
                    if not exists(filter_expr):
                        issues["missing_pair"].append(
                            {
                                "index": index,
                                "expected_law": law,
                                "expected_article": article,
                                "question": question,
                            }
                        )
            else:
                law_scope = [law_primary] + law_acceptable
                if law_scope:
                    for article in article_candidates:
                        if not article:
                            continue
                        pair_ok = False
                        for law in law_scope:
                            if not law:
                                continue
                            filter_expr = (
                                f'law_name == "{_milvus_escape(law)}" and '
                                f'article_id == "{_milvus_escape(article)}"'
                            )
                            if exists(filter_expr):
                                pair_ok = True
                                break
                        if not pair_ok:
                            issues["missing_pair"].append(
                                {
                                    "index": index,
                                    "expected_law_scope": law_scope,
                                    "expected_article": article,
                                    "question": question,
                                }
                            )
    except Exception as exc:
        return False, {
            "runtime": [
                {
                    "type": "query_error",
                    "message": f"执行Milvus校验查询失败: {exc}",
                }
            ]
        }

    has_error = any(issues[key] for key in ("missing_law", "missing_article", "missing_pair", "invalid_schema"))
    return (not has_error), issues


def create_chat(session: requests.Session, base_url: str, timeout: float) -> str:
    resp = session.post(f"{base_url}/chats", timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    chat_id = str(payload.get("chat_id", "")).strip()
    if not chat_id:
        raise ValueError("create_chat response missing chat_id")
    return chat_id


def build_eval_request(
    question: str,
    *,
    api_mode: str,
    eval_batch_id: str,
    eval_fast_mode: bool,
    chat_id: str = "",
    explain_routing: bool = False,
) -> dict[str, Any]:
    if api_mode == "chat":
        return {
            "chat_id": chat_id,
            "question": question,
            "explain_routing": explain_routing,
            "eval_batch_id": eval_batch_id,
            "eval_fast_mode": eval_fast_mode,
        }
    return {
        "contract_version": "v1",
        "question": question,
        "explain_routing": explain_routing,
        "eval_batch_id": eval_batch_id,
        "eval_fast_mode": eval_fast_mode,
    }


def eval_request_path(api_mode: str) -> str:
    return "/chat" if api_mode == "chat" else "/v1/augment"


def post_eval_request(
    session: requests.Session,
    base_url: str,
    payload: dict[str, Any],
    timeout: float,
    *,
    api_mode: str,
) -> Any:
    return session.post(f"{base_url}{eval_request_path(api_mode)}", json=payload, timeout=timeout)


def extract_refine_counts(refine: Any) -> dict[str, int]:
    payload = refine if isinstance(refine, dict) else {}
    claims = payload.get("claims") or []
    verdicts = [
        str(item.get("verdict", "")).strip().lower()
        for item in claims
        if isinstance(item, dict)
    ]
    counts = {
        "refine_supported_count": safe_int(payload.get("supported_count"), -1),
        "refine_weak_count": safe_int(payload.get("weak_count"), -1),
        "refine_unsupported_count": safe_int(payload.get("unsupported_count"), -1),
        "refine_claim_count": safe_int(payload.get("refined_claim_count"), -1),
    }
    if counts["refine_supported_count"] < 0:
        counts["refine_supported_count"] = sum(1 for value in verdicts if value == "supported")
    if counts["refine_weak_count"] < 0:
        counts["refine_weak_count"] = sum(1 for value in verdicts if value == "weak")
    if counts["refine_unsupported_count"] < 0:
        counts["refine_unsupported_count"] = sum(1 for value in verdicts if value == "unsupported")
    if counts["refine_claim_count"] < 0:
        counts["refine_claim_count"] = len(verdicts)
    return counts


def check_health(session: requests.Session, base_url: str, timeout: float) -> dict[str, Any]:
    resp = session.get(f"{base_url}/health", timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("health response is not a JSON object")
    return payload


def hit_law(expected_law: str, documents: list[dict[str, Any]]) -> bool:
    target = normalize_law_name(expected_law)
    if not target:
        return False
    for doc in documents:
        law = normalize_law_name(doc.get("law_name", ""))
        if law and law == target:
            return True
    return False


def hit_law_any(expected_laws: list[str], documents: list[dict[str, Any]]) -> bool:
    targets = {normalize_law_name(x) for x in expected_laws if normalize_law_name(x)}
    if not targets:
        return False
    for doc in documents:
        law = normalize_law_name(doc.get("law_name", ""))
        if law and law in targets:
            return True
    return False


def hit_article(expected_article: str, documents: list[dict[str, Any]]) -> bool:
    target = normalize_article(expected_article)
    if not target:
        return False
    for doc in documents:
        article = normalize_article(doc.get("article_id", ""))
        if article and article == target:
            return True
    return False


def hit_article_any(expected_articles: list[str], documents: list[dict[str, Any]]) -> bool:
    targets = {normalize_article(x) for x in expected_articles if normalize_article(x)}
    if not targets:
        return False
    for doc in documents:
        article = normalize_article(doc.get("article_id", ""))
        if article and article in targets:
            return True
    return False


def hit_article_all(required_articles: list[str], documents: list[dict[str, Any]]) -> bool:
    required = {normalize_article(x) for x in required_articles if normalize_article(x)}
    if not required:
        return False
    got = {
        normalize_article(doc.get("article_id", ""))
        for doc in documents
        if normalize_article(doc.get("article_id", ""))
    }
    return required.issubset(got)


def get_law_article_pairs(documents: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for doc in documents:
        law = normalize_law_name(doc.get("law_name", ""))
        article = normalize_article(doc.get("article_id", ""))
        if law and article:
            pairs.add((law, article))
    return pairs


def normalize_law_article_pair(pair: tuple[str, str]) -> tuple[str, str]:
    return normalize_law_name(pair[0]), normalize_article(pair[1])


def hit_law_article_pair_obj(expected_pair: tuple[str, str], documents: list[dict[str, Any]]) -> bool:
    law, article = normalize_law_article_pair(expected_pair)
    if not law or not article:
        return False
    return (law, article) in get_law_article_pairs(documents)


def hit_law_article_pair_objs_any(expected_pairs: list[tuple[str, str]], documents: list[dict[str, Any]]) -> bool:
    targets = {normalize_law_article_pair(pair) for pair in expected_pairs}
    targets = {(law, article) for law, article in targets if law and article}
    if not targets:
        return False
    pairs = get_law_article_pairs(documents)
    return any(pair in pairs for pair in targets)


def hit_law_article_pair_objs_all(expected_pairs: list[tuple[str, str]], documents: list[dict[str, Any]]) -> bool:
    targets = {normalize_law_article_pair(pair) for pair in expected_pairs}
    targets = {(law, article) for law, article in targets if law and article}
    if not targets:
        return False
    pairs = get_law_article_pairs(documents)
    return targets.issubset(pairs)


def hit_law_article_pair(expected_law: str, expected_article: str, documents: list[dict[str, Any]]) -> bool:
    law = normalize_law_name(expected_law)
    article = normalize_article(expected_article)
    if not law or not article:
        return False
    return (law, article) in get_law_article_pairs(documents)


def hit_law_article_pair_any(
    expected_laws: list[str], expected_articles: list[str], documents: list[dict[str, Any]]
) -> bool:
    laws = normalize_law_list(expected_laws)
    articles = normalize_article_list(expected_articles)
    if not laws or not articles:
        return False
    pairs = get_law_article_pairs(documents)
    for law in laws:
        for article in articles:
            if (law, article) in pairs:
                return True
    return False


def hit_law_article_pair_all(
    expected_laws: list[str], required_articles: list[str], documents: list[dict[str, Any]]
) -> bool:
    laws = normalize_law_list(expected_laws)
    required = normalize_article_list(required_articles)
    if not laws or not required:
        return False
    pairs = get_law_article_pairs(documents)
    for article in required:
        if not any((law, article) in pairs for law in laws):
            return False
    return True


def hit_keywords(expected_keywords: list[str], documents: list[dict[str, Any]]) -> tuple[int, int]:
    if not expected_keywords:
        return 0, 0
    corpus = "".join(
        normalize_text(
            " ".join(
                [
                    str(doc.get("display_title", "")),
                    str(doc.get("law_name", "")),
                    str(doc.get("article_id", "")),
                    str(doc.get("article_title", "")),
                    str(doc.get("snippet", "")),
                ]
            )
        )
        for doc in documents
    )
    hit_count = sum(1 for keyword in expected_keywords if keyword and keyword in corpus)
    return hit_count, len(expected_keywords)


def main() -> int:
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    eval_batch_id = args.eval_batch_id.strip() or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    warmup = max(0, int(args.warmup))
    warmup_mode = str(args.warmup_mode or "light").strip().lower()
    eval_fast_mode = str(args.eval_fast_mode or "off").strip().lower() == "on"
    api_mode = str(args.api_mode or "augment").strip().lower()
    request_timeout = max(1.0, float(args.timeout))
    warmup_timeout = max(request_timeout, float(args.warmup_timeout))
    health_timeout = max(1.0, float(args.health_timeout))

    try:
        rows = load_dataset(dataset_path)
    except Exception as exc:
        print(f"[eval] dataset error: {exc}", file=sys.stderr)
        return 1

    if not args.skip_db_validate:
        neo_ok, neo_issues = validate_dataset_against_neo4j(rows)
        if not neo_ok:
            print("[eval] dataset validation failed against Neo4j:", file=sys.stderr)
            print(json.dumps(neo_issues, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print("[eval] dataset validation passed against Neo4j")
        milvus_ok, milvus_issues = validate_dataset_against_milvus(rows)
        if not milvus_ok:
            print("[eval] dataset validation failed against Milvus:", file=sys.stderr)
            print(json.dumps(milvus_issues, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print("[eval] dataset validation passed against Milvus")
    else:
        print("[eval] skip db validation")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path, detail_path, result_version = resolve_versioned_output_paths(output_dir)
    if result_version > 1:
        print(f"[eval] existing result files detected, using version suffix _{result_version}")

    session = requests.Session()
    if not args.skip_health_check:
        try:
            health = check_health(session, base_url, timeout=health_timeout)
            status = str(health.get("status", "")).strip().lower()
            if status != "ready":
                print(
                    f"[eval] health check failed: status={health.get('status')} "
                    f"initialized={health.get('initialized')} system_ready={health.get('system_ready')} "
                    f"startup_error={health.get('startup_error')}",
                    file=sys.stderr,
                )
                return 1
            reranker_ready = bool(health.get("reranker_ready", False))
            if (not reranker_ready) and (not args.allow_reranker_not_ready):
                print(
                    f"[eval] health check failed: reranker_ready={health.get('reranker_ready')} "
                    f"reason={health.get('reranker_prewarm_reason', '')}",
                    file=sys.stderr,
                )
                return 1
            print(
                f"[eval] health ready: initialized={health.get('initialized')} "
                f"system_ready={health.get('system_ready')} "
                f"reranker_ready={health.get('reranker_ready')}"
            )
        except Exception as exc:
            print(f"[eval] health check failed: {exc}", file=sys.stderr)
            return 1
    else:
        print("[eval] skip health check")

    chat_id = ""
    if api_mode == "chat":
        try:
            chat_id = create_chat(session, base_url, timeout=request_timeout)
        except Exception as exc:
            print(f"[eval] create chat failed: {exc}", file=sys.stderr)
            return 1

    warmup_success = 0
    warmup_failures = 0
    for index, row in enumerate(rows[:warmup], start=1):
        try:
            if warmup_mode == "full":
                payload = build_eval_request(
                    str(row["question"]),
                    api_mode=api_mode,
                    eval_batch_id=eval_batch_id,
                    eval_fast_mode=eval_fast_mode,
                    chat_id=chat_id,
                )
                resp = post_eval_request(session, base_url, payload, warmup_timeout, api_mode=api_mode)
                resp.raise_for_status()
                print(f"[eval] warmup {index}/{warmup} done (full)")
            else:
                health = check_health(session, base_url, timeout=min(warmup_timeout, health_timeout))
                status = str(health.get("status", "")).strip().lower()
                if status != "ready":
                    raise RuntimeError(
                        f"warmup health not ready: status={health.get('status')} "
                        f"startup_error={health.get('startup_error', '')}"
                    )
                reranker_ready = bool(health.get("reranker_ready", False))
                if (not reranker_ready) and (not args.allow_reranker_not_ready):
                    raise RuntimeError(
                        f"warmup reranker not ready: reranker_ready={health.get('reranker_ready')} "
                        f"reason={health.get('reranker_prewarm_reason', '')}"
                    )
                print(f"[eval] warmup {index}/{warmup} done (light)")
            warmup_success += 1
        except Exception as exc:
            print(f"[eval] warmup {index}/{warmup} failed: {exc}")
            warmup_failures += 1

    if warmup > 0:
        print(
            f"[eval] warmup summary: total={warmup} success={warmup_success} "
            f"failed={warmup_failures} timeout={warmup_timeout:.1f}s mode={warmup_mode}"
        )
    if warmup_failures > 0 and not args.allow_warmup_fail:
        print(
            "[eval] warmup has failures, aborting evaluation. "
            "use --allow-warmup-fail to continue anyway.",
            file=sys.stderr,
        )
        return 1

    details: list[dict[str, Any]] = []
    elapsed_values: list[float] = []
    failure_count = 0
    empty_evidence_count = 0
    insufficient_count = 0
    law_den = 0
    law_num = 0
    law_acc_den = 0
    law_acc_num = 0
    article_den = 0
    article_num = 0
    article_acc_den = 0
    article_acc_num = 0
    article_complete_den = 0
    article_complete_num = 0
    keyword_den = 0
    keyword_num = 0
    graph_route_count = 0
    graph_grounding_success_count = 0
    graph_empty_no_grounding_count = 0
    graph_fallback_to_traditional_count = 0

    for idx, row in enumerate(rows, start=1):
        question = str(row["question"]).strip()
        expected_law = get_expected_law_primary(row)
        expected_law_acceptable = get_expected_law_acceptable(row)
        expected_article = get_expected_article_primary(row)
        expected_article_acceptable = get_expected_article_acceptable(row)
        expected_article_required_all = get_expected_article_required_all(row)
        expected_pair_primary = get_expected_law_article_pair_primary(row)
        expected_pairs_acceptable = get_expected_law_article_pairs_acceptable(row)
        expected_pairs_required_all = get_expected_law_article_pairs_required_all(row)
        expected_keywords = normalize_keywords(row.get("must_keywords", []))
        request_payload = build_eval_request(
            question,
            api_mode=api_mode,
            eval_batch_id=eval_batch_id,
            eval_fast_mode=eval_fast_mode,
            chat_id=chat_id,
        )
        request_start = time.perf_counter()
        http_status = 0
        error_message = ""
        response_payload: dict[str, Any] = {}
        try:
            resp = post_eval_request(session, base_url, request_payload, request_timeout, api_mode=api_mode)
            http_status = resp.status_code
            if resp.status_code == 200:
                response_payload = resp.json()
            else:
                error_message = resp.text[:500]
        except Exception as exc:
            error_message = str(exc)
        wall_seconds = round(time.perf_counter() - request_start, 4)

        is_failed = http_status != 200
        documents = []
        evidence_mode = ""
        elapsed_seconds = wall_seconds
        strategy = ""
        route_fallback = ""
        route_metrics_raw: dict[str, Any] = {}
        graph_empty_reason = ""
        graph_source_candidate_count = 0
        graph_source_hit_count = 0
        graph_target_candidate_count = 0
        graph_target_hit_count = 0
        graph_result_count = 0
        graph_attempted = False
        graph_fallback_to_traditional = False
        refine_counts = {
            "refine_supported_count": 0,
            "refine_weak_count": 0,
            "refine_unsupported_count": 0,
            "refine_claim_count": 0,
        }
        if not is_failed:
            documents = response_payload.get("documents", []) or []
            evidence = response_payload.get("evidence", {}) or {}
            analysis = response_payload.get("analysis", {}) or {}
            evidence_mode = str(evidence.get("mode", "") or "")
            strategy = str(analysis.get("strategy", "") or "")
            route_fallback = str(response_payload.get("route_fallback", "") or "")
            route_metrics_raw = response_payload.get("route_metrics", {}) or {}
            graph_empty_reason = str(route_metrics_raw.get("graph_empty_reason", "") or "")
            graph_source_candidate_count = safe_int(route_metrics_raw.get("graph_source_candidate_count", 0), 0)
            graph_source_hit_count = safe_int(route_metrics_raw.get("graph_source_hit_count", 0), 0)
            graph_target_candidate_count = safe_int(route_metrics_raw.get("graph_target_candidate_count", 0), 0)
            graph_target_hit_count = safe_int(route_metrics_raw.get("graph_target_hit_count", 0), 0)
            graph_result_count = safe_int(route_metrics_raw.get("graph_result_count", 0), 0)
            graph_attempted = safe_bool(route_metrics_raw.get("graph_attempted", False))
            if not graph_attempted and strategy in {"graph_rag", "combined"}:
                graph_attempted = True
            graph_fallback_to_traditional = safe_bool(route_metrics_raw.get("graph_fallback_to_traditional", False))
            if not graph_fallback_to_traditional and route_fallback == "empty_result_to_traditional":
                graph_fallback_to_traditional = True
            if graph_attempted:
                graph_route_count += 1
                if graph_source_hit_count > 0:
                    graph_grounding_success_count += 1
                if graph_empty_reason == "no_grounded_nodes":
                    graph_empty_no_grounding_count += 1
            if graph_fallback_to_traditional:
                graph_fallback_to_traditional_count += 1
            elapsed_seconds = float(response_payload.get("elapsed_seconds", wall_seconds) or wall_seconds)
            elapsed_values.append(elapsed_seconds)
            refine_counts = extract_refine_counts(response_payload.get("refine", {}))
        else:
            failure_count += 1

        if (not is_failed) and (not documents):
            empty_evidence_count += 1
        if evidence_mode == "insufficient":
            insufficient_count += 1

        timeout_stage = ""
        if is_failed:
            lower_error = error_message.lower()
            if "timed out" in lower_error:
                timeout_stage = "request_timeout"
            elif http_status > 0:
                timeout_stage = "http_error"
            elif error_message:
                timeout_stage = "transport_error"

        law_hit = False
        law_hit_acceptable = False
        article_hit = False
        article_hit_acceptable = False
        article_hit_complete = False
        article_strict_rule = "none"
        article_acceptable_rule = "none"
        article_complete_rule = "none"
        keyword_hit = 0
        keyword_total = 0
        if expected_law:
            law_den += 1
            law_hit = hit_law(expected_law, documents)
            if law_hit:
                law_num += 1
        law_targets_acceptable = [expected_law] + expected_law_acceptable
        if any(str(x).strip() for x in law_targets_acceptable):
            law_acc_den += 1
            law_hit_acceptable = hit_law_any(law_targets_acceptable, documents)
            if law_hit_acceptable:
                law_acc_num += 1
        if expected_pair_primary:
            article_den += 1
            article_hit = hit_law_article_pair_obj(expected_pair_primary, documents)
            article_strict_rule = "pair_schema_strict"
            if article_hit:
                article_num += 1
        elif expected_article:
            article_den += 1
            if expected_law:
                article_hit = hit_law_article_pair(expected_law, expected_article, documents)
                article_strict_rule = "law_article_pair"
            else:
                article_hit = hit_article(expected_article, documents)
                article_strict_rule = "article_only"
            if article_hit:
                article_num += 1
        article_targets_acceptable = [expected_article] + expected_article_acceptable
        pair_targets_acceptable = ([expected_pair_primary] if expected_pair_primary else []) + expected_pairs_acceptable
        if pair_targets_acceptable:
            article_acc_den += 1
            article_hit_acceptable = hit_law_article_pair_objs_any(pair_targets_acceptable, documents)
            article_acceptable_rule = "pair_schema_any"
            if article_hit_acceptable:
                article_acc_num += 1
        elif any(str(x).strip() for x in article_targets_acceptable):
            article_acc_den += 1
            if any(str(x).strip() for x in law_targets_acceptable):
                article_hit_acceptable = hit_law_article_pair_any(
                    law_targets_acceptable,
                    article_targets_acceptable,
                    documents,
                )
                article_acceptable_rule = "law_article_pair_any"
            else:
                article_hit_acceptable = hit_article_any(article_targets_acceptable, documents)
                article_acceptable_rule = "article_only_any"
            if article_hit_acceptable:
                article_acc_num += 1
        if expected_pairs_required_all:
            article_complete_den += 1
            article_hit_complete = hit_law_article_pair_objs_all(expected_pairs_required_all, documents)
            article_complete_rule = "pair_schema_all"
            if article_hit_complete:
                article_complete_num += 1
        elif expected_article_required_all:
            article_complete_den += 1
            if any(str(x).strip() for x in law_targets_acceptable):
                article_hit_complete = hit_law_article_pair_all(
                    law_targets_acceptable,
                    expected_article_required_all,
                    documents,
                )
                article_complete_rule = "law_article_pair_all"
            else:
                article_hit_complete = hit_article_all(expected_article_required_all, documents)
                article_complete_rule = "article_only_all"
            if article_hit_complete:
                article_complete_num += 1
        if expected_keywords:
            keyword_hit, keyword_total = hit_keywords(expected_keywords, documents)
            keyword_num += keyword_hit
            keyword_den += keyword_total

        details.append(
            {
                "index": idx,
                "question": question,
                "expected_law_raw": expected_law,
                "expected_law_norm": normalize_law_name(expected_law),
                "law_hit": int(law_hit),
                "expected_law_acceptable_raw": json.dumps(expected_law_acceptable, ensure_ascii=False),
                "law_hit_acceptable": int(law_hit_acceptable),
                "expected_article_raw": expected_article,
                "expected_article_norm": normalize_article(expected_article),
                "article_hit": int(article_hit),
                "expected_article_acceptable_raw": json.dumps(expected_article_acceptable, ensure_ascii=False),
                "article_hit_acceptable": int(article_hit_acceptable),
                "expected_article_required_all_raw": json.dumps(expected_article_required_all, ensure_ascii=False),
                "article_hit_complete": int(article_hit_complete),
                "expected_law_article_pair_primary_raw": json.dumps(
                    pair_to_jsonable(expected_pair_primary), ensure_ascii=False
                ),
                "expected_law_article_pairs_acceptable_raw": json.dumps(
                    pairs_to_jsonable(expected_pairs_acceptable), ensure_ascii=False
                ),
                "expected_law_article_pairs_required_all_raw": json.dumps(
                    pairs_to_jsonable(expected_pairs_required_all), ensure_ascii=False
                ),
                "article_strict_rule": article_strict_rule,
                "article_acceptable_rule": article_acceptable_rule,
                "article_complete_rule": article_complete_rule,
                "must_keywords_raw": json.dumps(row.get("must_keywords", []), ensure_ascii=False),
                "must_keywords_norm": json.dumps(expected_keywords, ensure_ascii=False),
                "keywords_hit": keyword_hit,
                "keywords_total": keyword_total,
                "http_status": http_status,
                "failed": int(is_failed),
                "error_message": error_message,
                "timeout_stage": timeout_stage,
                "elapsed_seconds": round(elapsed_seconds, 4),
                "wall_seconds": wall_seconds,
                "document_count": len(documents),
                "evidence_mode": evidence_mode,
                "strategy": strategy,
                "route_fallback": route_fallback,
                "graph_attempted": int(graph_attempted),
                "graph_fallback_to_traditional": int(graph_fallback_to_traditional),
                "graph_empty_reason": graph_empty_reason,
                "graph_source_candidate_count": graph_source_candidate_count,
                "graph_source_hit_count": graph_source_hit_count,
                "graph_target_candidate_count": graph_target_candidate_count,
                "graph_target_hit_count": graph_target_hit_count,
                "graph_result_count": graph_result_count,
                "eval_batch_id": eval_batch_id,
                "api_mode": api_mode,
                "eval_endpoint": eval_request_path(api_mode),
                "chat_id": chat_id,
                "refine_supported_count": refine_counts["refine_supported_count"],
                "refine_weak_count": refine_counts["refine_weak_count"],
                "refine_unsupported_count": refine_counts["refine_unsupported_count"],
                "refine_claim_count": refine_counts["refine_claim_count"],
            }
        )
        print(
            f"[eval] {idx}/{len(rows)} status={http_status} failed={int(is_failed)} "
            f"docs={len(documents)} mode={evidence_mode or '-'} elapsed={elapsed_seconds:.3f}s"
        )

    total_requests = len(rows)
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "eval_batch_id": eval_batch_id,
        "base_url": base_url,
        "api_mode": api_mode,
        "eval_endpoint": eval_request_path(api_mode),
        "dataset_path": str(dataset_path),
        "chat_id": chat_id,
        "result_version": result_version,
        "total_requests": total_requests,
        "warmup_requests": warmup,
        "warmup_success": warmup_success,
        "warmup_failures": warmup_failures,
        "warmup_mode": warmup_mode,
        "eval_fast_mode": eval_fast_mode,
        "timeouts": {
            "request_timeout_seconds": request_timeout,
            "warmup_timeout_seconds": warmup_timeout,
            "health_timeout_seconds": health_timeout,
        },
        "law_hit": {"numerator": law_num, "denominator": law_den, "rate": round(law_num / law_den, 4) if law_den else 0.0},
        "law_hit_acceptable": {
            "numerator": law_acc_num,
            "denominator": law_acc_den,
            "rate": round(law_acc_num / law_acc_den, 4) if law_acc_den else 0.0,
        },
        "article_hit": {
            "numerator": article_num,
            "denominator": article_den,
            "rate": round(article_num / article_den, 4) if article_den else 0.0,
        },
        "article_hit_acceptable": {
            "numerator": article_acc_num,
            "denominator": article_acc_den,
            "rate": round(article_acc_num / article_acc_den, 4) if article_acc_den else 0.0,
        },
        "article_complete_hit": {
            "numerator": article_complete_num,
            "denominator": article_complete_den,
            "rate": round(article_complete_num / article_complete_den, 4) if article_complete_den else 0.0,
        },
        "keyword_coverage": {
            "numerator": keyword_num,
            "denominator": keyword_den,
            "rate": round(keyword_num / keyword_den, 4) if keyword_den else 0.0,
        },
        "latency": {
            "count": len(elapsed_values),
            "mean": round(statistics.mean(elapsed_values), 4) if elapsed_values else 0.0,
            "p50": round(percentile(elapsed_values, 0.50), 4) if elapsed_values else 0.0,
            "p95": round(percentile(elapsed_values, 0.95), 4) if elapsed_values else 0.0,
        },
        "stability": {
            "request_failure_rate": round(failure_count / total_requests, 4) if total_requests else 0.0,
            "empty_evidence_rate": round(empty_evidence_count / total_requests, 4) if total_requests else 0.0,
            "insufficient_mode_rate": round(insufficient_count / total_requests, 4) if total_requests else 0.0,
            "request_failure_count": failure_count,
            "empty_evidence_count": empty_evidence_count,
            "insufficient_mode_count": insufficient_count,
        },
        "graph_route_metrics": {
            "graph_route_count": graph_route_count,
            "graph_grounding_success_count": graph_grounding_success_count,
            "graph_empty_no_grounding_count": graph_empty_no_grounding_count,
            "graph_fallback_to_traditional_count": graph_fallback_to_traditional_count,
            "graph_grounding_success_rate": (
                round(graph_grounding_success_count / graph_route_count, 4) if graph_route_count else 0.0
            ),
            "graph_empty_no_grounding_rate": (
                round(graph_empty_no_grounding_count / graph_route_count, 4) if graph_route_count else 0.0
            ),
            "graph_fallback_to_traditional_rate": (
                round(graph_fallback_to_traditional_count / graph_route_count, 4) if graph_route_count else 0.0
            ),
        },
        "exit_code_rule": "0=all success, 2=contains request failure, 1=fatal error",
    }

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = list(details[0].keys()) if details else []
    with detail_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in details:
            writer.writerow(row)

    print(f"[eval] summary: {summary_path}")
    print(f"[eval] detail : {detail_path}")

    if failure_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
