from __future__ import annotations

import sys
import types
from pathlib import Path

if "requests" not in sys.modules:
    sys.modules["requests"] = types.ModuleType("requests")

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import compare_eval_runs  # noqa: E402
import run_eval  # noqa: E402


def test_augment_request_has_no_session():
    payload = run_eval.build_eval_request(
        "q",
        api_mode="augment",
        eval_batch_id="s07",
        eval_fast_mode=False,
        chat_id="should-not-appear",
    )
    assert payload["contract_version"] == "v1"
    assert payload["question"] == "q"
    assert "chat_id" not in payload
    assert run_eval.eval_request_path("augment") == "/v1/augment"


def test_legacy_chat_request_keeps_source_shape():
    payload = run_eval.build_eval_request(
        "q",
        api_mode="chat",
        eval_batch_id="s01",
        eval_fast_mode=True,
        chat_id="chat-1",
    )
    assert payload == {
        "chat_id": "chat-1",
        "question": "q",
        "explain_routing": False,
        "eval_batch_id": "s01",
        "eval_fast_mode": True,
    }
    assert run_eval.eval_request_path("chat") == "/chat"


def test_refine_counts_prefer_payload_then_verdicts():
    from_counts = run_eval.extract_refine_counts(
        {"supported_count": 2, "weak_count": 1, "unsupported_count": 0, "refined_claim_count": 3}
    )
    assert from_counts["refine_supported_count"] == 2
    from_claims = run_eval.extract_refine_counts(
        {"claims": [{"verdict": "supported"}, {"verdict": "unsupported"}, {"verdict": "weak"}]}
    )
    assert from_claims == {
        "refine_supported_count": 1,
        "refine_weak_count": 1,
        "refine_unsupported_count": 1,
        "refine_claim_count": 3,
    }


def test_compare_eval_runs_flags_semantic_diffs(tmp_path):
    header = "index,strategy,law_hit,law_hit_acceptable,article_hit,article_hit_acceptable,evidence_mode,route_fallback,failed,graph_fallback_to_traditional\n"
    baseline = tmp_path / "base.csv"
    current = tmp_path / "cur.csv"
    baseline.write_text(header + "1,hybrid_traditional,1,1,1,1,strong,,0,0\n", encoding="utf-8")
    current.write_text(header + "1,graph_rag,1,1,1,1,strong,,0,0\n", encoding="utf-8")
    report = compare_eval_runs.compare_rows(
        compare_eval_runs._load_rows(baseline),
        compare_eval_runs._load_rows(current),
    )
    assert report["diff_count"] == 1
    assert "strategy" in report["diffs"][0]["fields"]
