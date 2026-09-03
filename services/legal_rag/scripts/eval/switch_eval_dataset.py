#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def count_lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch active eval dataset between top10 and full50.")
    parser.add_argument("target", choices=["10", "50", "status"], help="10 / 50 / status")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    eval_dir = root / "data" / "eval"
    active = eval_dir / "eval_questions_v1.jsonl"
    top10 = eval_dir / "eval_questions_v1_top10.jsonl"
    full50 = eval_dir / "eval_questions_v1_full50.jsonl"

    for path in (active, top10, full50):
        if not path.exists():
            raise FileNotFoundError(f"dataset file missing: {path}")

    if args.target == "status":
        print(f"[eval-switch] active: {active.name} ({count_lines(active)} rows)")
        print(f"[eval-switch] option10: {top10.name} ({count_lines(top10)} rows)")
        print(f"[eval-switch] option50: {full50.name} ({count_lines(full50)} rows)")
        return 0

    source = top10 if args.target == "10" else full50
    shutil.copy2(source, active)
    print(f"[eval-switch] switched to {args.target} rows via {source.name}")
    print(f"[eval-switch] active now: {active.name} ({count_lines(active)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
