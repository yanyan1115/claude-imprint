#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[PASS] %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[WARN] %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[FAIL] %s\n' "$1"
}

load_env() {
  if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    . ".env"
    set +a
    pass ".env loaded"
  else
    warn ".env not found; using defaults and current environment"
  fi
}

expand_path() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s/%s\n' "$HOME" "${1#~/}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    PYTHON_BIN=""
  fi
}

http_probe() {
  "$PYTHON_BIN" - "$1" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as resp:
        print(resp.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)
PY
}

json_probe() {
  "$PYTHON_BIN" - "$1" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print(json.dumps(data, ensure_ascii=False))
PY
}

sqlite_probe() {
  "$PYTHON_BIN" - "$1" <<'PY'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
conn = sqlite3.connect(str(db_path))
try:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    required = {"memories", "conversation_log", "summaries"}
    missing = sorted(required - tables)
    if missing:
        print("MISSING:" + ",".join(missing))
        sys.exit(2)
    counts = {}
    for table in ("memories", "conversation_log", "summaries"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(counts)
finally:
    conn.close()
PY
}

printf 'Claude Imprint smoke test\n'
printf 'Project: %s\n\n' "$ROOT_DIR"

load_env
find_python

if [ -z "$PYTHON_BIN" ]; then
  fail "Python not found"
else
  PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
  "$PYTHON_BIN" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  if [ $? -eq 0 ]; then
    pass "Python $PY_VERSION"
  else
    fail "Python $PY_VERSION found, but Python 3.11+ is recommended"
  fi
fi

if [ -f "requirements.txt" ]; then
  pass "requirements.txt found"
else
  fail "requirements.txt missing"
fi

if [ -f "docker-compose.yml" ]; then
  pass "docker-compose.yml found"
else
  warn "docker-compose.yml missing"
fi

if [ -f ".env.example" ]; then
  pass ".env.example found"
else
  fail ".env.example missing"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if docker compose --env-file .env.example config --quiet >/dev/null 2>&1; then
    pass "docker compose config is valid"
  else
    fail "docker compose config failed"
  fi
else
  warn "docker compose not available; skipped compose validation"
fi

if [ -n "$PYTHON_BIN" ]; then
  for module in fastapi psutil yaml; do
    if "$PYTHON_BIN" -c "import $module" >/dev/null 2>&1; then
      pass "Python module import ok: $module"
    else
      warn "Python module not importable yet: $module"
    fi
  done
fi

MEMORY_HTTP_PORT="${MEMORY_HTTP_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
MEMORY_HTTP_URL="${MEMORY_HTTP_URL:-http://127.0.0.1:${MEMORY_HTTP_PORT}/mcp}"
DASHBOARD_URL="${DASHBOARD_URL:-http://127.0.0.1:${DASHBOARD_PORT}}"
STATUS_URL="${STATUS_URL:-${DASHBOARD_URL%/}/api/status}"

if [ -n "$PYTHON_BIN" ]; then
  if HTTP_CODE="$(http_probe "$MEMORY_HTTP_URL" 2>/dev/null)"; then
    if [[ "$HTTP_CODE" =~ ^[234][0-9][0-9]$ ]]; then
      pass "Memory HTTP reachable: $MEMORY_HTTP_URL (HTTP $HTTP_CODE)"
    else
      warn "Memory HTTP responded with HTTP $HTTP_CODE: $MEMORY_HTTP_URL"
    fi
  else
    fail "Memory HTTP not reachable: $MEMORY_HTTP_URL"
  fi

  if STATUS_JSON="$(json_probe "$STATUS_URL" 2>/dev/null)"; then
    pass "Dashboard status JSON reachable: $STATUS_URL"
    "$PYTHON_BIN" - "$STATUS_JSON" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
components = data.get("components", {})
for key in ("memory_http", "tunnel", "telegram"):
    comp = components.get(key, {})
    print(f"  - {key}: running={comp.get('running')} pid={comp.get('pid')}")
memory = data.get("memory", {})
print(f"  - memories={memory.get('count', 0)} today_logs={memory.get('today_logs', 0)}")
PY
  else
    fail "Dashboard status JSON not reachable: $STATUS_URL"
  fi
fi

DATA_DIR_RAW="${IMPRINT_DATA_DIR:-$HOME/.imprint}"
DATA_DIR="$(expand_path "$DATA_DIR_RAW")"
DB_PATH="${IMPRINT_DB:-$DATA_DIR/memory.db}"

if [ -d "$DATA_DIR" ]; then
  pass "IMPRINT_DATA_DIR exists: $DATA_DIR"
else
  warn "IMPRINT_DATA_DIR does not exist yet: $DATA_DIR"
fi

if [ -f "$DB_PATH" ]; then
  if SQLITE_RESULT="$(sqlite_probe "$DB_PATH" 2>/dev/null)"; then
    pass "SQLite schema readable: $DB_PATH"
    printf '  - table counts: %s\n' "$SQLITE_RESULT"
  else
    fail "SQLite schema check failed: $DB_PATH"
  fi
else
  warn "memory.db not found yet: $DB_PATH"
fi

RECENT_CONTEXT="$DATA_DIR/recent_context.md"
if [ -f "$RECENT_CONTEXT" ]; then
  pass "recent_context.md found"
else
  warn "recent_context.md not found yet; it appears after hooks/channel activity"
fi

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  pass "Telegram send env configured"
else
  warn "Telegram send env incomplete; set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID when enabling Telegram notifications"
fi

printf '\nSummary: %s passed, %s warnings, %s failed\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
