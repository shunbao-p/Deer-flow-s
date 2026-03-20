"""custom skill 原地更新服务。"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from deerflow.skills import loader, validation


@dataclass(frozen=True)
class SkillUpdateResult:
    skill_name: str
    message: str


class SkillUpdateError(Exception):
    """custom skill 更新失败的业务异常基类。"""


class SkillUpdateSourceNotFoundError(SkillUpdateError):
    """更新源目录不存在。"""


class SkillUpdateTargetNotFoundError(SkillUpdateError):
    """目标 custom skill 不存在。"""


class InvalidSkillUpdateError(SkillUpdateError):
    """更新源目录不是有效 skill。"""


class SkillUpdateNameMismatchError(SkillUpdateError):
    """更新内容的 frontmatter 名称与目标 skill 不一致。"""


def update_custom_skill_from_directory(
    skill_name: str,
    source_dir: str | Path,
    *,
    skills_root: Path | None = None,
) -> SkillUpdateResult:
    """用工作区中的草稿目录原地替换已有 custom skill。"""

    source_path = Path(source_dir)
    if not source_path.exists() or not source_path.is_dir():
        raise SkillUpdateSourceNotFoundError(f"Skill update source directory not found: {source_dir}")

    resolved_skills_root = skills_root or loader.get_skills_root_path()
    skills = loader.load_skills(skills_path=resolved_skills_root, use_config=False, enabled_only=False)
    target_skill = next((skill for skill in skills if skill.category == "custom" and skill.name == skill_name), None)
    if target_skill is None:
        raise SkillUpdateTargetNotFoundError(f"Custom skill '{skill_name}' not found")

    is_valid, message, parsed_name = validation._validate_skill_frontmatter(source_path)
    if not is_valid:
        raise InvalidSkillUpdateError(f"Invalid skill update source: {message}")
    if parsed_name != skill_name:
        raise SkillUpdateNameMismatchError(
            f"Updated skill frontmatter name must remain '{skill_name}', got '{parsed_name}'"
        )

    parent_dir = target_skill.skill_dir.parent
    temp_root = Path(tempfile.mkdtemp(prefix=f".{target_skill.skill_dir.name}.update-", dir=parent_dir))
    staged_dir = temp_root / target_skill.skill_dir.name
    backup_dir = parent_dir / f".{target_skill.skill_dir.name}.backup-{uuid.uuid4().hex}"

    try:
        shutil.copytree(source_path, staged_dir)
        shutil.move(str(target_skill.skill_dir), str(backup_dir))
        shutil.move(str(staged_dir), str(target_skill.skill_dir))
    except Exception:
        if not target_skill.skill_dir.exists() and backup_dir.exists():
            shutil.move(str(backup_dir), str(target_skill.skill_dir))
        raise
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)

    return SkillUpdateResult(
        skill_name=skill_name,
        message=f"Skill '{skill_name}' updated successfully",
    )
