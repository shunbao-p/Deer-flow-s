from deerflow.skills.lifecycle_policy import (
    LifecycleCheckOutcome,
    SkillLifecycleProfile,
    compare_skill_profiles,
    evaluate_skill_lifecycle,
)


def _profile(
    name: str,
    description: str,
    *,
    workflow_steps: tuple[str, ...] = (),
    usage_summary: str = "",
    enabled: bool = True,
    skill_path: str | None = None,
) -> SkillLifecycleProfile:
    return SkillLifecycleProfile(
        name=name,
        description=description,
        workflow_steps=workflow_steps,
        usage_summary=usage_summary,
        enabled=enabled,
        skill_path=skill_path,
    )


def test_compare_skill_profiles_marks_high_overlap_as_similar():
    candidate = _profile(
        "weather-report-skill",
        "Generate a weather report from city input and format the result.",
        workflow_steps=("collect city", "call weather provider", "format report"),
        usage_summary="use when the user needs a weather report from a city input",
    )
    existing = _profile(
        "weather-reporter",
        "Generate a formatted weather report for a city request.",
        workflow_steps=("collect city", "call weather provider", "format report"),
        usage_summary="use when the task asks for a weather report from a city input",
    )

    match = compare_skill_profiles(candidate, existing)

    assert match.similarity.name_match is True
    assert match.similarity.description_match is True
    assert match.similarity.workflow_match is True
    assert match.similarity.usage_match is True
    assert match.similarity.total_score == 4


def test_evaluate_skill_lifecycle_returns_same_name_when_name_exists():
    candidate = _profile("weather-report", "Format weather results for a city request.")
    existing = [
        _profile(
            "weather-report",
            "A custom weather reporting workflow.",
            workflow_steps=("collect city", "format report"),
            skill_path="weather-report",
        )
    ]

    result = evaluate_skill_lifecycle(candidate, existing)

    assert result.outcome == LifecycleCheckOutcome.SAME_NAME_EXISTS
    assert result.primary_match is not None
    assert result.primary_match.profile.name == "weather-report"


def test_evaluate_skill_lifecycle_returns_no_match_when_profiles_are_distinct():
    candidate = _profile(
        "meeting-summary",
        "Summarize meeting notes into decisions and action items.",
        workflow_steps=("read notes", "extract decisions", "write summary"),
        usage_summary="use when the user wants a meeting summary",
    )
    existing = [
        _profile(
            "weather-report",
            "Generate a weather report for a city request.",
            workflow_steps=("collect city", "call weather provider", "format report"),
            usage_summary="use when the task asks for a weather report",
        )
    ]

    result = evaluate_skill_lifecycle(candidate, existing)

    assert result.outcome == LifecycleCheckOutcome.NO_MATCH
    assert result.primary_match is None
    assert result.disable_recommendations == ()


def test_evaluate_skill_lifecycle_returns_primary_and_disable_recommendations_for_multiple_similar():
    candidate = _profile(
        "weather-report",
        "Generate a weather report from a city request and return a structured summary.",
        workflow_steps=("collect city", "call weather provider", "format report"),
        usage_summary="use when the user asks for a weather report",
    )
    existing = [
        _profile(
            "weather-helper",
            "Generate a weather report from a city request and include summary details.",
            workflow_steps=("collect city", "call weather provider", "format report", "add summary"),
            usage_summary="use when the user asks for a weather report",
            enabled=True,
            skill_path="weather-helper",
        ),
        _profile(
            "weather-quick",
            "Generate a weather report for city input.",
            workflow_steps=("collect city", "format report"),
            usage_summary="use when the user asks for a weather report",
            enabled=False,
            skill_path="weather-quick",
        ),
    ]

    result = evaluate_skill_lifecycle(candidate, existing)

    assert result.outcome == LifecycleCheckOutcome.MULTIPLE_SIMILAR_SKILLS_EXIST
    assert result.primary_match is not None
    assert result.primary_match.profile.name == "weather-helper"
    assert result.disable_recommendations == ("weather-quick",)
