"""Core behavior tests for install_skill tool."""

import importlib
from types import SimpleNamespace

from deerflow.skills.installer import (
    InvalidSkillArchiveError,
    SkillAlreadyExistsError,
    SkillInstallResult,
)

install_skill_tool_module = importlib.import_module("deerflow.tools.builtins.install_skill_tool")


def _make_runtime(thread_id: str | None = "thread-1") -> SimpleNamespace:
    context = {}
    if thread_id is not None:
        context["thread_id"] = thread_id
    return SimpleNamespace(context=context, state={"thread_data": {}}, config={})


def test_install_skill_tool_installs_from_thread_virtual_path(monkeypatch, tmp_path):
    archive_path = tmp_path / "demo.skill"
    archive_path.write_text("placeholder")

    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: archive_path),
    )
    monkeypatch.setattr(
        install_skill_tool_module,
        "install_skill_archive",
        lambda path: SkillInstallResult(
            skill_name="demo-skill",
            message="Skill 'demo-skill' installed successfully",
        ),
    )

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/demo.skill",
    )

    assert result == "Skill 'demo-skill' installed successfully"


def test_install_skill_tool_accepts_runtime_auto_create_source(monkeypatch, tmp_path):
    archive_path = tmp_path / "demo.skill"
    archive_path.write_text("placeholder")

    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: archive_path),
    )
    monkeypatch.setattr(
        install_skill_tool_module,
        "install_skill_archive",
        lambda path: SkillInstallResult(
            skill_name="demo-skill",
            message="Skill 'demo-skill' installed successfully",
        ),
    )

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/demo.skill",
        source="runtime_auto_create",
        expected_skill_name="demo-skill",
    )

    assert result == "Skill 'demo-skill' installed successfully"


def test_install_skill_tool_rejects_expected_name_mismatch(monkeypatch, tmp_path):
    archive_path = tmp_path / "demo.skill"
    archive_path.write_text("placeholder")

    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: archive_path),
    )
    monkeypatch.setattr(
        install_skill_tool_module,
        "install_skill_archive",
        lambda path: SkillInstallResult(
            skill_name="other-skill",
            message="Skill 'other-skill' installed successfully",
        ),
    )

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/demo.skill",
        source="runtime_auto_create",
        expected_skill_name="demo-skill",
    )

    assert "did not match expected skill 'demo-skill'" in result


def test_install_skill_tool_requires_thread_id():
    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(thread_id=None),
        path="/mnt/user-data/outputs/demo.skill",
    )

    assert result == "Error: Thread ID is not available in runtime context"


def test_install_skill_tool_rejects_non_thread_virtual_path():
    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/tmp/demo.skill",
    )

    assert result == "Error: Path must start with /mnt/user-data"


def test_install_skill_tool_returns_business_error(monkeypatch, tmp_path):
    archive_path = tmp_path / "demo.skill"
    archive_path.write_text("placeholder")

    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: archive_path),
    )

    def raise_conflict(_path):
        raise SkillAlreadyExistsError("Skill 'demo-skill' already exists")

    monkeypatch.setattr(install_skill_tool_module, "install_skill_archive", raise_conflict)

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/demo.skill",
    )

    assert result == "Error: Skill 'demo-skill' already exists"


def test_install_skill_tool_returns_invalid_path_error(monkeypatch):
    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(
            resolve_virtual_path=lambda thread_id, path: (_ for _ in ()).throw(ValueError("Access denied: path traversal detected"))
        ),
    )

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/../demo.skill",
    )

    assert result == "Error: Access denied: path traversal detected"


def test_install_skill_tool_returns_invalid_archive_error(monkeypatch, tmp_path):
    archive_path = tmp_path / "demo.skill"
    archive_path.write_text("placeholder")

    monkeypatch.setattr(
        install_skill_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_virtual_path=lambda thread_id, path: archive_path),
    )

    def raise_invalid(_path):
        raise InvalidSkillArchiveError("File is not a valid ZIP archive")

    monkeypatch.setattr(install_skill_tool_module, "install_skill_archive", raise_invalid)

    result = install_skill_tool_module.install_skill_tool.func(
        runtime=_make_runtime(),
        path="/mnt/user-data/outputs/demo.skill",
    )

    assert result == "Error: File is not a valid ZIP archive"
