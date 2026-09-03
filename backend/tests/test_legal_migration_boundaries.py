from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PYPROJECT = REPO_ROOT / "backend" / "packages" / "harness" / "pyproject.toml"
COMPOSE_FILES = (
    REPO_ROOT / "docker" / "docker-compose.yaml",
    REPO_ROOT / "docker" / "docker-compose-dev.yaml",
)
BANNED_DEPS = (
    "pymilvus",
    "neo4j",
    "sentence-transformers",
    "langchain-core==0.3",
    "torch",
)
BANNED_DB_TOKENS = ("neo4j", "milvus", "etcd", "minio")


def test_harness_does_not_take_legal_heavy_deps():
    text = HARNESS_PYPROJECT.read_text(encoding="utf-8")
    for token in BANNED_DEPS:
        assert token not in text


def test_compose_reuses_external_dbs_and_does_not_block_deer_startup():
    for path in COMPOSE_FILES:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = data["services"]
        assert "legal-rag" in services
        for name, spec in services.items():
            lowered = name.lower()
            image = str((spec or {}).get("image", "")).lower()
            assert not any(token in lowered for token in BANNED_DB_TOKENS)
            assert not any(token in image for token in BANNED_DB_TOKENS)
        langgraph = services["langgraph"]
        depends = langgraph.get("depends_on")
        if isinstance(depends, dict):
            legal = depends.get("legal-rag") or {}
            assert legal.get("condition") != "service_healthy"
        else:
            assert "legal-rag" in list(depends or [])


def test_deer_python_has_no_direct_db_clients():
    harness = REPO_ROOT / "backend" / "packages" / "harness" / "deerflow"
    offenders: list[str] = []
    for py_file in harness.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "import neo4j" in text or "from neo4j" in text or "import pymilvus" in text or "from pymilvus" in text:
            offenders.append(str(py_file.relative_to(REPO_ROOT)))
    assert offenders == []
