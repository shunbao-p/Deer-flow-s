from __future__ import annotations

import asyncio
import os

import pytest

from deerflow.config.legal_rag_config import LegalRAGConfig
from deerflow.legal.client import LegalRAGClient
from deerflow.legal.contracts import LegalAugmentationRequest

pytestmark = pytest.mark.skipif(
    os.getenv("LEGAL_RAG_LIVE") != "1",
    reason="set LEGAL_RAG_LIVE=1 against a ready legal-rag service",
)


def test_live_augment_returns_v1_authority_fields():
    config = LegalRAGConfig(
        enabled=True,
        base_url=os.getenv("LEGAL_RAG_BASE_URL", "http://127.0.0.1:8003"),
        timeout_seconds=120,
    )

    async def _run() -> None:
        client = LegalRAGClient(config)
        try:
            try:
                health = await client.health()
            except Exception:
                pytest.skip("legal-rag health is not ready")
            if not health.get("system_ready"):
                pytest.skip("legal-rag is reachable but not ready")
            result = await client.augment(LegalAugmentationRequest(question="试用期解除劳动合同的法定依据"))
            assert result.contract_version == "v1"
            assert result.documents is not None
            assert result.evidence.mode
            assert isinstance(result.refine.claims, list)
        finally:
            await client.aclose()

    asyncio.run(_run())
