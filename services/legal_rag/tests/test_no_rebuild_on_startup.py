from __future__ import annotations

import sys
import types

import pytest

from api.service import LegalAugmentationService


def _install_fake_system(monkeypatch, *, on_build):
    class _FakeSystem:
        system_ready = True

        def initialize_system(self):
            return None

        def build_knowledge_base(self, allow_rebuild=True):
            return on_build(allow_rebuild)

        def _cleanup(self):
            return None

    fake_main = types.ModuleType("main")
    fake_main.AdvancedGraphRAGSystem = _FakeSystem
    monkeypatch.setitem(sys.modules, "main", fake_main)
    return _FakeSystem


def test_startup_requires_existing_collection_and_does_not_rebuild(monkeypatch):
    seen: dict[str, bool] = {}

    def on_build(allow_rebuild: bool):
        seen["allow_rebuild"] = allow_rebuild
        raise RuntimeError("existing legal_knowledge collection is required; refusing to rebuild")

    _install_fake_system(monkeypatch, on_build=on_build)
    service = LegalAugmentationService()
    with pytest.raises(RuntimeError, match="refusing to rebuild"):
        service.startup()
    assert seen["allow_rebuild"] is False
    health = service.health()
    assert health["status"] == "failed"
    assert health["system_ready"] is False


def test_startup_load_failure_does_not_rebuild(monkeypatch):
    def on_build(allow_rebuild: bool):
        assert allow_rebuild is False
        raise RuntimeError("existing legal_knowledge collection failed to load; refusing to rebuild")

    _install_fake_system(monkeypatch, on_build=on_build)
    service = LegalAugmentationService()
    with pytest.raises(RuntimeError, match="failed to load"):
        service.startup()
    assert service.health()["status"] == "failed"


def test_startup_loads_existing_collection_when_present(monkeypatch):
    def on_build(allow_rebuild: bool):
        assert allow_rebuild is False
        return None

    _install_fake_system(monkeypatch, on_build=on_build)
    service = LegalAugmentationService()
    service.startup()
    assert service.health()["status"] == "ready"
    assert service.health()["system_ready"] is True
