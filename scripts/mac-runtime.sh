#!/usr/bin/env bash
# This Mac's stable Deer runtime. Use this instead of `make dev` / `make stop`.
#
# Why not the official scripts:
#   - `make stop` / serve.sh run `pkill next-server` and kill the :3000 3d-portfolio
#   - `make dev` expects `python`, frontend :3000, and Turbopack (ChunkLoadError after a while)
#   - Legal graph must NOT be recreated (`docker compose up --build` can cost ~15 min)
#
# Topology:
#   browser :2026 → nginx → frontend :3001 (next start)
#                            gateway  :8001
#                            langgraph:2024
#   legal   :8003  existing container deer-flow-legal-rag → Windows Neo4j/Milvus
#
# Usage:
#   ./scripts/mac-runtime.sh start
#   ./scripts/mac-runtime.sh stop          # Deer only; Legal stays up
#   ./scripts/mac-runtime.sh stop --legal  # also stop Legal container (no wipe)
#   ./scripts/mac-runtime.sh status

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NGINX_BIN="${NGINX_BIN:-/opt/homebrew/bin/nginx}"
NGINX_CONF="$REPO_ROOT/docker/nginx/nginx.local.3001.conf"
LEGAL_CONTAINER="${LEGAL_CONTAINER:-deer-flow-legal-rag}"
FRONTEND_PORT=3001
FORBIDDEN_PORT=3000

cmd="${1:-}"
shift || true

STOP_LEGAL=false
for arg in "$@"; do
    case "$arg" in
        --legal) STOP_LEGAL=true ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done

port_pids() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | sort -u || true
}

http_code() {
    curl -sS -o /dev/null -w '%{http_code}' --max-time "${2:-5}" "$1" 2>/dev/null || echo '000'
}

assert_not_touching_3000() {
    if lsof -nP -iTCP:"$FORBIDDEN_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "  keep :$FORBIDDEN_PORT (other project) untouched"
    fi
}

ensure_prereqs() {
    local missing=0
    for bin in uv pnpm docker curl lsof; do
        if ! command -v "$bin" >/dev/null 2>&1; then
            echo "✗ missing: $bin"
            missing=1
        fi
    done
    if [[ ! -x "$NGINX_BIN" ]]; then
        echo "✗ missing nginx at $NGINX_BIN (brew install nginx)"
        missing=1
    fi
    if [[ ! -f "$REPO_ROOT/config.yaml" ]]; then
        echo "✗ missing config.yaml (do not overwrite from Windows; keep deerflow.* tool paths and legal_rag.enabled)"
        missing=1
    fi
    if [[ ! -f "$REPO_ROOT/.env" ]]; then
        echo "✗ missing root .env (API keys)"
        missing=1
    fi
    if [[ ! -f "$REPO_ROOT/frontend/.env" ]]; then
        echo "✗ missing frontend/.env"
        missing=1
    fi
    if ! grep -q 'BETTER_AUTH_SECRET=' "$REPO_ROOT/frontend/.env"; then
        echo "✗ frontend/.env needs BETTER_AUTH_SECRET for next start"
        missing=1
    fi
    if [[ "$missing" -ne 0 ]]; then
        exit 1
    fi
}

ensure_legal() {
    if ! docker inspect "$LEGAL_CONTAINER" >/dev/null 2>&1; then
        echo "✗ Legal container $LEGAL_CONTAINER not found."
        echo "  Do NOT docker compose up --build / force-recreate (rebuilds the graph)."
        echo "  Start the existing container only after it has been created once."
        exit 1
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$LEGAL_CONTAINER")" != "true" ]]; then
        echo "Starting existing Legal container (no recreate)..."
        docker start "$LEGAL_CONTAINER" >/dev/null
    fi
    local i=0
    while [[ "$i" -lt 60 ]]; do
        if curl -sS --max-time 3 http://127.0.0.1:8003/health 2>/dev/null | grep -q '"system_ready": true'; then
            echo "✓ Legal ready on :8003"
            return 0
        fi
        sleep 2
        i=$((i + 1))
    done
    echo "✗ Legal :8003 not ready. Do not rebuild the graph unless you intend to wait ~15 min."
    exit 1
}

start_langgraph() {
    if [[ -n "$(port_pids 2024)" ]]; then
        echo "✓ LangGraph already on :2024"
        return 0
    fi
    echo "Starting LangGraph..."
    (
        set -a
        # shellcheck disable=SC1091
        . "$REPO_ROOT/.env"
        set +a
        unset NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD NEO4J_DATABASE
        unset MILVUS_HOST MILVUS_PORT MILVUS_COLLECTION
        cd "$REPO_ROOT/backend"
        NO_COLOR=1 uv run langgraph dev --no-browser --allow-blocking --no-reload
    ) >"$REPO_ROOT/logs/langgraph.log" 2>&1 &
    "$REPO_ROOT/scripts/wait-for-port.sh" 2024 60 "LangGraph"
    echo "✓ LangGraph on :2024"
}

start_gateway() {
    if [[ -n "$(port_pids 8001)" ]]; then
        echo "✓ Gateway already on :8001"
        return 0
    fi
    echo "Starting Gateway..."
    (
        set -a
        # shellcheck disable=SC1091
        . "$REPO_ROOT/.env"
        set +a
        cd "$REPO_ROOT/backend"
        PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001
    ) >"$REPO_ROOT/logs/gateway.log" 2>&1 &
    "$REPO_ROOT/scripts/wait-for-port.sh" 8001 30 "Gateway"
    echo "✓ Gateway on :8001"
}

start_frontend() {
    if [[ -n "$(port_pids "$FRONTEND_PORT")" ]]; then
        echo "✓ Frontend already on :$FRONTEND_PORT"
        return 0
    fi
    if [[ ! -f "$REPO_ROOT/frontend/.next/BUILD_ID" ]]; then
        echo "Building frontend (one-time, production)..."
        (cd "$REPO_ROOT/frontend" && pnpm build) || exit 1
    fi
    echo "Starting frontend (next start, not Turbopack)..."
    (
        cd "$REPO_ROOT/frontend"
        PORT="$FRONTEND_PORT" pnpm exec next start -p "$FRONTEND_PORT"
    ) >"$REPO_ROOT/logs/frontend.log" 2>&1 &
    "$REPO_ROOT/scripts/wait-for-port.sh" "$FRONTEND_PORT" 30 "Frontend"
    echo "✓ Frontend on :$FRONTEND_PORT"
}

start_nginx() {
    if [[ -n "$(port_pids 2026)" ]]; then
        echo "✓ Nginx already on :2026"
        return 0
    fi
    echo "Starting nginx..."
    "$NGINX_BIN" -t -c "$NGINX_CONF" -p "$REPO_ROOT" >/dev/null
    "$NGINX_BIN" -g 'daemon off;' -c "$NGINX_CONF" -p "$REPO_ROOT" >"$REPO_ROOT/logs/nginx.log" 2>&1 &
    "$REPO_ROOT/scripts/wait-for-port.sh" 2026 10 "Nginx"
    echo "✓ Nginx on :2026"
}

stop_port() {
    local port="$1"
    local pids
    pids="$(port_pids "$port")"
    if [[ -z "$pids" ]]; then
        return 0
    fi
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 0.4
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

cmd_stop() {
    echo "Stopping Deer runtime (not :$FORBIDDEN_PORT, Legal default keep)..."
    assert_not_touching_3000
    if [[ -f "$REPO_ROOT/logs/nginx.pid" ]]; then
        "$NGINX_BIN" -s quit -c "$NGINX_CONF" -p "$REPO_ROOT" 2>/dev/null || true
        "$NGINX_BIN" -s quit -c /tmp/deer-nginx.local.conf -p "$REPO_ROOT" 2>/dev/null || true
        sleep 0.4
    fi
    stop_port 2026
    # Only this stack's frontend. Never pkill next-server / next dev.
    pkill -f "next start -p ${FRONTEND_PORT}" 2>/dev/null || true
    stop_port "$FRONTEND_PORT"
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    stop_port 8001
    pkill -f "langgraph dev" 2>/dev/null || true
    stop_port 2024
    if $STOP_LEGAL; then
        echo "Stopping Legal container (data kept)..."
        docker stop "$LEGAL_CONTAINER" >/dev/null 2>&1 || true
    else
        echo "  Legal :8003 left running"
    fi
    echo "✓ Deer runtime stopped"
}

cmd_status() {
    printf '%-10s %-6s %s\n' "service" "port" "check"
    printf '%-10s %-6s %s\n' "Legal" "8003" "$(http_code http://127.0.0.1:8003/health)"
    printf '%-10s %-6s %s\n' "LangGraph" "2024" "$(http_code http://127.0.0.1:2024/ok)"
    printf '%-10s %-6s %s\n' "Gateway" "8001" "$(http_code http://127.0.0.1:8001/health)"
    printf '%-10s %-6s %s\n' "Frontend" "3001" "$(http_code http://127.0.0.1:3001/workspace/chats/new)"
    printf '%-10s %-6s %s\n' "Nginx" "2026" "$(http_code http://127.0.0.1:2026/workspace/chats/new)"
    printf '%-10s %-6s %s\n' "Models" "2026" "$(http_code http://127.0.0.1:2026/api/models)"
    if lsof -nP -iTCP:"$FORBIDDEN_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo ":$FORBIDDEN_PORT still in use by the other project (expected)"
    fi
}

cmd_start() {
    mkdir -p "$REPO_ROOT/logs"
    ensure_prereqs
    assert_not_touching_3000
    ensure_legal
    start_langgraph
    start_gateway
    start_frontend
    start_nginx
    echo ""
    echo "Open:  http://localhost:2026"
    echo "Model: DeepSeek Chat  (Kimi is 404 on this key)"
    echo "Logs:  logs/langgraph.log logs/gateway.log logs/frontend.log logs/nginx.log"
    cmd_status
}

case "$cmd" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    status) cmd_status ;;
    restart) cmd_stop; cmd_start ;;
    *)
        echo "Usage: $0 {start|stop|status|restart} [--legal]"
        exit 2
        ;;
esac
