from pathlib import Path

import pytest

from deerflow.skills.installer import InvalidSkillArchiveError, _resolve_skill_dir_from_archive_root


def _write_skill(skill_dir: Path) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: demo-skill
description: Demo skill
---

# Demo Skill
""",
        encoding="utf-8",
    )


def test_resolve_skill_dir_ignores_macosx_wrapper(tmp_path: Path) -> None:
    _write_skill(tmp_path / "demo-skill")
    (tmp_path / "__MACOSX").mkdir()

    assert _resolve_skill_dir_from_archive_root(tmp_path) == tmp_path / "demo-skill"


def test_resolve_skill_dir_ignores_hidden_top_level_entries(tmp_path: Path) -> None:
    _write_skill(tmp_path / "demo-skill")
    (tmp_path / ".DS_Store").write_text("metadata", encoding="utf-8")

    assert _resolve_skill_dir_from_archive_root(tmp_path) == tmp_path / "demo-skill"


def test_resolve_skill_dir_rejects_archive_with_only_metadata(tmp_path: Path) -> None:
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / ".DS_Store").write_text("metadata", encoding="utf-8")

    with pytest.raises(InvalidSkillArchiveError) as error:
        _resolve_skill_dir_from_archive_root(tmp_path)

    assert str(error.value) == "Skill archive is empty"
