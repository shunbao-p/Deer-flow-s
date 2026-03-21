from deerflow.skills.loader import get_skills_root_path, load_skills


def test_runtime_tool_builder_is_discoverable_from_project_skills():
    skills = load_skills(skills_path=get_skills_root_path(), use_config=False, enabled_only=False)

    runtime_skill = next((skill for skill in skills if skill.name == "runtime-tool-builder"), None)

    assert runtime_skill is not None
    assert runtime_skill.category == "public"
    assert runtime_skill.skill_path == "runtime-tool-builder"


def test_runtime_tool_builder_instructions_include_tool_gap_and_registration_flow():
    skill_file = get_skills_root_path() / "public" / "runtime-tool-builder" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    assert "evaluate_tool_gap" in content
    assert "TOOL_GAP" in content
    assert "install_custom_mcp_server(" in content
    assert "register_custom_mcp_server(" in content
    assert 'source="runtime_auto_create"' in content
    assert "/mnt/user-data/workspace/runtime-tools/<tool-name>/" in content
    assert "Python" in content
    assert "stdio" in content


def test_python_mcp_template_contains_expected_files():
    template_root = get_skills_root_path().parent / "tool-templates" / "python-mcp-server"

    assert (template_root / "server.py").is_file()
    assert (template_root / "tool_impl.py").is_file()
    assert (template_root / "requirements.txt").is_file()
    assert (template_root / "README.md").is_file()
