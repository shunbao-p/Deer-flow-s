#!/usr/bin/env bash
# S07 live gates: /v1/augment eval + optional compare against S01.
# Never starts empty Neo4j/Milvus and never ingests.
set -euo pipefail

DEER_ROOT="${DEER_ROOT:-/Users/yuh/Desktop/项目/Deer-flow-s}"
BASE_URL="${LEGAL_RAG_BASE_URL:-http://127.0.0.1:8003}"
OUT_DIR="${DEER_ROOT}/.omx/plans/artifacts/s07"
S01_DIR="${DEER_ROOT}/.omx/plans/artifacts/s01"
EVAL_PY="${DEER_ROOT}/services/legal_rag/scripts/eval/run_eval.py"
COMPARE_PY="${DEER_ROOT}/services/legal_rag/scripts/eval/compare_eval_runs.py"
DATASET_DIR="${DEER_ROOT}/services/legal_rag/data/eval"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

need curl
need python3

if ! curl -fsS --max-time 5 "${BASE_URL}/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("status")=="ready" or d.get("system_ready") else 2)'; then
  echo "S07 blocked: ${BASE_URL}/health is not ready." >&2
  exit 2
fi

mkdir -p "${OUT_DIR}"

python3 "${EVAL_PY}" \
  --api-mode augment \
  --base-url "${BASE_URL}" \
  --dataset "${DATASET_DIR}/eval_questions_v1_top10.jsonl" \
  --output-dir "${OUT_DIR}" \
  --eval-batch-id s07-top10 \
  --warmup-mode light \
  --skip-db-validate

python3 "${EVAL_PY}" \
  --api-mode augment \
  --base-url "${BASE_URL}" \
  --dataset "${DATASET_DIR}/eval_questions_v1_full50.jsonl" \
  --output-dir "${OUT_DIR}" \
  --eval-batch-id s07-full50 \
  --warmup-mode light \
  --skip-db-validate

if ls "${S01_DIR}"/metrics_detail_v1*.csv >/dev/null 2>&1; then
  python3 "${COMPARE_PY}" \
    --baseline "$(ls -1 "${S01_DIR}"/metrics_detail_v1*.csv | tail -n 1)" \
    --current "$(ls -1 "${OUT_DIR}"/metrics_detail_v1*.csv | tail -n 1)" \
    --output "${OUT_DIR}/compare_latest.json" || true
else
  echo "S01 detail CSV not found; skip compare. Finish S01 live first."
fi

echo "S07 live artifacts written under ${OUT_DIR}"
echo "Six-scene Deer conversation still requires a running lead_agent + LEGAL_RAG_LIVE=1."
