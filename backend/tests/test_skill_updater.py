from pathlib import Path

import pytest

from deerflow.skills.loader import load_skills
from deerflow.skills.updater import SkillUpdateNameMismatchError, update_custom_skill_from_directory


def _write_skill(skill_dir: Path, name: str, description: str, body: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_update_custom_skill_from_directory_replaces_existing_custom_skill(tmp_path: Path):
    skills_root = tmp_path / "skills"
    target_dir = skills_root / "custom" / "weather-helper"
    _write_skill(
        target_dir,
        "weather-helper",
        "Original description.",
        "# Weather Helper\n\n1. Original step.\n",
    )

    source_dir = tmp_path / "draft"
    _write_skill(
        source_dir,
        "weather-helper",
        "Updated description.",
        "# Weather Helper\n\n1. Updated step.\n2. Validation step.\n",
    )

    result = update_custom_skill_from_directory(
        "weather-helper",
        source_dir,
        skills_root=skills_root,
    )

    assert result.message == "Skill 'weather-helper' updated successfully"
    skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)
    updated = next(skill for skill in skills if skill.name == "weather-helper")
    content = updated.skill_file.read_text(encoding="utf-8")
    assert "Updated description." in content
    assert "Validation step." in content
    assert "Original step." not in content


def test_update_custom_skill_from_directory_rejects_name_mismatch(tmp_path: Path):
    skills_root = tmp_path / "skills"
    target_dir = skills_root / "custom" / "weather-helper"
    _write_skill(
        target_dir,
        "weather-helper",
        "Original description.",
        "# Weather Helper\n",
    )

    source_dir = tmp_path / "draft"
    _write_skill(
        source_dir,
        "weather-helper-v2",
        "Updated description.",
        "# Weather Helper V2\n",
    )

    with pytest.raises(SkillUpdateNameMismatchError):
        update_custom_skill_from_directory(
            "weather-helper",
            source_dir,
            skills_root=skills_root,
        )
