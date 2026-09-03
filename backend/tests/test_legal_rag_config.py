from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.config.app_config import AppConfig
from deerflow.config.legal_rag_config import LegalRAGConfig


def test_default_legal_rag_is_disabled():
    config = AppConfig.model_validate({"sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"}})
    assert config.legal_rag.enabled is False
    assert config.legal_rag.base_url == "http://127.0.0.1:8003"
    assert config.legal_rag.timeout_seconds == 120


def test_valid_legal_rag_config_loads():
    config = LegalRAGConfig(enabled=True, base_url="http://legal-rag:8003/", timeout_seconds=30)
    assert config.enabled is True
    assert config.base_url == "http://legal-rag:8003"
    assert config.timeout_seconds == 30


def test_invalid_url_rejected():
    with pytest.raises(ValidationError):
        LegalRAGConfig(base_url="legal-rag:8003")


def test_non_positive_timeout_rejected():
    with pytest.raises(ValidationError):
        LegalRAGConfig(timeout_seconds=0)
