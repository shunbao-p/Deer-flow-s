"""custom skill 生命周期的纯规则判断。

第一阶段只处理 ``skills/custom``，聚焦三个问题：

- 创建前是否已经存在同名或相近 skill
- 多个相近 skill 中应优先保留哪个
- 哪些较弱 skill 适合被建议停用
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LifecycleCheckOutcome(StrEnum):
    """创建前生命周期检查的稳定结果码。"""

    NO_MATCH = "no_match"
    SAME_NAME_EXISTS = "same_name_exists"
    SIMILAR_SKILL_EXISTS = "similar_skill_exists"
    MULTIPLE_SIMILAR_SKILLS_EXIST = "multiple_similar_skills_exist"


def _normalize_text(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return " ".join(cleaned.split())


def _tokenize(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split() if len(token) >= 2}


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _has_prefix_token_overlap(left: set[str], right: set[str]) -> bool:
    for left_token in left:
        for right_token in right:
            if (
                left_token == right_token
                or left_token.startswith(right_token)
                or right_token.startswith(left_token)
            ):
                return True
    return False


def _prefix_overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0

    matched: set[str] = set()
    for left_token in left:
        for right_token in right:
            if (
                left_token == right_token
                or left_token.startswith(right_token)
                or right_token.startswith(left_token)
            ):
                matched.add(left_token)
                break
    return len(matched) / max(len(left), len(right))


@dataclass(frozen=True)
class SkillLifecycleProfile:
    """用于生命周期判断的 skill 摘要。"""

    name: str
    description: str
    workflow_steps: tuple[str, ...] = ()
    usage_summary: str = ""
    skill_path: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class SkillSimilarityBreakdown:
    """候选 skill 与已有 skill 的相近性拆解。"""

    name_match: bool
    description_match: bool
    workflow_match: bool
    usage_match: bool

    @property
    def total_score(self) -> int:
        return sum(
            (
                self.name_match,
                self.description_match,
                self.workflow_match,
                self.usage_match,
            )
        )


@dataclass(frozen=True)
class LifecycleMatch:
    """某个已有 custom skill 与候选 skill 的匹配结果。"""

    profile: SkillLifecycleProfile
    similarity: SkillSimilarityBreakdown
    strength_score: int


@dataclass(frozen=True)
class LifecycleCheckResult:
    """创建前生命周期检查输出。"""

    outcome: LifecycleCheckOutcome
    primary_match: LifecycleMatch | None = None
    similar_matches: tuple[LifecycleMatch, ...] = ()
    disable_recommendations: tuple[str, ...] = ()
    reason: str = ""


def _description_match(candidate: SkillLifecycleProfile, existing: SkillLifecycleProfile) -> bool:
    left = _tokenize(candidate.description)
    right = _tokenize(existing.description)
    return _jaccard_similarity(left, right) >= 0.35 or _prefix_overlap_ratio(left, right) >= 0.5


def _workflow_match(candidate: SkillLifecycleProfile, existing: SkillLifecycleProfile) -> bool:
    left = {_normalize_text(step) for step in candidate.workflow_steps if step.strip()}
    right = {_normalize_text(step) for step in existing.workflow_steps if step.strip()}
    if not left or not right:
        return False
    return _jaccard_similarity(left, right) >= 0.5


def _usage_match(candidate: SkillLifecycleProfile, existing: SkillLifecycleProfile) -> bool:
    left = _tokenize(candidate.usage_summary)
    right = _tokenize(existing.usage_summary)
    return _jaccard_similarity(left, right) >= 0.5


def compare_skill_profiles(candidate: SkillLifecycleProfile, existing: SkillLifecycleProfile) -> LifecycleMatch:
    """比较候选 skill 与已有 skill 的相近程度。"""

    candidate_name = _normalize_text(candidate.name)
    existing_name = _normalize_text(existing.name)
    candidate_name_tokens = _tokenize(candidate.name)
    existing_name_tokens = _tokenize(existing.name)
    name_match = (
        candidate_name == existing_name
        or (candidate_name and candidate_name in existing_name)
        or (existing_name and existing_name in candidate_name)
        or _jaccard_similarity(candidate_name_tokens, existing_name_tokens) >= 0.6
        or _prefix_overlap_ratio(candidate_name_tokens, existing_name_tokens) >= 0.6
    )

    similarity = SkillSimilarityBreakdown(
        name_match=name_match,
        description_match=_description_match(candidate, existing),
        workflow_match=_workflow_match(candidate, existing),
        usage_match=_usage_match(candidate, existing),
    )

    strength_score = (
        len(existing.workflow_steps) * 3
        + min(len(_tokenize(existing.description)), 20)
        + min(len(_tokenize(existing.usage_summary)), 12)
        + (2 if existing.enabled else 0)
    )
    return LifecycleMatch(
        profile=existing,
        similarity=similarity,
        strength_score=strength_score,
    )


def _is_similar(match: LifecycleMatch) -> bool:
    if match.similarity.total_score >= 3:
        return True
    return match.similarity.total_score >= 2 and (
        match.similarity.workflow_match
        or match.similarity.usage_match
        or match.similarity.description_match
    )


def _match_sort_key(match: LifecycleMatch) -> tuple[int, int, int, str]:
    return (
        match.strength_score,
        match.similarity.total_score,
        1 if match.profile.enabled else 0,
        match.profile.name,
    )


def evaluate_skill_lifecycle(
    candidate: SkillLifecycleProfile,
    existing_custom_skills: list[SkillLifecycleProfile],
) -> LifecycleCheckResult:
    """在创建前评估 custom skill 生命周期动作。"""

    matches = [compare_skill_profiles(candidate, existing) for existing in existing_custom_skills]
    same_name_matches = [match for match in matches if _normalize_text(match.profile.name) == _normalize_text(candidate.name)]

    if same_name_matches:
        primary = max(same_name_matches, key=_match_sort_key)
        return LifecycleCheckResult(
            outcome=LifecycleCheckOutcome.SAME_NAME_EXISTS,
            primary_match=primary,
            similar_matches=tuple(sorted(same_name_matches, key=_match_sort_key, reverse=True)),
            reason="custom skill with the same name already exists",
        )

    similar_matches = [match for match in matches if _is_similar(match)]
    similar_matches.sort(key=_match_sort_key, reverse=True)

    if not similar_matches:
        return LifecycleCheckResult(
            outcome=LifecycleCheckOutcome.NO_MATCH,
            similar_matches=(),
            disable_recommendations=(),
            reason="no similar custom skill found",
        )

    primary = similar_matches[0]
    if len(similar_matches) == 1:
        return LifecycleCheckResult(
            outcome=LifecycleCheckOutcome.SIMILAR_SKILL_EXISTS,
            primary_match=primary,
            similar_matches=(primary,),
            disable_recommendations=(),
            reason="a similar custom skill already exists",
        )

    weaker_matches = tuple(match.profile.name for match in similar_matches[1:])
    return LifecycleCheckResult(
        outcome=LifecycleCheckOutcome.MULTIPLE_SIMILAR_SKILLS_EXIST,
        primary_match=primary,
        similar_matches=tuple(similar_matches),
        disable_recommendations=weaker_matches,
        reason="multiple similar custom skills already exist",
    )
