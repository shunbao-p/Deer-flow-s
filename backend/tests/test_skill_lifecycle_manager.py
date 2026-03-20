from pathlib import Path

from deerflow.skills.lifecycle_manager import (
    build_lifecycle_profile,
    evaluate_custom_skill_candidate,
    load_custom_skill_profiles,
)
from deerflow.skills.lifecycle_policy import LifecycleCheckOutcome
from deerflow.skills.loader import load_skills


def _write_skill(skill_dir: Path, name: str, description: str, body: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_build_lifecycle_profile_extracts_workflow_and_usage(tmp_path: Path):
    skills_root = tmp_path / "skills"
    custom_dir = skills_root / "custom" / "weather-helper"
    _write_skill(
        custom_dir,
        "weather-helper",
        "Generate a weather report from city input.",
        """
# Weather Helper

## When To Use
Use this skill when the user asks for a weather report from a city.

1. Collect the city.
2. Call the weather provider.
3. Format the report.
""",
    )

    skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)
    skill = next(item for item in skills if item.name == "weather-helper")

    profile = build_lifecycle_profile(skill)

    assert profile.workflow_steps == (
        "Collect the city.",
        "Call the weather provider.",
        "Format the report.",
    )
    assert "Use this skill when the user asks for a weather report" in profile.usage_summary


def test_load_custom_skill_profiles_ignores_public_skills(tmp_path: Path):
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "public" / "public-one", "public-one", "A public skill.", "# Public\n")
    _write_skill(skills_root / "custom" / "custom-one", "custom-one", "A custom skill.", "# Custom\n")

    profiles = load_custom_skill_profiles(skills_path=skills_root, use_config=False)

    assert [profile.name for profile in profiles] == ["custom-one"]


def test_evaluate_custom_skill_candidate_detects_existing_similar_custom_skill(tmp_path: Path):
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root / "custom" / "weather-helper",
        "weather-helper",
        "Generate a weather report from city input and format the output.",
        """
# Weather Helper

## When To Use
Use this skill when the user asks for a weather report from a city.

1. Collect the city.
2. Call the weather provider.
3. Format the report.
""",
    )

    result = evaluate_custom_skill_candidate(
        name="weather-reporter",
        description="Generate a formatted weather report from city input.",
        workflow="""
1. Collect the city.
2. Call the weather provider.
3. Format the report.
""",
        input_output="input: city; output: formatted weather report",
        skills_path=skills_root,
        use_config=False,
    )

    assert result.outcome == LifecycleCheckOutcome.SIMILAR_SKILL_EXISTS
    assert result.primary_match is not None
    assert result.primary_match.profile.name == "weather-helper"
