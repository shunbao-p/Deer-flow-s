#!/usr/bin/env bash
# Resume remaining Legal RAG live gates in order. Never starts empty DBs.
set -euo pipefail

DEER_ROOT="${DEER_ROOT:-/Users/yuh/Desktop/项目/Deer-flow-s}"
SOURCE_API="${LEGAL_SOURCE_BASE_URL:-http://127.0.0.1:8000}"
AUGMENT_API="${LEGAL_RAG_BASE_URL:-http://127.0.0.1:8003}"

ready() {
  local url="$1"
  curl -fsS --max-time 5 "${url}/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("status")=="ready" or d.get("system_ready") else 2)'
}

echo "=== remaining live resume ==="
if ready "${SOURCE_API}"; then
  echo "S01 source API ready: ${SOURCE_API}"
  "${DEER_ROOT}/.omx/plans/artifacts/s01/run_s01_live.sh"
else
  echo "S01 blocked: ${SOURCE_API}/health is not ready."
  echo "Start existing Neo4j + Milvus + source Legal API first. Do not compose up empty volumes."
  exit 2
fi

if ready "${AUGMENT_API}"; then
  echo "S07 augment API ready: ${AUGMENT_API}"
  "${DEER_ROOT}/.omx/plans/artifacts/s07/run_s07_live.sh"
else
  echo "S07 blocked: ${AUGMENT_API}/health is not ready. Start services/legal_rag against the same existing DBs."
  exit 3
fi

echo "Live eval scripts finished. Six-scene real-LLM Deer dialogue still needs lead_agent + LEGAL_RAG_LIVE=1."
