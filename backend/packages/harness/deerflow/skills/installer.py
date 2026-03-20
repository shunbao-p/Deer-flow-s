"""Shared skill installation service.

Pure business logic for installing a ``.skill`` archive into ``skills/custom``.
This module intentionally has no FastAPI or frontend dependencies so it can be
reused by the Gateway API, the embedded client, and future bridge tools.
"""

from __future__ import annotations

import logging
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from deerflow.skills import loader, validation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillInstallResult:
    skill_name: str
    message: str


class SkillInstallError(Exception):
    """Base exception for business-level skill installation failures."""


class SkillArchiveNotFoundError(FileNotFoundError, SkillInstallError):
    """Raised when the requested archive path does not exist."""


class InvalidSkillArchiveError(ValueError, SkillInstallError):
    """Raised when the archive exists but fails validation or extraction."""


class SkillAlreadyExistsError(ValueError, SkillInstallError):
    """Raised when the target skill name already exists in custom skills."""


def _is_unsafe_zip_member(info: zipfile.ZipInfo) -> bool:
    """Return True if the zip member path is absolute or attempts traversal."""
    name = info.filename
    if not name:
        return False
    path = Path(name)
    return path.is_absolute() or ".." in path.parts


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    """Detect symlinks using Unix file mode bits embedded in ZipInfo."""
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _should_ignore_archive_entry(path: Path) -> bool:
    return path.name.startswith(".") or path.name == "__MACOSX"


def _resolve_skill_dir_from_archive_root(temp_path: Path) -> Path:
    extracted_items = [item for item in temp_path.iterdir() if not _should_ignore_archive_entry(item)]
    if len(extracted_items) == 0:
        raise InvalidSkillArchiveError("Skill archive is empty")
    if len(extracted_items) == 1 and extracted_items[0].is_dir():
        return extracted_items[0]
    return temp_path


def _safe_extract_skill_archive(
    zip_ref: zipfile.ZipFile,
    dest_path: Path,
    max_total_size: int = 512 * 1024 * 1024,
) -> None:
    """Safely extract a skill archive into ``dest_path`` with basic protections."""
    dest_root = Path(dest_path).resolve()
    total_size = 0

    for info in zip_ref.infolist():
        if _is_unsafe_zip_member(info):
            raise InvalidSkillArchiveError(f"Archive contains unsafe member path: {info.filename!r}")

        if _is_symlink_member(info):
            logger.warning("Skipping symlink entry in skill archive: %s", info.filename)
            continue

        total_size += max(info.file_size, 0)
        if total_size > max_total_size:
            raise InvalidSkillArchiveError("Skill archive is too large or appears highly compressed.")

        member_path = dest_root / info.filename
        member_path.parent.mkdir(parents=True, exist_ok=True)

        if info.is_dir():
            member_path.mkdir(parents=True, exist_ok=True)
            continue

        with zip_ref.open(info) as src, open(member_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def install_skill_archive(skill_path: str | Path, skills_root: Path | None = None) -> SkillInstallResult:
    """Install a ``.skill`` archive into the custom skills directory."""
    path = Path(skill_path)
    display_path = str(skill_path)

    if not path.exists():
        raise SkillArchiveNotFoundError(f"Skill file not found: {display_path}")
    if not path.is_file():
        raise InvalidSkillArchiveError(f"Path is not a file: {display_path}")
    if path.suffix != ".skill":
        raise InvalidSkillArchiveError("File must have .skill extension")
    if not zipfile.is_zipfile(path):
        raise InvalidSkillArchiveError("File is not a valid ZIP archive")

    resolved_skills_root = skills_root or loader.get_skills_root_path()
    custom_skills_dir = resolved_skills_root / "custom"
    custom_skills_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        with zipfile.ZipFile(path, "r") as zip_ref:
            _safe_extract_skill_archive(zip_ref, temp_path)

        skill_dir = _resolve_skill_dir_from_archive_root(temp_path)

        is_valid, message, skill_name = validation._validate_skill_frontmatter(skill_dir)
        if not is_valid:
            raise InvalidSkillArchiveError(f"Invalid skill: {message}")
        if not skill_name:
            raise InvalidSkillArchiveError("Could not determine skill name")

        target_dir = custom_skills_dir / skill_name
        if target_dir.exists():
            raise SkillAlreadyExistsError(
                f"Skill '{skill_name}' already exists. Please remove it first or use a different name."
            )

        shutil.copytree(skill_dir, target_dir)

    return SkillInstallResult(
        skill_name=skill_name,
        message=f"Skill '{skill_name}' installed successfully",
    )
