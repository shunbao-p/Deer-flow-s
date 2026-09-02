#!/usr/bin/env python3
"""Compare two eval detail CSVs on semantic fields only.

Does not print full questions, evidence text, or credentials.
Exit 0 when compared rows match on the required fields; exit 2 on diffs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


SEMANTIC_FIELDS = (
    "strategy",
    "law_hit",
    "law_hit_acceptable",
    "article_hit",
    "article_hit_acceptable",
    "evidence_mode",
    "route_fallback",
    "failed",
    "graph_fallback_to_traditional",
)

OPTIONAL_REFINE_FIELDS = (
    "refine_supported_count",
    "refine_weak_count",
    "refine_unsupported_count",
)


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _norm(value: Any) -> str:
    return str(value or "").strip()


def compare_rows(baseline: list[dict[str, str]], current: list[dict[str, str]]) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    compared = min(len(baseline), len(current))
    fields = list(SEMANTIC_FIELDS)
    if baseline and current:
        if all(name in baseline[0] and name in current[0] for name in OPTIONAL_REFINE_FIELDS):
            fields.extend(OPTIONAL_REFINE_FIELDS)
    for idx in range(compared):
        left = baseline[idx]
        right = current[idx]
        changed = {
            field: {"baseline": _norm(left.get(field)), "current": _norm(right.get(field))}
            for field in fields
            if _norm(left.get(field)) != _norm(right.get(field))
        }
        if changed:
            diffs.append({"index": _norm(left.get("index") or right.get("index") or idx + 1), "fields": changed})
    return {
        "baseline_rows": len(baseline),
        "current_rows": len(current),
        "compared_rows": compared,
        "row_count_mismatch": len(baseline) != len(current),
        "diff_count": len(diffs),
        "diffs": diffs,
        "compared_fields": fields,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two Legal eval detail CSVs.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = compare_rows(_load_rows(Path(args.baseline)), _load_rows(Path(args.current)))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    if report["row_count_mismatch"] or report["diff_count"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
