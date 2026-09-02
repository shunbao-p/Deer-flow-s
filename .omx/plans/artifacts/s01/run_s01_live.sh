#!/usr/bin/env bash
# Run S01 live gates only when an existing Legal stack is already ready.
# This script never starts docker compose, never creates volumes, and never ingests.
set -euo pipefail

SOURCE_ROOT="${LEGAL_SOURCE_ROOT:-/Users/yuh/Desktop/项目/Legal-consulting-expert}"
DEER_ROOT="${DEER_ROOT:-/Users/yuh/Desktop/项目/Deer-flow-s}"
BASE_URL="${LEGAL_SOURCE_BASE_URL:-http://127.0.0.1:8000}"
OUT_DIR="${DEER_ROOT}/.omx/plans/artifacts/s01"
EVAL_PY="${DEER_ROOT}/services/legal_rag/scripts/eval/run_eval.py"
INVENTORY_PY="${OUT_DIR}/readonly_db_inventory.py"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

resolve_python() {
  local candidate
  for candidate in \
    "${LEGAL_PYTHON:-}" \
    "${SOURCE_ROOT}/.venv/bin/python" \
    "${DEER_ROOT}/services/legal_rag/.venv/bin/python" \
    python3; do
    if [ -n "${candidate}" ] && command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
    if [ -x "${candidate}" ]; then
      echo "${candidate}"
      return 0
    fi
  done
  echo "python3"
}

need curl
PYTHON_BIN="$(resolve_python)"
if ! "${PYTHON_BIN}" -c "import requests" >/dev/null 2>&1; then
  echo "S01 blocked: ${PYTHON_BIN} has no requests. Use LEGAL_PYTHON=... pointing at the Legal runtime venv." >&2
  exit 1
fi

if ! curl -fsS --max-time 5 "${BASE_URL}/health" | "${PYTHON_BIN}" -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("status")=="ready" or d.get("system_ready") else 2)'; then
  echo "S01 blocked: ${BASE_URL}/health is not ready. Start the existing Legal API and databases first." >&2
  echo "Do not docker compose up empty Neo4j/Milvus volumes." >&2
  exit 2
fi

mkdir -p "${OUT_DIR}"
set +e
"${PYTHON_BIN}" "${INVENTORY_PY}" "${OUT_DIR}/db_inventory.json"
inventory_rc=$?
set -e
if [ "${inventory_rc}" -ne 0 ]; then
  echo "S01 inventory incomplete (exit ${inventory_rc}); continue eval against ready API. Do not rebuild databases."
fi

"${PYTHON_BIN}" "${EVAL_PY}" \
  --api-mode chat \
  --base-url "${BASE_URL}" \
  --dataset "${SOURCE_ROOT}/data/eval/eval_questions_v1_top10.jsonl" \
  --output-dir "${OUT_DIR}" \
  --eval-batch-id s01-top10 \
  --warmup-mode light \
  --skip-db-validate

"${PYTHON_BIN}" "${EVAL_PY}" \
  --api-mode chat \
  --base-url "${BASE_URL}" \
  --dataset "${SOURCE_ROOT}/data/eval/eval_questions_v1_full50.jsonl" \
  --output-dir "${OUT_DIR}" \
  --eval-batch-id s01-full50 \
  --warmup-mode light \
  --skip-db-validate

echo "S01 live artifacts written under ${OUT_DIR}"
