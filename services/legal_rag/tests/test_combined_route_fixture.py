"""S01 fixture: combined is still a first-class route, without changing the router."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

try:
    from rag_modules.intelligent_query_router import IntelligentQueryRouter, SearchStrategy
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in slim envs
    IntelligentQueryRouter = None
    SearchStrategy = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def test_rule_based_analysis_keeps_combined_path() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(str(_IMPORT_ERROR))
    fixture = ROOT / "data" / "eval" / "eval_questions_combined_fixture.jsonl"
    question = json.loads(fixture.read_text(encoding="utf-8").splitlines()[0])["question"]
    analysis = IntelligentQueryRouter._rule_based_analysis(object(), question)
    assert analysis.recommended_strategy == SearchStrategy.COMBINED
