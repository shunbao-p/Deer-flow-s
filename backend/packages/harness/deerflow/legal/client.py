from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from deerflow.config.legal_rag_config import LegalRAGConfig
from deerflow.legal.contracts import (
    CONTRACT_VERSION,
    LegalAugmentationFailure,
    LegalAugmentationRequest,
    LegalAugmentationResult,
)

logger = logging.getLogger(__name__)


class LegalRAGClientError(Exception):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message

    def to_failure(self) -> LegalAugmentationFailure:
        allowed = {"disabled", "timeout", "unavailable", "invalid_response"}
        error_type = self.error_type if self.error_type in allowed else "unavailable"
        return LegalAugmentationFailure(error_type=error_type, message=self.message)


def resolve_legal_rag_base_url(config: LegalRAGConfig) -> str:
    env_url = str(os.getenv("LEGAL_RAG_BASE_URL") or "").strip()
    return (env_url or config.base_url).rstrip("/")


class LegalRAGClient:
    def __init__(self, config: LegalRAGConfig) -> None:
        self._config = config
        self._base_url = resolve_legal_rag_base_url(config)
        timeout = httpx.Timeout(config.timeout_seconds, connect=5.0)
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/health")
        except httpx.TimeoutException as exc:
            logger.warning("legal_rag timeout endpoint=/health error_type=timeout")
            raise LegalRAGClientError("timeout", "legal rag health timed out") from exc
        except httpx.RequestError as exc:
            logger.warning("legal_rag unavailable endpoint=/health error_type=unavailable")
            raise LegalRAGClientError("unavailable", "legal rag service unavailable") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("legal_rag invalid_json endpoint=/health error_type=invalid_response")
            raise LegalRAGClientError("invalid_response", "legal rag health returned non-json") from exc
        if not isinstance(payload, dict):
            raise LegalRAGClientError("invalid_response", "legal rag health returned a non-object body")
        return payload

    async def augment(self, request: LegalAugmentationRequest) -> LegalAugmentationResult:
        started = time.perf_counter()
        try:
            response = await self._client.post("/v1/augment", json=request.model_dump())
        except httpx.TimeoutException as exc:
            logger.warning("legal_rag timeout endpoint=/v1/augment error_type=timeout")
            raise LegalRAGClientError("timeout", "legal rag request timed out") from exc
        except httpx.RequestError as exc:
            logger.warning("legal_rag unavailable endpoint=/v1/augment error_type=unavailable")
            raise LegalRAGClientError("unavailable", "legal rag service unavailable") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            logger.warning(
                "legal_rag http_error endpoint=/v1/augment status=%s elapsed_ms=%s error_type=unavailable",
                response.status_code,
                elapsed_ms,
            )
            raise LegalRAGClientError("unavailable", f"legal rag returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("legal_rag invalid_json endpoint=/v1/augment error_type=invalid_response")
            raise LegalRAGClientError("invalid_response", "legal rag returned non-json") from exc

        if not isinstance(payload, dict):
            raise LegalRAGClientError("invalid_response", "legal rag returned a non-object body")
        if payload.get("contract_version") != CONTRACT_VERSION:
            raise LegalRAGClientError("invalid_response", "legal rag contract version mismatch")
        for field in ("documents", "evidence", "refine"):
            if field not in payload:
                raise LegalRAGClientError("invalid_response", f"legal rag missing {field}")

        try:
            result = LegalAugmentationResult.model_validate(payload)
        except Exception as exc:
            logger.warning("legal_rag schema_error endpoint=/v1/augment error_type=invalid_response")
            raise LegalRAGClientError("invalid_response", "legal rag payload failed schema validation") from exc

        logger.info(
            "legal_rag ok endpoint=/v1/augment elapsed_ms=%s strategy=%s evidence_mode=%s document_count=%s",
            elapsed_ms,
            result.analysis.strategy,
            result.evidence.mode,
            len(result.documents),
        )
        return result
