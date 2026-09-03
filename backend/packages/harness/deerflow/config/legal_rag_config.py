"""Configuration for the internal Legal RAG augmentation client."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LegalRAGConfig(BaseModel):
    """Deer-side client settings for the internal Legal RAG service."""

    enabled: bool = Field(default=False, description="Whether to expose the legal augmentation tool")
    base_url: str = Field(default="http://127.0.0.1:8003", description="Internal Legal RAG service base URL")
    timeout_seconds: float = Field(default=120, gt=0, description="Total HTTP timeout in seconds")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        url = str(value or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("legal_rag.base_url must be an http(s) URL")
        return url.rstrip("/")
