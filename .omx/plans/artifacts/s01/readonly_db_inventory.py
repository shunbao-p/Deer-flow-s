#!/usr/bin/env python3
"""Read-only inventory of the existing Legal Neo4j/Milvus instances.

This script never creates, drops, rebuilds, or writes collections/indexes.
It only reports identifiers needed by S01. Do not print passwords.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def inventory_neo4j() -> dict:
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return {
            "reachable": False,
            "error": "ImportError",
            "driver_missing": True,
        }

    uri = _env("NEO4J_URI", "bolt://localhost:7687")
    user = _env("NEO4J_USER", "neo4j")
    password = _env("NEO4J_PASSWORD", "all-in-rag")
    database = _env("NEO4J_DATABASE", "neo4j")
    payload: dict = {
        "reachable": False,
        "uri_scheme_host": uri.split("@")[-1],
        "database": database,
        "labels": [],
        "relationship_types": [],
        "indexes": [],
        "constraints": [],
        "label_counts": {},
        "error": "",
    }
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            payload["reachable"] = True
            payload["labels"] = [
                rec["label"] for rec in session.run("CALL db.labels() YIELD label RETURN label ORDER BY label")
            ]
            payload["relationship_types"] = [
                rec["rel"]
                for rec in session.run("CALL db.relationshipTypes() YIELD relationshipType AS rel RETURN rel ORDER BY rel")
            ]
            payload["indexes"] = [dict(rec) for rec in session.run("SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties RETURN name, type, state, labelsOrTypes, properties")]
            payload["constraints"] = [dict(rec) for rec in session.run("SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties")]
            for label in payload["labels"]:
                count = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS c").single()
                payload["label_counts"][label] = int(count["c"]) if count else 0
    except Exception as exc:
        payload["error"] = f"{exc.__class__.__name__}"
    finally:
        driver.close()
    return payload


def inventory_milvus() -> dict:
    try:
        from pymilvus import MilvusClient
    except ImportError:
        return {
            "reachable": False,
            "error": "ImportError",
            "driver_missing": True,
        }

    host = _env("MILVUS_HOST", "localhost")
    port = int(_env("MILVUS_PORT", "19530"))
    collection = _env("MILVUS_COLLECTION_NAME", "legal_knowledge")
    payload: dict = {
        "reachable": False,
        "host": host,
        "port": port,
        "target_collection": collection,
        "collections": [],
        "collection": {},
        "error": "",
    }
    client = MilvusClient(uri=f"http://{host}:{port}")
    try:
        payload["reachable"] = True
        payload["collections"] = list(client.list_collections())
        if collection in payload["collections"]:
            stats = client.get_collection_stats(collection_name=collection)
            desc = client.describe_collection(collection_name=collection)
            payload["collection"] = {
                "name": collection,
                "row_count": stats.get("row_count", stats.get("rowCount")),
                "description": desc,
            }
        else:
            payload["error"] = "target_collection_missing"
    except Exception as exc:
        payload["error"] = f"{exc.__class__.__name__}"
    return payload


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("db_inventory.json")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only",
        "writes_executed": False,
        "neo4j": {},
        "milvus": {},
    }
    try:
        report["neo4j"] = inventory_neo4j()
    except Exception as exc:
        report["neo4j"] = {"reachable": False, "error": exc.__class__.__name__}
    try:
        report["milvus"] = inventory_milvus()
    except Exception as exc:
        report["milvus"] = {"reachable": False, "error": exc.__class__.__name__}

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out_path}")
    print(json.dumps({
        "neo4j_reachable": report["neo4j"].get("reachable"),
        "milvus_reachable": report["milvus"].get("reachable"),
        "neo4j_error": report["neo4j"].get("error", ""),
        "milvus_error": report["milvus"].get("error", ""),
        "writes_executed": False,
    }, ensure_ascii=False))
    return 0 if report["neo4j"].get("reachable") and report["milvus"].get("reachable") else 2


if __name__ == "__main__":
    raise SystemExit(main())
