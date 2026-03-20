from deerflow.skills.loader import get_skills_root_path, load_skills


def test_runtime_skill_builder_is_discoverable_from_project_skills():
    skills = load_skills(skills_path=get_skills_root_path(), use_config=False, enabled_only=False)

    runtime_skill = next((skill for skill in skills if skill.name == "runtime-skill-builder"), None)

    assert runtime_skill is not None
    assert runtime_skill.category == "public"
    assert runtime_skill.skill_path == "runtime-skill-builder"


def test_runtime_skill_builder_instructions_include_guardrails_and_install_flow():
    skill_file = get_skills_root_path() / "public" / "runtime-skill-builder" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    assert "Do not use for one-off, temporary, ambiguous" in content
    assert "Never write directly into `skills/custom`" in content
    assert "evaluate_skill_lifecycle" in content
    assert "evaluate_skill_creation" in content
    assert "enable_skill" in content
    assert "update_custom_skill" in content
    assert "install_skill(" in content
    assert 'source="runtime_auto_create"' in content
    assert 'expected_skill_name="<skill-name>"' in content
    assert "/mnt/user-data/outputs/runtime-skills/<skill-name>.skill" in content
    assert "package_skill.py" in content
