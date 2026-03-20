"""custom skill 生命周期的扫描与检查入口。"""

from __future__ import annotations

import re
from pathlib import Path

from deerflow.skills.loader import load_skills
from deerflow.skills.types import Skill

from .lifecycle_policy import LifecycleCheckResult, SkillLifecycleProfile, evaluate_skill_lifecycle

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_STEP_RE = re.compile(r"^(?:[-*]|\d+\.)\s+(.+)$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


def _strip_frontmatter(content: str) -> str:
    return _FRONTMATTER_RE.sub("", content, count=1)


def _extract_workflow_steps(body: str) -> tuple[str, ...]:
    steps: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _STEP_RE.match(line)
        if match:
            steps.append(match.group(1).strip())
    return tuple(steps[:12])


def _extract_usage_summary(body: str) -> str:
    collected: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            title = heading.group(1).strip().lower()
            if any(keyword in title for keyword in ("use", "when", "input", "output", "trigger", "scope")):
                collected.append(heading.group(1).strip())
                continue
        if line.lower().startswith(("use ", "when ", "input", "output", "trigger", "scope", "goal")):
            collected.append(line)
        if len(collected) >= 6:
            break
    return " ".join(collected)


def build_lifecycle_profile(skill: Skill) -> SkillLifecycleProfile:
    """从 skill 文件构建生命周期比较所需的摘要。"""

    content = skill.skill_file.read_text(encoding="utf-8")
    body = _strip_frontmatter(content)
    return SkillLifecycleProfile(
        name=skill.name,
        description=skill.description,
        workflow_steps=_extract_workflow_steps(body),
        usage_summary=_extract_usage_summary(body),
        skill_path=skill.skill_path,
        enabled=skill.enabled,
    )


def load_custom_skill_profiles(skills_path: Path | None = None, *, use_config: bool = True) -> list[SkillLifecycleProfile]:
    """加载所有 custom skill 的生命周期摘要。"""

    skills = load_skills(skills_path=skills_path, use_config=use_config, enabled_only=False)
    profiles: list[SkillLifecycleProfile] = []
    for skill in skills:
        if skill.category != "custom":
            continue
        profiles.append(build_lifecycle_profile(skill))
    profiles.sort(key=lambda profile: profile.name)
    return profiles


def evaluate_custom_skill_candidate(
    *,
    name: str,
    description: str,
    workflow: str = "",
    input_output: str = "",
    skills_path: Path | None = None,
    use_config: bool = True,
) -> LifecycleCheckResult:
    """对候选 custom skill 执行创建前重复检查。"""

    workflow_steps = _extract_workflow_steps(workflow)
    usage_summary = _extract_usage_summary(workflow)
    if input_output.strip():
        usage_summary = f"{usage_summary} {input_output}".strip()

    candidate = SkillLifecycleProfile(
        name=name,
        description=description,
        workflow_steps=workflow_steps,
        usage_summary=usage_summary,
        skill_path=None,
        enabled=True,
    )
    existing = load_custom_skill_profiles(skills_path=skills_path, use_config=use_config)
    return evaluate_skill_lifecycle(candidate, existing)
