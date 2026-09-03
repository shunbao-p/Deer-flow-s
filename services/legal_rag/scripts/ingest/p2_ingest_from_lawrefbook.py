#!/usr/bin/env python3
"""
P2 legal knowledge ingestion pipeline.

Source:
- data/raw/Laws (LawRefBook/Laws repository markdown files)

Targets:
- Neo4j graph: LawDocument / Article / LegalDomain / RiskScenario / ComplianceStep
- Milvus collection: legal_knowledge
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from langchain_core.documents import Document
from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rag_modules.milvus_index_construction import MilvusIndexConstructionModule


ARTICLE_LINE_RE = re.compile(r"^第([一二三四五六七八九十百千万〇零两0-9]+)条[：:、\s]*(.*)$")
ARTICLE_REF_RE = re.compile(r"第([一二三四五六七八九十百千万〇零两0-9]+)条")
DATE_SUFFIX_RE = re.compile(r"[（(](\d{4}-\d{2}-\d{2})[)）]$")
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")


def short_hash(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def normalize_law_name(file_stem: str) -> str:
    return DATE_SUFFIX_RE.sub("", file_stem).strip()


def extract_version_date(file_stem: str) -> str:
    m = DATE_SUFFIX_RE.search(file_stem)
    return m.group(1) if m else "0000-00-00"


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    step = max(1, chunk_size - chunk_overlap)
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start += step
    return chunks


def pick_latest_law_files(source_root: Path) -> List[Path]:
    candidates = [
        p
        for p in source_root.rglob("*.md")
        if p.name != "_index.md" and ".git" not in p.parts
    ]

    by_key: Dict[Tuple[str, str], Path] = {}
    for p in candidates:
        rel = p.relative_to(source_root)
        domain = rel.parts[0] if rel.parts else "未分类"
        law_key = normalize_law_name(p.stem)
        key = (domain, law_key)

        prev = by_key.get(key)
        if prev is None:
            by_key[key] = p
            continue

        prev_date = extract_version_date(prev.stem)
        cur_date = extract_version_date(p.stem)
        if cur_date >= prev_date:
            by_key[key] = p

    # Prefer larger files first: more articles/chunks, faster hit target.
    return sorted(by_key.values(), key=lambda x: x.stat().st_size, reverse=True)


@dataclass
class ParsedArticle:
    node_id: str
    law_id: str
    law_name: str
    article_id: str
    article_title: str
    content: str
    domain: str
    citations: List[str]
    order_idx: int


@dataclass
class ParsedLaw:
    node_id: str
    name: str
    doc_type: str
    effective_date: str
    status: str
    domain: str
    source_path: str
    source_url: str
    version_date: str
    articles: List[ParsedArticle]


def parse_law_markdown(source_root: Path, path: Path) -> Optional[ParsedLaw]:
    rel = path.relative_to(source_root)
    domain = rel.parts[0] if rel.parts else "未分类"
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    law_name = normalize_law_name(path.stem)
    for ln in lines[:30]:
        m = HEADING_RE.match(ln.strip())
        if m:
            law_name = m.group(1).strip()
            break

    law_id = f"law_{short_hash(f'{domain}|{law_name}')}"
    version_date = extract_version_date(path.stem)
    source_rel = str(rel).replace("\\", "/")
    source_url = f"https://raw.githubusercontent.com/LawRefBook/Laws/master/{source_rel}"

    article_starts: List[Tuple[int, re.Match[str]]] = []
    for idx, raw in enumerate(lines):
        m = ARTICLE_LINE_RE.match(raw.strip())
        if m:
            article_starts.append((idx, m))

    if not article_starts:
        return None

    articles: List[ParsedArticle] = []
    for i, (start_idx, m) in enumerate(article_starts):
        end_idx = article_starts[i + 1][0] if i + 1 < len(article_starts) else len(lines)
        seg_lines = [x.rstrip() for x in lines[start_idx:end_idx]]
        seg = "\n".join(seg_lines).strip()
        if not seg:
            continue

        article_num = m.group(1).strip()
        article_id = f"第{article_num}条"
        first_title = m.group(2).strip()
        if first_title:
            article_title = first_title[:120]
        else:
            content_no_head = "\n".join(seg_lines[1:]).strip()
            article_title = content_no_head.split("。", 1)[0][:120] if content_no_head else article_id

        citations = [f"第{x}条" for x in ARTICLE_REF_RE.findall(seg)]
        citations = sorted({c for c in citations if c != article_id})

        article_node_id = f"art_{short_hash(f'{law_id}|{article_id}')}"
        articles.append(
            ParsedArticle(
                node_id=article_node_id,
                law_id=law_id,
                law_name=law_name,
                article_id=article_id,
                article_title=article_title,
                content=seg,
                domain=domain,
                citations=citations,
                order_idx=i,
            )
        )

    if not articles:
        return None

    return ParsedLaw(
        node_id=law_id,
        name=law_name,
        doc_type=domain,
        effective_date=version_date if version_date != "0000-00-00" else "",
        status="现行",
        domain=domain,
        source_path=source_rel,
        source_url=source_url,
        version_date=version_date,
        articles=articles,
    )


def map_domain_to_risk(domain: str) -> str:
    domain = domain or ""
    mappings = [
        ("社会法", "劳动用工与社会保障合规风险"),
        ("民法商法", "合同履约与交易合规风险"),
        ("诉讼与非诉讼程序法", "诉讼程序与证据风险"),
        ("行政法规", "行政监管与行政处罚风险"),
        ("经济法", "市场竞争与经营合规风险"),
        ("刑法", "刑事责任与犯罪预防风险"),
        ("地方性法规", "地方监管政策适用风险"),
        ("司法解释", "司法适用尺度变化风险"),
    ]
    for key, scenario in mappings:
        if key in domain:
            return scenario
    return "一般法律合规风险"


def batch_iter(items: Sequence[dict], batch_size: int) -> Iterable[Sequence[dict]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def run_neo4j_ingest(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str,
    laws: List[ParsedLaw],
    articles: List[ParsedArticle],
) -> Dict[str, int]:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    with driver.session(database=neo4j_database) as session:
        # Reset target labels only.
        session.run(
            """
            MATCH (n)
            WHERE n:LawDocument OR n:Article OR n:LegalDomain OR n:RiskScenario OR n:ComplianceStep
            DETACH DELETE n
            """
        )

        # Constraints / indexes.
        session.run("DROP CONSTRAINT article_id_unique IF EXISTS")
        session.run(
            "CREATE CONSTRAINT law_doc_node_id_unique IF NOT EXISTS FOR (n:LawDocument) REQUIRE n.nodeId IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT article_node_id_unique IF NOT EXISTS FOR (n:Article) REQUIRE n.nodeId IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT domain_node_id_unique IF NOT EXISTS FOR (n:LegalDomain) REQUIRE n.nodeId IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT risk_node_id_unique IF NOT EXISTS FOR (n:RiskScenario) REQUIRE n.nodeId IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT step_node_id_unique IF NOT EXISTS FOR (n:ComplianceStep) REQUIRE n.nodeId IS UNIQUE"
        )
        session.run("CREATE INDEX article_id_idx IF NOT EXISTS FOR (n:Article) ON (n.articleId)")
        session.run("CREATE INDEX law_doc_name_idx IF NOT EXISTS FOR (n:LawDocument) ON (n.name)")
        session.run("CREATE INDEX article_title_idx IF NOT EXISTS FOR (n:Article) ON (n.title)")
        session.run(
            """
            CREATE FULLTEXT INDEX legal_fulltext_idx IF NOT EXISTS
            FOR (n:LawDocument|Article|RiskScenario)
            ON EACH [n.name, n.title, n.content, n.keywords, n.description, n.articleId]
            """
        )

        domain_names = sorted({law.domain for law in laws if law.domain})
        domains = [{"node_id": f"domain_{short_hash(d)}", "name": d} for d in domain_names]
        domain_id_map = {x["name"]: x["node_id"] for x in domains}

        law_rows = [
            {
                "node_id": x.node_id,
                "name": x.name,
                "doc_type": x.doc_type,
                "effective_date": x.effective_date,
                "status": x.status,
                "source_path": x.source_path,
                "source_url": x.source_url,
                "version_date": x.version_date,
            }
            for x in laws
        ]
        article_rows = [
            {
                "node_id": x.node_id,
                "law_id": x.law_id,
                "article_id": x.article_id,
                "title": x.article_title,
                "content": x.content,
                "keywords": "",
                "law_name": x.law_name,
                "domain_id": domain_id_map.get(x.domain, ""),
                "domain_name": x.domain,
                "order_idx": x.order_idx,
            }
            for x in articles
        ]

        for batch in batch_iter(domains, 500):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (d:LegalDomain {nodeId: row.node_id})
                SET d.name = row.name
                """,
                rows=list(batch),
            )

        for batch in batch_iter(law_rows, 300):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (l:LawDocument {nodeId: row.node_id})
                SET l.name = row.name,
                    l.docType = row.doc_type,
                    l.effectiveDate = row.effective_date,
                    l.status = row.status,
                    l.sourcePath = row.source_path,
                    l.sourceUrl = row.source_url,
                    l.documentVersion = row.version_date
                """,
                rows=list(batch),
            )

        for batch in batch_iter(article_rows, 500):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (a:Article {nodeId: row.node_id})
                SET a.articleId = row.article_id,
                    a.title = row.title,
                    a.content = row.content,
                    a.keywords = row.keywords,
                    a.lawName = row.law_name,
                    a.orderIndex = row.order_idx,
                    a.domain = row.domain_name
                """,
                rows=list(batch),
            )

        for batch in batch_iter(article_rows, 500):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (l:LawDocument {nodeId: row.law_id})
                MATCH (a:Article {nodeId: row.node_id})
                MERGE (l)-[:HAS_ARTICLE]->(a)
                """,
                rows=list(batch),
            )
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Article {nodeId: row.node_id})
                MATCH (d:LegalDomain {nodeId: row.domain_id})
                MERGE (a)-[:BELONGS_TO_DOMAIN]->(d)
                """,
                rows=[x for x in batch if x.get("domain_id")],
            )

        cite_rows: List[dict] = []
        precedes_rows: List[dict] = []
        relates_rows: List[dict] = []
        applies_rows: List[dict] = []

        by_law: Dict[str, List[ParsedArticle]] = {}
        for a in articles:
            by_law.setdefault(a.law_id, []).append(a)

        # Risk scenarios and compliance steps.
        scenario_names = sorted({map_domain_to_risk(x.domain) for x in laws})
        scenario_rows = [
            {"node_id": f"risk_{short_hash(name)}", "name": name, "description": f"{name}（自动生成）"}
            for name in scenario_names
        ]
        scenario_id_map = {x["name"]: x["node_id"] for x in scenario_rows}
        step_rows = [
            {"node_id": "step_001", "name": "识别事实与主体", "description": "识别行为事实与法律主体", "order": 1},
            {"node_id": "step_002", "name": "定位法规与条款", "description": "定位适用法规和条款依据", "order": 2},
            {"node_id": "step_003", "name": "形成合规建议", "description": "形成风险提示与合规建议", "order": 3},
        ]

        for law_id, law_articles in by_law.items():
            sorted_articles = sorted(law_articles, key=lambda x: x.order_idx)
            law_article_ids = {x.article_id for x in sorted_articles}
            for idx, art in enumerate(sorted_articles):
                if idx + 1 < len(sorted_articles):
                    nxt = sorted_articles[idx + 1]
                    precedes_rows.append({"src": art.node_id, "dst": nxt.node_id})
                    relates_rows.append({"src": art.node_id, "dst": nxt.node_id})

                for c in art.citations:
                    if c in law_article_ids:
                        cite_rows.append({"law_id": law_id, "src": art.node_id, "cited_article_id": c})

                scenario_name = map_domain_to_risk(art.domain)
                applies_rows.append({"src": art.node_id, "risk_id": scenario_id_map[scenario_name]})

        for batch in batch_iter(scenario_rows, 200):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (r:RiskScenario {nodeId: row.node_id})
                SET r.name = row.name, r.description = row.description
                """,
                rows=list(batch),
            )
        for batch in batch_iter(step_rows, 50):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (s:ComplianceStep {nodeId: row.node_id})
                SET s.name = row.name, s.description = row.description, s.order = row.order
                """,
                rows=list(batch),
            )
        session.run(
            """
            MATCH (r:RiskScenario), (s1:ComplianceStep {nodeId:'step_001'}), (s2:ComplianceStep {nodeId:'step_002'}), (s3:ComplianceStep {nodeId:'step_003'})
            MERGE (r)-[:REQUIRES_STEP]->(s1)
            MERGE (r)-[:REQUIRES_STEP]->(s2)
            MERGE (r)-[:REQUIRES_STEP]->(s3)
            MERGE (s1)-[:PRECEDES]->(s2)
            MERGE (s2)-[:PRECEDES]->(s3)
            """
        )

        for batch in batch_iter(precedes_rows, 1000):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Article {nodeId: row.src})
                MATCH (b:Article {nodeId: row.dst})
                MERGE (a)-[:PRECEDES]->(b)
                """,
                rows=list(batch),
            )
        for batch in batch_iter(relates_rows, 1000):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Article {nodeId: row.src})
                MATCH (b:Article {nodeId: row.dst})
                MERGE (a)-[:RELATES_TO]->(b)
                """,
                rows=list(batch),
            )
        for batch in batch_iter(cite_rows, 1000):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Article {nodeId: row.src})
                MATCH (l:LawDocument {nodeId: row.law_id})-[:HAS_ARTICLE]->(t:Article {articleId: row.cited_article_id})
                MERGE (s)-[:CITES]->(t)
                """,
                rows=list(batch),
            )
        for batch in batch_iter(applies_rows, 1000):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Article {nodeId: row.src})
                MATCH (r:RiskScenario {nodeId: row.risk_id})
                MERGE (a)-[:APPLIES_TO]->(r)
                """,
                rows=list(batch),
            )

        counts = session.run(
            """
            MATCH (l:LawDocument)
            WITH count(l) AS law_docs
            MATCH (a:Article)
            WITH law_docs, count(a) AS articles
            MATCH (d:LegalDomain)
            WITH law_docs, articles, count(d) AS domains
            MATCH (r:RiskScenario)
            WITH law_docs, articles, domains, count(r) AS risks
            MATCH (s:ComplianceStep)
            RETURN law_docs, articles, domains, risks, count(s) AS steps
            """
        ).single()
        rel_total = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]

    driver.close()
    return {
        "law_docs": counts["law_docs"],
        "articles": counts["articles"],
        "domains": counts["domains"],
        "risks": counts["risks"],
        "steps": counts["steps"],
        "relations": rel_total,
    }


def run_milvus_ingest(
    milvus_host: str,
    milvus_port: int,
    collection_name: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
    articles: List[ParsedArticle],
    batch_size: int,
) -> Dict[str, int]:
    milvus = MilvusIndexConstructionModule(
        host=milvus_host,
        port=milvus_port,
        collection_name=collection_name,
        dimension=512,
        model_name=embedding_model,
    )
    if not milvus.create_collection(force_recreate=True):
        raise RuntimeError("Milvus collection create failed")

    # Cache per article relation stats.
    citation_count_map = {a.node_id: len(a.citations) for a in articles}
    relation_count_map = {a.node_id: 2 for a in articles}  # PRECEDES + RELATES_TO baseline

    inserted = 0
    batch_round = 0
    docs_batch: List[Document] = []

    for art in articles:
        scenario_name = map_domain_to_risk(art.domain)
        chunks = chunk_text(art.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        total_chunks = len(chunks)
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{art.node_id}_chunk_{idx}"
            metadata = {
                "node_id": art.node_id,
                "node_type": "Article",
                "doc_type": "chunk",
                "law_name": art.law_name,
                "article_id": art.article_id,
                "article_title": art.article_title,
                "legal_domain": art.domain,
                "citation_count": citation_count_map.get(art.node_id, 0),
                "relation_count": relation_count_map.get(art.node_id, 0),
                "risk_scenarios": [scenario_name],
                "chunk_id": chunk_id,
                "parent_id": art.node_id,
                "chunk_index": idx,
                "total_chunks": total_chunks,
            }
            docs_batch.append(Document(page_content=chunk, metadata=metadata))

            if len(docs_batch) >= batch_size:
                if not milvus.add_documents(docs_batch):
                    raise RuntimeError(f"Milvus add_documents failed at inserted={inserted}")
                inserted += len(docs_batch)
                batch_round += 1
                if batch_round % 10 == 0:
                    print(f"[P2] Milvus progress: inserted={inserted}", flush=True)
                docs_batch = []

    if docs_batch:
        if not milvus.add_documents(docs_batch):
            raise RuntimeError(f"Milvus add_documents failed at inserted={inserted}")
        inserted += len(docs_batch)
        print(f"[P2] Milvus progress: inserted={inserted}", flush=True)

    if not milvus.create_index():
        raise RuntimeError("Milvus create_index failed")
    if not milvus.load_collection():
        raise RuntimeError("Milvus load_collection failed")
    stats = milvus.get_collection_stats()
    milvus.close()
    return {"inserted_chunks": inserted, "row_count": int(stats.get("row_count", 0))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P2 ingestion from LawRefBook markdown source")
    parser.add_argument("--source-root", default="data/raw/Laws")
    parser.add_argument("--target-laws", type=int, default=120)
    parser.add_argument("--target-articles", type=int, default=15000)
    parser.add_argument("--target-chunks", type=int, default=50000)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--chunk-overlap", type=int, default=20)
    parser.add_argument("--milvus-batch", type=int, default=320)
    parser.add_argument("--manifest", default="data/manifests/legal_sources_manifest.csv")
    args = parser.parse_args()

    load_dotenv(".env")
    source_root = Path(args.source_root)
    if not source_root.exists():
        raise FileNotFoundError(f"source_root not found: {source_root}")

    start_ts = time.time()
    print("[P2] scanning law files...")
    files = pick_latest_law_files(source_root)
    print(f"[P2] candidate latest laws: {len(files)}")

    selected_laws: List[ParsedLaw] = []
    selected_articles: List[ParsedArticle] = []
    law_count = 0
    article_count = 0
    chunk_count = 0

    for p in files:
        parsed = parse_law_markdown(source_root, p)
        if parsed is None:
            continue
        selected_laws.append(parsed)
        selected_articles.extend(parsed.articles)

        law_count += 1
        article_count += len(parsed.articles)
        for art in parsed.articles:
            chunk_count += len(chunk_text(art.content, args.chunk_size, args.chunk_overlap))

        if (
            law_count >= args.target_laws
            and article_count >= args.target_articles
            and chunk_count >= args.target_chunks
        ):
            break

    print(
        f"[P2] selected laws={law_count}, articles={article_count}, estimated_chunks={chunk_count}"
    )
    if law_count < args.target_laws or article_count < args.target_articles or chunk_count < args.target_chunks:
        raise RuntimeError(
            f"target not reached: laws={law_count}/{args.target_laws}, "
            f"articles={article_count}/{args.target_articles}, chunks={chunk_count}/{args.target_chunks}"
        )

    # Build manifest.
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_url",
                "source_title",
                "publisher",
                "fetch_date",
                "document_version",
                "effective_date",
                "license_or_terms",
                "checksum",
                "ingest_batch_id",
                "source_path",
            ],
        )
        writer.writeheader()
        batch_id = f"p2_{int(start_ts)}"
        for law in selected_laws:
            writer.writerow(
                {
                    "source_url": law.source_url,
                    "source_title": law.name,
                    "publisher": "LawRefBook (来源声明：国家法律法规数据库)",
                    "fetch_date": time.strftime("%Y-%m-%d"),
                    "document_version": law.version_date,
                    "effective_date": law.effective_date,
                    "license_or_terms": "法律法规文本（公开法律文本整合）",
                    "checksum": short_hash(law.source_path),
                    "ingest_batch_id": batch_id,
                    "source_path": law.source_path,
                }
            )

    print("[P2] ingesting into Neo4j...")
    neo4j_stats = run_neo4j_ingest(
        neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", "all-in-rag"),
        neo4j_database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        laws=selected_laws,
        articles=selected_articles,
    )
    print(f"[P2] Neo4j stats: {neo4j_stats}")

    print("[P2] ingesting vectors into Milvus...")
    milvus_stats = run_milvus_ingest(
        milvus_host=os.environ.get("MILVUS_HOST", "localhost"),
        milvus_port=int(os.environ.get("MILVUS_PORT", "19530")),
        collection_name="legal_knowledge",
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        articles=selected_articles,
        batch_size=args.milvus_batch,
    )
    print(f"[P2] Milvus stats: {milvus_stats}")

    elapsed = time.time() - start_ts
    print(
        f"[P2] DONE in {elapsed/60:.1f} min | laws={law_count}, articles={article_count}, "
        f"chunks={chunk_count}, neo4j_rel={neo4j_stats['relations']}, milvus_rows={milvus_stats['row_count']}"
    )


if __name__ == "__main__":
    main()
