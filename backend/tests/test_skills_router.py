import asyncio
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException

from app.gateway.routers.skills import SkillInstallRequest, install_skill
from deerflow.skills.installer import (
    InvalidSkillArchiveError,
    SkillAlreadyExistsError,
    SkillArchiveNotFoundError,
    SkillInstallResult,
    install_skill_archive,
)
from deerflow.skills.validation import _validate_skill_frontmatter

VALIDATE_SKILL_FRONTMATTER = cast(
    Callable[[Path], tuple[bool, str, str | None]],
    _validate_skill_frontmatter,
)


def _write_skill(skill_dir: Path, frontmatter: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(frontmatter, encoding="utf-8")


def _build_skill_archive(archive_path: Path, skill_dir_name: str, frontmatter: str) -> None:
    source_dir = archive_path.parent / f"{skill_dir_name}-src"
    _write_skill(source_dir, frontmatter)
    with zipfile.ZipFile(archive_path, "w") as zip_ref:
        zip_ref.write(source_dir / "SKILL.md", f"{skill_dir_name}/SKILL.md")


def test_validate_skill_frontmatter_allows_standard_optional_metadata(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    _write_skill(
        skill_dir,
        """---
name: demo-skill
description: Demo skill
version: 1.0.0
author: example.com/demo
compatibility: OpenClaw >= 1.0
license: MIT
---

# Demo Skill
""",
    )

    valid, message, skill_name = VALIDATE_SKILL_FRONTMATTER(skill_dir)

    assert valid is True
    assert message == "Skill is valid!"
    assert skill_name == "demo-skill"


def test_validate_skill_frontmatter_still_rejects_unknown_keys(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    _write_skill(
        skill_dir,
        """---
name: demo-skill
description: Demo skill
unsupported: true
---

# Demo Skill
""",
    )

    valid, message, skill_name = VALIDATE_SKILL_FRONTMATTER(skill_dir)

    assert valid is False
    assert "unsupported" in message
    assert skill_name is None


def test_validate_skill_frontmatter_reads_utf8_on_windows_locale(tmp_path, monkeypatch) -> None:
    skill_dir = tmp_path / "demo-skill"
    _write_skill(
        skill_dir,
        """---
name: demo-skill
description: "Curly quotes: \u201cutf8\u201d"
---

# Demo Skill
""",
    )

    original_read_text = Path.read_text

    def read_text_with_gbk_default(self, *args, **kwargs):
        kwargs.setdefault("encoding", "gbk")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_with_gbk_default)

    valid, message, skill_name = VALIDATE_SKILL_FRONTMATTER(skill_dir)

    assert valid is True
    assert message == "Skill is valid!"
    assert skill_name == "demo-skill"


def test_install_skill_archive_success(tmp_path: Path) -> None:
    archive_path = tmp_path / "demo-skill.skill"
    _build_skill_archive(
        archive_path,
        "demo-skill",
        """---
name: demo-skill
description: Demo skill
---

# Demo Skill
""",
    )

    skills_root = tmp_path / "skills"
    result = install_skill_archive(archive_path, skills_root=skills_root)

    assert result == SkillInstallResult(
        skill_name="demo-skill",
        message="Skill 'demo-skill' installed successfully",
    )
    assert (skills_root / "custom" / "demo-skill" / "SKILL.md").exists()


def test_install_skill_archive_rejects_unsafe_member_path(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.skill"
    with zipfile.ZipFile(archive_path, "w") as zip_ref:
        zip_ref.writestr("../escape.txt", "malicious")

    with pytest.raises(InvalidSkillArchiveError, match="unsafe member path"):
        install_skill_archive(archive_path, skills_root=tmp_path / "skills")


def test_install_skill_archive_rejects_missing_skill_md(tmp_path: Path) -> None:
    archive_path = tmp_path / "missing-skill-md.skill"
    with zipfile.ZipFile(archive_path, "w") as zip_ref:
        zip_ref.writestr("missing-skill-md/readme.txt", "hello")

    with pytest.raises(InvalidSkillArchiveError, match=r"Invalid skill: SKILL\.md not found"):
        install_skill_archive(archive_path, skills_root=tmp_path / "skills")


def test_install_skill_archive_rejects_duplicate_skill_name(tmp_path: Path) -> None:
    archive_path = tmp_path / "demo-skill.skill"
    _build_skill_archive(
        archive_path,
        "demo-skill",
        """---
name: demo-skill
description: Demo skill
---

# Demo Skill
""",
    )
    existing_dir = tmp_path / "skills" / "custom" / "demo-skill"
    existing_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(SkillAlreadyExistsError, match="already exists"):
        install_skill_archive(archive_path, skills_root=tmp_path / "skills")


@pytest.mark.parametrize(
    ("raised", "status_code"),
    [
        (SkillArchiveNotFoundError("Skill file not found: /mnt/user-data/outputs/demo.skill"), 404),
        (InvalidSkillArchiveError("File is not a valid ZIP archive"), 400),
        (SkillAlreadyExistsError("Skill 'demo-skill' already exists"), 409),
    ],
)
def test_install_skill_route_maps_business_errors(monkeypatch, raised, status_code: int) -> None:
    monkeypatch.setattr(
        "app.gateway.routers.skills.resolve_thread_virtual_path",
        lambda thread_id, virtual_path: Path("/tmp/demo.skill"),
    )

    def raise_error(_path: Path) -> SkillInstallResult:
        raise raised

    monkeypatch.setattr("app.gateway.routers.skills.install_skill_archive", raise_error)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(install_skill(SkillInstallRequest(thread_id="thread-1", path="/mnt/user-data/outputs/demo.skill")))

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == str(raised)
