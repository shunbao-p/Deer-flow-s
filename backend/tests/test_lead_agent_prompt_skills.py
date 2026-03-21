from pathlib import Path

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.config.app_config import AppConfig
from deerflow.skills.types import Skill


def _make_app_config(*, auto_create_enabled: bool) -> AppConfig:
    return AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "skills": {
                "container_path": "/mnt/skills",
                "auto_create_enabled": auto_create_enabled,
            },
        }
    )


def _make_skill(name: str, description: str, *, category: str = "public") -> Skill:
    skill_dir = Path("/tmp") / name
    return Skill(
        name=name,
        description=description,
        license=None,
        skill_dir=skill_dir,
        skill_file=skill_dir / "SKILL.md",
        relative_path=Path(name),
        category=category,
        enabled=True,
    )


def test_skills_prompt_includes_runtime_creation_policy_when_enabled(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "load_skills",
        lambda enabled_only=True: [
            _make_skill("analysis-helper", "Existing analysis workflow"),
            _make_skill("runtime-skill-builder", "Build and install runtime skills"),
            _make_skill("runtime-tool-builder", "Build and register runtime tools"),
        ],
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = prompt_module.get_skills_prompt_section()

    assert "Custom Skill Lifecycle Policy" in result
    assert "call `evaluate_skill_lifecycle`" in result
    assert "`enable_skill`" in result
    assert "update it in place via `update_custom_skill`" in result
    assert "Runtime Skill Creation Policy" in result
    assert "First check whether an existing skill already covers the task" in result
    assert "If the lifecycle result is not `no_match`, do not create a new near-duplicate skill" in result
    assert "call `evaluate_skill_creation` with concrete signals" in result
    assert "load `runtime-skill-builder` via `read_file`" in result
    assert "/mnt/skills/public/runtime-skill-builder/SKILL.md" in result
    assert "Runtime Tool Creation Policy" in result
    assert "call `evaluate_tool_gap`" in result
    assert "temporary bash/python script is not automatically equivalent to a formally registered tool" in result
    assert "load `runtime-tool-builder` via `read_file`" in result
    assert "install_custom_mcp_server" in result
    assert "register_custom_mcp_server" in result


def test_skills_prompt_forbids_auto_creation_when_disabled(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "load_skills",
        lambda enabled_only=True: [
            _make_skill("analysis-helper", "Existing analysis workflow"),
            _make_skill("runtime-skill-builder", "Build and install runtime skills"),
            _make_skill("runtime-tool-builder", "Build and register runtime tools"),
        ],
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: _make_app_config(auto_create_enabled=False),
    )

    result = prompt_module.get_skills_prompt_section()

    assert "Custom Skill Lifecycle Policy" in result
    assert "call `evaluate_skill_lifecycle`" in result
    assert "`enable_skill`" in result
    assert "Runtime skill auto-creation is disabled" in result
    assert "Never create or install a new skill automatically" in result
    assert "load `runtime-skill-builder` via `read_file`" not in result
    assert "Runtime Tool Creation Policy" in result
    assert "call `evaluate_tool_gap`" in result


def test_skills_prompt_does_not_improvise_without_runtime_builder(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "load_skills",
        lambda enabled_only=True: [
            _make_skill("analysis-helper", "Existing analysis workflow"),
        ],
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = prompt_module.get_skills_prompt_section()

    assert "call `evaluate_skill_lifecycle`" in result
    assert "`enable_skill`" in result
    assert "If no `runtime-skill-builder` skill is available" in result
    assert "call `evaluate_skill_creation` with concrete signals" in result
    assert "do not improvise a replacement creation flow" in result


def test_skills_prompt_does_not_improvise_without_runtime_tool_builder(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "load_skills",
        lambda enabled_only=True: [
            _make_skill("analysis-helper", "Existing analysis workflow"),
        ],
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = prompt_module.get_skills_prompt_section()

    assert "Runtime Tool Creation Policy" in result
    assert "call `evaluate_tool_gap`" in result
    assert "temporary bash/python script is not automatically equivalent to a formally registered tool" in result
    assert "If no `runtime-tool-builder` skill is available" in result
    assert "do not improvise a replacement runtime tool creation flow" in result


def test_skills_prompt_keeps_policy_when_no_enabled_skills(monkeypatch):
    monkeypatch.setattr(prompt_module, "load_skills", lambda enabled_only=True: [])
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: _make_app_config(auto_create_enabled=True),
    )

    result = prompt_module.get_skills_prompt_section()

    assert "Custom Skill Lifecycle Policy" in result
    assert "Runtime Skill Creation Policy" in result
    assert "No enabled skills are currently available." in result
    assert "`enable_skill`" in result
    assert "evaluate_skill_lifecycle" in result
    assert "evaluate_skill_creation" in result
    assert "evaluate_tool_gap" in result
