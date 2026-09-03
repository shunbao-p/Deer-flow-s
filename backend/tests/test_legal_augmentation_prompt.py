from __future__ import annotations

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.config.app_config import AppConfig


def _config(*, enabled: bool) -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "legal_rag": {"enabled": enabled},
        }
    )


def test_prompt_includes_rules_when_enabled(monkeypatch):
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=True))
    text = prompt_module.get_legal_augmentation_prompt_section()
    assert "<legal_augmentation>" in text
    assert "unsupported" in text
    assert "documents + evidence + refine.claims" in text


def test_prompt_omits_rules_when_disabled(monkeypatch):
    monkeypatch.setattr("deerflow.config.app_config.get_app_config", lambda: _config(enabled=False))
    text = prompt_module.get_legal_augmentation_prompt_section()
    assert text == ""
