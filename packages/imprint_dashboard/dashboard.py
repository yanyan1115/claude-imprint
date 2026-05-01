#!/usr/bin/env python3
"""
Claude Imprint — Dashboard
localhost:3000 — manage all components: start/stop/status
"""

import os
import re
import subprocess
import signal
import json
import shutil
import sqlite3
import time
import urllib.request
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import psutil
import uvicorn
import sys

from memo_clover import memory_manager as mem

app = FastAPI(title="Claude Imprint")
BASE = Path(__file__).parent.parent.parent  # packages/imprint_dashboard -> project root
DATA_DIR = Path(os.environ.get("IMPRINT_DATA_DIR", str(Path.home() / ".imprint")))
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", 0))
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)
SEARCH_STATUS_TTL_SECONDS = 30
SEARCH_STATUS_TIMEOUT_SECONDS = 3
_SEARCH_STATUS_CACHE = {"checked_at": 0.0, "data": None}

# ─── Components ──────────────────────────────────────────

COMPONENTS = {
    "memory_http": {
        "name": "🧠 Memory HTTP",
        "pid_file": ".pid-http",
        "start_cmd": ["memo-clover", "--http"],
        "log_file": "logs/http.log",
        "type": "background",
        "check_port": 8000,
    },
    "tunnel": {
        "name": "🌐 Cloudflare Tunnel",
        "pid_file": ".pid-tunnel",
        "start_cmd": ["cloudflared", "tunnel", "run", "my-tunnel"],
        "log_file": "logs/tunnel.log",
        "type": "background",
        "grep_pattern": "cloudflared tunnel",
    },
    "telegram": {
        "name": "📨 Telegram",
        "grep_pattern": "channels plugin:telegram",
        "terminal_cmd": "claude --permission-mode auto --channels plugin:telegram@claude-plugins-official",
        "type": "terminal",
    },
}


# ─── Status Detection ────────────────────────────────────

def _pid_is_running(pid):
    """Return True when a PID exists and is not a zombie."""
    try:
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        return proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _find_listening_port(port):
    """Find a listening process by port using psutil, cross-platform."""
    try:
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr or conn.laddr.port != port:
                continue
            if conn.status == psutil.CONN_LISTEN:
                return {"running": True, "pid": conn.pid}
    except (psutil.AccessDenied, OSError):
        pass
    return {"running": False, "pid": None}


def _find_process_by_cmdline(pattern):
    """Find a process whose command line contains the given pattern."""
    try:
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmd = " ".join(proc.info.get('cmdline') or [])
                if pattern in cmd:
                    return {"running": True, "pid": proc.info.get('pid')}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return {"running": False, "pid": None}


def _find_port_with_lsof(port):
    """Unix fallback: find listening PIDs with lsof."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=3
        )
        pids = [p for p in result.stdout.strip().split("\n") if p]
        if pids:
            return {"running": True, "pid": int(pids[0])}
    except Exception:
        pass
    return {"running": False, "pid": None}


def _find_process_with_pgrep(pattern):
    """Unix fallback: find process by command line with pgrep."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=3
        )
        pids = [p for p in result.stdout.strip().split("\n") if p]
        if pids:
            return {"running": True, "pid": int(pids[0])}
    except Exception:
        pass
    return {"running": False, "pid": None}


def get_pid_status(comp):
    """Check background process status: psutil port → lsof → psutil cmdline → pgrep → PID file"""
    # Method 1: cross-platform port detection
    if "check_port" in comp:
        status = _find_listening_port(comp["check_port"])
        if status["running"]:
            return status

    # Method 2: Unix port fallback
    if "check_port" in comp:
        status = _find_port_with_lsof(comp["check_port"])
        if status["running"]:
            return status

    # Method 3: cross-platform process command line matching
    if "grep_pattern" in comp:
        status = _find_process_by_cmdline(comp["grep_pattern"])
        if status["running"]:
            return status

    # Method 4: Unix process name fallback
    if "grep_pattern" in comp:
        status = _find_process_with_pgrep(comp["grep_pattern"])
        if status["running"]:
            return status

    # Method 5: PID file fallback
    pid_file = comp.get("pid_file")
    pid_path = BASE / pid_file if pid_file else None
    if pid_path and pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            if _pid_is_running(pid):
                return {"running": True, "pid": pid}
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        pid_path.unlink(missing_ok=True)
    return {"running": False, "pid": None}


def get_terminal_status(comp):
    """Check terminal window process status"""
    status = _find_process_by_cmdline(comp["grep_pattern"])
    if status["running"]:
        return status
    return _find_process_with_pgrep(comp["grep_pattern"])


def get_tunnel_url():
    """Return tunnel status string if running"""
    status = get_pid_status(COMPONENTS["tunnel"])
    if status["running"]:
        return "Active"
    return None


def get_memory_stats():
    """Get memory stats"""
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return {"count": 0, "today_logs": 0}
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.close()

        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=TZ_OFFSET))
        today = datetime.now(tz).strftime("%Y-%m-%d")
        log_file = DATA_DIR / "memory" / f"{today}.md"
        today_logs = 0
        if log_file.exists():
            today_logs = len([l for l in log_file.read_text().splitlines() if l.strip()])
        return {"count": count, "today_logs": today_logs}
    except Exception:
        return {"count": 0, "today_logs": 0}


def _search_status_payload(
    *,
    mode,
    fallback,
    provider,
    model,
    reason="",
    endpoint="",
):
    message = "Vector Search" if mode == "vector" else "Text-only (Fallback)"
    tooltip = (
        "Vector engine is responding; semantic retrieval is available."
        if mode == "vector"
        else "Vector engine is not responding; current searches use text-only retrieval."
    )
    return {
        "mode": mode,
        "fallback": fallback,
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "message": message,
        "reason": reason,
        "tooltip": tooltip,
        "checked_at": int(time.time()),
    }


def _probe_ollama_search_status(provider, model):
    endpoint = getattr(mem, "OLLAMA_URL", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    try:
        payload = json.dumps({"model": model, "input": "dashboard search status"}).encode()
        req = urllib.request.Request(
            f"{endpoint.rstrip('/')}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=SEARCH_STATUS_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        embeddings = data.get("embeddings", [])
        if embeddings and embeddings[0]:
            return _search_status_payload(
                mode="vector",
                fallback=False,
                provider=provider,
                model=model,
                endpoint=endpoint,
            )
        return _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            endpoint=endpoint,
            reason="Ollama returned an empty embedding payload",
        )
    except Exception as exc:
        return _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            endpoint=endpoint,
            reason=str(exc),
        )


def _probe_openai_search_status(provider, model):
    api_key = getattr(mem, "OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    base = getattr(mem, "EMBED_API_BASE", os.environ.get("EMBED_API_BASE", "https://api.openai.com"))
    endpoint = f"{base.rstrip('/')}/v1/embeddings"
    if not api_key:
        return _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            endpoint=endpoint,
            reason="OPENAI_API_KEY is not configured",
        )

    try:
        payload = json.dumps({"model": model, "input": "dashboard search status"}).encode()
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=SEARCH_STATUS_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        items = data.get("data", [])
        if items and items[0].get("embedding"):
            return _search_status_payload(
                mode="vector",
                fallback=False,
                provider=provider,
                model=model,
                endpoint=endpoint,
            )
        return _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            endpoint=endpoint,
            reason="Embedding API returned an empty payload",
        )
    except Exception as exc:
        return _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            endpoint=endpoint,
            reason=str(exc),
        )


def get_search_status(force=False):
    """Return current retrieval mode with a short TTL to avoid noisy probes."""
    now = time.time()
    cached = _SEARCH_STATUS_CACHE.get("data")
    if cached and not force and now - _SEARCH_STATUS_CACHE.get("checked_at", 0.0) < SEARCH_STATUS_TTL_SECONDS:
        return cached

    provider = getattr(mem, "EMBED_PROVIDER", os.environ.get("EMBED_PROVIDER", "ollama"))
    model = getattr(mem, "EMBED_MODEL", os.environ.get("EMBED_MODEL", "bge-m3"))
    provider = (provider or "ollama").strip().lower()
    model = (model or "bge-m3").strip()

    if provider == "ollama":
        status = _probe_ollama_search_status(provider, model)
    elif provider == "openai":
        status = _probe_openai_search_status(provider, model)
    else:
        status = _search_status_payload(
            mode="text_only",
            fallback=True,
            provider=provider,
            model=model,
            reason=f"Unknown embedding provider: {provider}",
        )

    _SEARCH_STATUS_CACHE["checked_at"] = now
    _SEARCH_STATUS_CACHE["data"] = status
    return status


def get_scheduled_tasks():
    """Read scheduled tasks directory"""
    tasks_dir = Path.home() / ".claude" / "scheduled-tasks"
    if not tasks_dir.exists():
        return []
    tasks = []
    import yaml
    for d in sorted(tasks_dir.iterdir()):
        skill = d / "SKILL.md"
        if not skill.exists():
            continue
        text = skill.read_text()
        # parse frontmatter
        meta = {"id": d.name, "name": d.name, "description": ""}
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1])
                    if fm:
                        meta["name"] = fm.get("name", d.name)
                        meta["description"] = fm.get("description", "")
                except Exception:
                    pass
        tasks.append(meta)
    return tasks


def get_heatmap_data():
    """Get interaction data, dynamic date range back to earliest record"""
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=TZ_OFFSET))
    today = datetime.now(tz).date()
    data = {}

    db_path = DATA_DIR / "memory.db"
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(str(db_path))

        rows = conn.execute(
            "SELECT DATE(created_at) as d, COUNT(*) as c FROM memories GROUP BY DATE(created_at)"
        ).fetchall()
        for d, c in rows:
            if d:
                data[d] = data.get(d, 0) + c

        # Count conversation_log entries per day
        try:
            rows = conn.execute(
                "SELECT DATE(created_at) as d, COUNT(*) as c FROM conversation_log GROUP BY DATE(created_at)"
            ).fetchall()
            for d, c in rows:
                if d:
                    data[d] = data.get(d, 0) + c
        except sqlite3.OperationalError:
            pass  # table may not exist yet

        conn.close()

    # Also count daily log lines
    mem_dir = DATA_DIR / "memory"
    if mem_dir.exists():
        for f in mem_dir.glob("????-??-??.md"):
            d = f.stem
            lines = len([l for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")])
            if lines > 0:
                data[d] = data.get(d, 0) + lines

    # Dynamic date range: back to earliest record
    if data:
        from datetime import date as _date
        earliest = min(_date.fromisoformat(d) for d in data)
    else:
        earliest = today - timedelta(days=181)
    total_days = (today - earliest).days

    result = []
    for i in range(total_days, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        result.append({"date": d, "count": data.get(d, 0)})
    return result


# ─── API ────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    statuses = {}
    for key, comp in COMPONENTS.items():
        if comp["type"] == "background":
            status = get_pid_status(comp)
        else:
            status = get_terminal_status(comp)
        status["name"] = comp["name"]
        status["type"] = comp["type"]
        statuses[key] = status

    tunnel_url = get_tunnel_url()
    memory = get_memory_stats()
    tasks = get_scheduled_tasks()

    return {
        "components": statuses,
        "tunnel_url": tunnel_url,
        "memory": memory,
        "tasks": tasks,
    }


@app.get("/api/search-status")
async def api_search_status(force: bool = False):
    return get_search_status(force=force)


@app.post("/api/{component}/start")
async def api_start(component: str):
    if component not in COMPONENTS:
        return JSONResponse({"error": "unknown component"}, 404)

    comp = COMPONENTS[component]

    if comp["type"] == "background":
        log_path = BASE / comp["log_file"]
        with open(log_path, "a") as log:
            proc = subprocess.Popen(
                comp["start_cmd"],
                stdout=log, stderr=log,
                cwd=str(BASE),
                start_new_session=True,
            )
        pid_path = BASE / comp["pid_file"]
        pid_path.write_text(str(proc.pid))
        return {"ok": True, "pid": proc.pid}
    else:
        # Terminal / interactive component
        cmd = comp["terminal_cmd"]
        if shutil.which("osascript"):
            # macOS: open in Terminal window
            try:
                result = subprocess.run(
                    [
                        "osascript", "-e",
                        f'tell application "Terminal" to do script "cd {BASE} && {cmd}"'
                    ],
                    capture_output=True, text=True, timeout=10,
                )
            except (subprocess.TimeoutExpired, Exception) as e:
                return JSONResponse(
                    {"ok": False, "error": f"Failed to open Terminal: {e}. Run manually: {cmd}"},
                    status_code=500,
                )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()
                return JSONResponse(
                    {"ok": False, "error": f"AppleScript error: {err}. Run manually: {cmd}"},
                    status_code=500,
                )
            return {"ok": True}
        else:
            # Linux: run as background process
            log_name = component.replace(" ", "-")
            log_path = LOGS / f"{log_name}.log"
            pid_file = f".pid-{component}"
            with open(log_path, "a") as log:
                proc = subprocess.Popen(
                    cmd.split(),
                    stdout=log, stderr=log,
                    cwd=str(BASE),
                    start_new_session=True,
                )
            (BASE / pid_file).write_text(str(proc.pid))
            return {"ok": True, "pid": proc.pid}


@app.post("/api/{component}/stop")
async def api_stop(component: str):
    if component not in COMPONENTS:
        return JSONResponse({"error": "unknown component"}, 404)

    comp = COMPONENTS[component]

    if comp["type"] == "background":
        # Get actual PID via status detection
        status = get_pid_status(comp)
        if status["running"] and status["pid"]:
            try:
                os.kill(status["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        # Clean up PID file
        pid_file = comp.get("pid_file", "")
        if pid_file:
            pid_path = BASE / pid_file
            pid_path.unlink(missing_ok=True)
        return {"ok": True}
    else:
        if shutil.which("osascript"):
            # macOS: can't force-kill terminal sessions
            return {"ok": True, "message": "Please close the terminal window manually (Ctrl+C)"}
        else:
            # Linux: kill the background process
            status = get_terminal_status(comp)
            if status["running"] and status["pid"]:
                try:
                    os.kill(status["pid"], signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            pid_file = f".pid-{component}"
            (BASE / pid_file).unlink(missing_ok=True)
            return {"ok": True}


@app.get("/api/heatmap")
async def api_heatmap():
    """Return heatmap data"""
    return {"days": get_heatmap_data()}


MEMORY_FIELD_DEFAULTS = {
    "id": None,
    "content": "",
    "category": "general",
    "source": "",
    "importance": 5,
    "created_at": None,
    "valence": 0.5,
    "arousal": 0.3,
    "resolved": False,
    "decay_rate": None,
    "pinned": False,
    "activation_count": 1,
    "last_active": None,
}
MEMORY_OPTIONAL_FIELDS = ("archived", "is_archived", "decay_score", "status")


def _table_columns(conn, table):
    """Return SQLite column names for a table; empty set means missing table."""
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return set()


def _sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _clamp_float(value, min_value, max_value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def _clamp_int(value, min_value, max_value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _memory_is_archived(memory):
    status = str(memory.get("status") or "")
    normalized = status.strip().lower().replace("-", "_")
    return (
        _as_bool(memory.get("archived"), False)
        or _as_bool(memory.get("is_archived"), False)
        or normalized in {"archived", "archive", "is_archived"}
    )


def _memory_decay_status(memory):
    category = str(memory.get("category") or "").lower()
    decay_rate = memory.get("decay_rate")
    try:
        decay_rate_value = float(decay_rate) if decay_rate is not None else None
    except (TypeError, ValueError):
        decay_rate_value = None
    if _memory_is_archived(memory):
        return {"key": "archived", "label": "Archived", "zh": "已归档"}
    protected = (
        _as_bool(memory.get("pinned"), False)
        or category == "core_profile"
        or decay_rate_value == 0.0
    )
    if protected:
        return {"key": "protected", "label": "Protected", "zh": "不衰减"}
    if not _as_bool(memory.get("resolved"), False) and float(memory.get("arousal") or 0) >= 0.7:
        return {"key": "surfacing", "label": "Surfacing", "zh": "主动浮现候选"}
    if _as_bool(memory.get("resolved"), False):
        return {"key": "resolved", "label": "Resolved", "zh": "已解决"}
    decay_score = memory.get("decay_score")
    try:
        if decay_score is not None and float(decay_score) < 0.3:
            return {"key": "low_score", "label": "Low score", "zh": "低分"}
    except (TypeError, ValueError):
        pass
    return {"key": "decaying", "label": "Decaying", "zh": "衰减中"}


def _fetch_memories(q="", limit=20, max_limit=100):
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return []
    limit = _clamp_int(limit, 1, max_limit, 20)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = _table_columns(conn, "memories")
        if not columns:
            return []
        select_fields = []
        for field, default in MEMORY_FIELD_DEFAULTS.items():
            if field in columns:
                select_fields.append(field)
            else:
                select_fields.append(f"{_sql_literal(default)} AS {field}")
        for field in MEMORY_OPTIONAL_FIELDS:
            if field in columns:
                select_fields.append(field)

        order_col = "created_at" if "created_at" in columns else "id"
        sql = f"SELECT {', '.join(select_fields)} FROM memories"
        params = []
        if q and "content" in columns:
            sql += " WHERE content LIKE ?"
            params.append(f"%{q}%")
        elif q:
            return []
        sql += f" ORDER BY {order_col} DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        memories = []
        for row in rows:
            memory = dict(row)
            memory["valence"] = _clamp_float(memory.get("valence"), 0.0, 1.0, 0.5)
            memory["arousal"] = _clamp_float(memory.get("arousal"), 0.0, 1.0, 0.3)
            memory["resolved"] = _as_bool(memory.get("resolved"), False)
            memory["pinned"] = _as_bool(memory.get("pinned"), False)
            memory["activation_count"] = _clamp_int(memory.get("activation_count"), 0, 10**9, 1)
            memory["decay_status"] = _memory_decay_status(memory)
            memories.append(memory)
        return memories
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


@app.get("/api/memories")
async def api_memories(q: str = "", limit: int = 20):
    """Search or list memories"""
    status = get_search_status()
    search_mode = "vector" if status.get("mode") == "vector" and not status.get("fallback") else "fts5_fallback"
    return {
        "memories": _fetch_memories(q=q, limit=limit),
        "meta": {
            "search_mode": search_mode,
            "provider": status.get("provider", ""),
            "model": status.get("model", ""),
            "reason": status.get("reason", ""),
        },
    }


@app.get("/api/decay-status")
async def api_decay_status():
    """Return lightweight Phase 3 decay/status counters for the dashboard."""
    memories = _fetch_memories(limit=100000, max_limit=100000)
    stats = {
        "total": len(memories),
        "protected": 0,
        "surfacing": 0,
        "resolved": 0,
        "archived": 0,
        "decaying": 0,
        "low_score": 0,
    }
    for memory in memories:
        key = memory.get("decay_status", {}).get("key", "decaying")
        if key in {"protected", "decaying", "low_score"}:
            stats[key] += 1
        if _as_bool(memory.get("resolved"), False):
            stats["resolved"] += 1
        if _memory_is_archived(memory):
            stats["archived"] += 1
        if not _as_bool(memory.get("resolved"), False) and float(memory.get("arousal") or 0) >= 0.7:
            stats["surfacing"] += 1
    return stats


@app.get("/api/summaries")
def get_summaries(q: str = "", limit: int = 10):
    """Return recent rolling conversation summaries."""
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return []
    limit = _clamp_int(limit, 1, 100, 10)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if q:
            rows = conn.execute(
                "SELECT id, content, turn_count, platform, created_at FROM summaries WHERE content LIKE ? OR platform LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{q}%", f"%{q}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, content, turn_count, platform, created_at FROM summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.delete("/api/summaries/{summary_id}")
async def api_delete_summary(summary_id: int):
    """Delete a rolling conversation summary."""
    result = mem.delete_summary(summary_id)
    if not result.get("ok"):
        status_code = 404 if "not found" in result.get("error", "").lower() else 400
        return JSONResponse(result, status_code=status_code)
    return result


@app.put("/api/summaries/{summary_id}")
async def api_update_summary(summary_id: int, request: Request):
    """Update a rolling conversation summary."""
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "error": "JSON body must be an object"}, status_code=400)
    content = (body.get("content") or "").strip()
    platform = (body.get("platform") or "unknown").strip() or "unknown"
    try:
        turn_count = int(body.get("turn_count") or 0)
    except (TypeError, ValueError):
        turn_count = 0
    result = mem.update_summary(
        summary_id=summary_id,
        content=content,
        turn_count=turn_count,
        platform=platform,
    )
    if not result.get("ok"):
        status_code = 404 if "not found" in result.get("error", "").lower() else 400
        return JSONResponse(result, status_code=status_code)
    return result


@app.delete("/api/memories/{memory_id}")
async def api_delete_memory(memory_id: int):
    """Delete a memory"""
    result = mem.delete_memory(memory_id)
    if not result.get("ok"):
        return JSONResponse(result, status_code=404 if "not found" in result.get("error", "").lower() else 400)
    return result


@app.put("/api/memories/{memory_id}")
async def api_update_memory(memory_id: int, request: Request):
    """Update a memory"""
    body = await request.json()
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return JSONResponse({"ok": False, "error": "database not found"}, status_code=404)

    core_fields = {"content", "category", "importance"}
    if any(field in body for field in core_fields):
        content = (body.get("content") or "").strip()
        category = (body.get("category") or "general").strip() or "general"
        importance = _clamp_int(body.get("importance"), 1, 10, 5)
        if not content:
            return JSONResponse({"ok": False, "error": "content is required"}, status_code=400)
        result = mem.update_memory(memory_id, content=content, category=category, importance=importance)
        if not result.get("ok"):
            status_code = 404 if "not found" in result.get("error", "").lower() else 400
            return JSONResponse({"ok": False, "error": result.get("error", "update failed")}, status_code=status_code)

    conn = sqlite3.connect(str(db_path))
    try:
        columns = _table_columns(conn, "memories")
        if not columns:
            return JSONResponse({"ok": False, "error": "memories table not found"}, status_code=404)
        exists = conn.execute("SELECT 1 FROM memories WHERE id = ? LIMIT 1", (memory_id,)).fetchone()
        if not exists:
            return JSONResponse({"ok": False, "error": "memory not found"}, status_code=404)

        updates = []
        params = []
        if "valence" in body and "valence" in columns:
            updates.append("valence = ?")
            params.append(_clamp_float(body.get("valence"), 0.0, 1.0, 0.5))
        if "arousal" in body and "arousal" in columns:
            updates.append("arousal = ?")
            params.append(_clamp_float(body.get("arousal"), 0.0, 1.0, 0.3))
        if "resolved" in body and "resolved" in columns:
            updates.append("resolved = ?")
            params.append(1 if _as_bool(body.get("resolved"), False) else 0)
        if "pinned" in body and "pinned" in columns:
            updates.append("pinned = ?")
            params.append(1 if _as_bool(body.get("pinned"), False) else 0)
        if "decay_rate" in body and "decay_rate" in columns:
            raw_decay_rate = body.get("decay_rate")
            if raw_decay_rate == "" or raw_decay_rate is None:
                updates.append("decay_rate = ?")
                params.append(None)
            else:
                try:
                    decay_rate = max(0.0, float(raw_decay_rate))
                except (TypeError, ValueError):
                    return JSONResponse({"ok": False, "error": "decay_rate must be a non-negative number"}, status_code=400)
                updates.append("decay_rate = ?")
                params.append(decay_rate)

        if updates:
            params.append(memory_id)
            conn.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    except sqlite3.OperationalError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/stream-stats")
async def api_stream_stats():
    """Stream (conversation_log) statistics."""
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return {"total": 0, "today": 0, "platforms": {}, "last_message": None}
    import sqlite3
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=TZ_OFFSET))
    today = datetime.now(tz).strftime("%Y-%m-%d")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_log WHERE created_at >= ?", (today,)
        ).fetchone()[0]
        platform_rows = conn.execute(
            "SELECT platform, COUNT(*) as c FROM conversation_log GROUP BY platform ORDER BY c DESC"
        ).fetchall()
        platforms = {r["platform"]: r["c"] for r in platform_rows}
        last = conn.execute(
            "SELECT platform, direction, content, created_at FROM conversation_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_msg = None
        if last:
            content = last["content"]
            if len(content) > 80:
                content = content[:80] + "..."
            last_msg = {
                "platform": last["platform"],
                "direction": last["direction"],
                "content": content,
                "time": last["created_at"],
            }
    except Exception:
        total, today_count, platforms, last_msg = 0, 0, {}, None
    finally:
        conn.close()
    return {"total": total, "today": today_count, "platforms": platforms, "last_message": last_msg}


@app.get("/api/remote-tools")
async def api_remote_tools():
    """Get remote tool call log (cc_tasks etc.)"""
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return {"tasks": []}
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, prompt, status, result, source, created_at, completed_at FROM cc_tasks ORDER BY id DESC LIMIT 20"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []  # table doesn't exist yet
    conn.close()
    return {"tasks": [dict(r) for r in rows]}


@app.get("/api/logs/{component}")
async def api_logs(component: str, lines: int = 30):
    """Get recent logs"""
    comp = COMPONENTS.get(component)
    if not comp or "log_file" not in comp:
        return {"logs": "No logs"}
    log_path = BASE / comp["log_file"]
    if not log_path.exists():
        return {"logs": "Log file not found"}
    try:
        all_lines = log_path.read_text().splitlines()
        return {"logs": "\n".join(all_lines[-lines:])}
    except Exception as e:
        return {"logs": f"Read error: {e}"}


def get_system_status():
    """System status: today's messages, total messages, days active, last heartbeat"""
    from datetime import datetime, timezone, timedelta
    import sqlite3
    tz = timezone(timedelta(hours=TZ_OFFSET))
    now = datetime.now(tz)
    today = now.date().isoformat()
    tz_offset_str = f'+{TZ_OFFSET} hours' if TZ_OFFSET >= 0 else f'{TZ_OFFSET} hours'
    db_path = DATA_DIR / "memory.db"
    result = {"last_heartbeat": None, "today_messages": 0, "days_active": 0, "total_messages": 0}

    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM conversation_log WHERE DATE(created_at, '{tz_offset_str}') = ?", (today,)
            ).fetchone()
            result["today_messages"] = row[0] if row else 0
            row = conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()
            result["total_messages"] = row[0] if row else 0
            row = conn.execute(f"SELECT MIN(DATE(created_at, '{tz_offset_str}')) FROM conversation_log").fetchone()
            if row and row[0]:
                from datetime import date as dt_date
                first = dt_date.fromisoformat(row[0])
                result["days_active"] = (now.date() - first).days
        except sqlite3.OperationalError:
            pass
        conn.close()

    # Count CC conversation messages from JSONL files
    cc_projects = Path.home() / ".claude" / "projects"
    day_start = (now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=TZ_OFFSET)).strftime("%Y-%m-%dT%H:%M")
    if cc_projects.exists():
        for jsonl in cc_projects.rglob("*.jsonl"):
            try:
                if (now.timestamp() - jsonl.stat().st_mtime) > 86400:
                    continue
                with open(jsonl) as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                            if obj.get("message", {}).get("role") == "user" and obj.get("timestamp", "") >= day_start:
                                result["today_messages"] += 1
                        except Exception:
                            pass
            except Exception:
                pass

    # Last heartbeat from cron logs
    latest_ts = None
    for log_file in LOGS.glob("cron-*.log"):
        try:
            for line in reversed(log_file.read_text().strip().splitlines()):
                m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", line)
                if m:
                    ts = m.group(1)
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                    break
        except Exception:
            pass
    if latest_ts:
        result["last_heartbeat"] = latest_ts

    return result


def get_memory_fragment():
    """Get a random memory fragment (importance >= 3)"""
    import sqlite3
    db_path = DATA_DIR / "memory.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT content, category, created_at FROM memories WHERE importance >= 3 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return {"content": row[0], "category": row[1], "date": row[2][:10] if row[2] else ""}
    return None


@app.get("/api/system-status")
async def api_system_status():
    return get_system_status()


@app.get("/api/memory-fragment")
async def api_memory_fragment():
    frag = get_memory_fragment()
    return {"fragment": frag}


@app.get("/api/short-term-memory")
async def api_short_term_memory():
    """Read recent_context.md (Horizon), parse summaries and messages"""
    ctx_file = DATA_DIR / "recent_context.md"
    if not ctx_file.exists():
        # Fallback: check BASE directory
        ctx_file = BASE / "recent_context.md"
    if not ctx_file.exists():
        return {"exists": False, "summaries": [], "messages": [], "total_lines": 0, "msg_count": 0}

    text = ctx_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    updated = ""
    for line in lines:
        if "Updated:" in line:
            updated = line.strip().replace("<!-- Updated: ", "").replace(" -->", "")
            break

    summaries = []
    messages = []
    summarized_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if stripped.startswith("[summary") or stripped.startswith("[摘要"):
            summaries.append(stripped)
        elif stripped.startswith("["):
            messages.append(stripped)
            if "[summary]" in stripped.lower() or "[摘要]" in stripped:
                summarized_count += 1

    return {
        "exists": True,
        "updated": updated,
        "summaries": summaries,
        "messages": messages,
        "total_lines": len([l for l in lines if l.strip() and not l.strip().startswith("<!--")]),
        "msg_count": len(messages),
        "summarized_count": summarized_count,
        "summary_count": len(summaries),
        "threshold": 120,
    }


@app.get("/api/live-files")
async def api_live_files():
    """Return all dynamically-updated md files with content and metadata"""
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=TZ_OFFSET))
    now = datetime.now(tz)

    CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
    today = now.strftime("%Y-%m-%d")
    daily_path = DATA_DIR / "memory" / f"{today}.md"

    files_config = [
        {"key": "claude_md", "label": "CLAUDE.md", "path": CLAUDE_MD, "desc": "Persona + system config"},
        {"key": "recent_context", "label": "recent_context.md", "path": DATA_DIR / "recent_context.md", "desc": "Horizon — cross-channel recent context"},
        {"key": "memory_index", "label": "MEMORY.md", "path": DATA_DIR / "MEMORY.md", "desc": "Memory index (auto-generated)"},
        {"key": "daily_log", "label": f"{today}.md", "path": daily_path, "desc": "Today's event log"},
        {"key": "experience", "label": "experience.md", "path": DATA_DIR / "memory" / "bank" / "experience.md", "desc": "Knowledge bank — experience"},
        {"key": "backlog", "label": "backlog.md", "path": DATA_DIR / "memory" / "bank" / "backlog.md", "desc": "Knowledge bank — backlog"},
    ]

    # Also check BASE directory for recent_context.md fallback
    rc_path = files_config[1]["path"]
    if not rc_path.exists():
        alt = BASE / "recent_context.md"
        if alt.exists():
            files_config[1]["path"] = alt

    results = []
    for f in files_config:
        p = f["path"]
        info = {"key": f["key"], "label": f["label"], "desc": f["desc"]}
        if p and p.exists():
            stat = p.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=tz)
            info["exists"] = True
            info["size"] = stat.st_size
            info["mtime"] = mtime.strftime("%m-%d %H:%M")
            info["content"] = p.read_text(encoding="utf-8", errors="replace")
            age_min = (now - mtime).total_seconds() / 60
            info["stale"] = age_min > 60
        else:
            info["exists"] = False
            info["content"] = ""
            info["mtime"] = ""
            info["size"] = 0
            info["stale"] = False
        results.append(info)
    return {"files": results}


@app.get("/api/todos/system")
async def api_todos_system():
    """Read system todos (system-todos.md in bank/)"""
    for name in ["system-todos.md", "north-todos.md"]:
        f = DATA_DIR / "memory" / "bank" / name
        if f.exists():
            return {"content": f.read_text(encoding="utf-8")}
    return {"content": ""}


@app.get("/api/todos/backlog")
async def api_todos_backlog():
    """Read user backlog (backlog.md in bank/)"""
    f = DATA_DIR / "memory" / "bank" / "backlog.md"
    if not f.exists():
        return {"content": ""}
    return {"content": f.read_text(encoding="utf-8")}


@app.put("/api/todos/backlog")
async def api_save_backlog(request: Request):
    """Save user backlog edits"""
    body = await request.json()
    content = body.get("content", "")
    f = DATA_DIR / "memory" / "bank" / "backlog.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return {"ok": True}


# ─── Frontend ────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Imprint</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #FAF9F5;
    color: #3D3D3A;
    min-height: 100vh;
    padding: 20px;
  }
  .header {
    text-align: center;
    padding: 30px 0 20px;
    position: relative;
  }
  .header h1 {
    font-size: 28px;
    color: #B96748;
    margin-bottom: 8px;
  }
  .header .subtitle {
    color: #B0AEA5;
    font-size: 14px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    max-width: 900px;
    margin: 20px auto;
  }
  .card {
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 20px;
    transition: border-color 0.3s, box-shadow 0.3s;
  }
  .card:hover { border-color: #B96748; box-shadow: 0 2px 12px rgba(185,103,72,0.08); }
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .card-name { font-size: 16px; font-weight: 600; color: #3D3D3A; }
  .status-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 8px;
  }
  .status-dot.on { background: #B96748; box-shadow: 0 0 8px rgba(185,103,72,0.4); }
  .status-dot.off { background: #B0AEA5; }
  .status-dot.warn { background: #F59E0B; box-shadow: 0 0 8px rgba(245,158,11,0.4); }
  .toggle {
    position: relative;
    width: 44px; height: 24px;
    cursor: pointer;
  }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle .slider {
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: #D5D3C9;
    border-radius: 12px;
    transition: 0.3s;
  }
  .toggle .slider:before {
    content: "";
    position: absolute;
    height: 18px; width: 18px;
    left: 3px; bottom: 3px;
    background: #fff;
    border-radius: 50%;
    transition: 0.3s;
  }
  .toggle input:checked + .slider { background: #B96748; }
  .toggle input:checked + .slider:before { transform: translateX(20px); }
  .card-info {
    font-size: 12px;
    color: #B0AEA5;
    margin-top: 8px;
  }
  .info-bar {
    max-width: 900px;
    margin: 20px auto;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }
  .info-chip {
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
    flex: 1;
    min-width: 200px;
  }
  .info-chip .label { color: #B0AEA5; margin-bottom: 4px; }
  .info-chip .value { color: #B96748; font-family: monospace; word-break: break-all; }
  .memory-section {
    max-width: 900px;
    margin: 20px auto;
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 20px;
  }
  .memory-section h2 {
    font-size: 18px;
    margin-bottom: 12px;
    color: #B96748;
  }
  .search-box {
    width: 100%;
    padding: 8px 12px;
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 8px;
    color: #3D3D3A;
    font-size: 14px;
    margin-bottom: 12px;
  }
  .search-box:focus { outline: none; border-color: #B96748; }
  .memory-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }
  .memory-title-row h2 {
    margin-bottom: 0;
  }
  .search-mode-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 26px;
    padding: 4px 9px;
    border: 1px solid #E8E6DC;
    border-radius: 7px;
    background: #FAF9F5;
    color: #6B6962;
    font-size: 12px;
    white-space: nowrap;
  }
  .search-mode-pill::before {
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #B0AEA5;
  }
  .search-mode-pill.vector {
    border-color: #9AC89A;
    color: #2B8A3E;
    background: #F4FBF3;
  }
  .search-mode-pill.vector::before {
    background: #2B8A3E;
    box-shadow: 0 0 8px rgba(43,138,62,0.35);
  }
  .search-mode-pill.fallback {
    border-color: #F4C46A;
    color: #9A5A00;
    background: #FFF7E8;
  }
  .search-mode-pill.fallback::before {
    background: #F59E0B;
    box-shadow: 0 0 8px rgba(245,158,11,0.35);
  }
  .search-mode-pill.unknown::before {
    background: #B0AEA5;
  }
  .memory-item {
    padding: 10px 0;
    border-bottom: 1px solid #E8E6DC;
    font-size: 13px;
    color: #3D3D3A;
    position: relative;
  }
  .memory-item:last-child { border-bottom: none; }
  .memory-item:hover .memory-actions { opacity: 1; }
  .memory-meta { color: #B0AEA5; font-size: 11px; margin-top: 2px; }
  .memory-content {
    padding-right: 90px;
    white-space: pre-wrap;
    line-height: 1.55;
  }
  .memory-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
    padding-right: 90px;
  }
  .memory-badge {
    display: inline-flex;
    align-items: center;
    min-height: 20px;
    padding: 1px 6px;
    border-radius: 4px;
    border: 1px solid #E8E6DC;
    color: #6B6962;
    background: #FAF9F5;
    font-size: 11px;
    line-height: 1.4;
  }
  .memory-badge.protected { border-color: #8FBC8F; color: #2B8A3E; background: #F4FBF3; }
  .memory-badge.surfacing { border-color: #E3A44D; color: #9A5A00; background: #FFF7E8; font-weight: 600; }
  .memory-badge.resolved { border-color: #9FB9D9; color: #386FA4; background: #F2F7FC; }
  .memory-badge.archived, .memory-badge.low_score { border-color: #C9C6BC; color: #7A766B; background: #F2F1EC; }
  .memory-badge.decaying { border-color: #DDA58A; color: #B96748; background: #FFF8F0; }
  .decay-stat-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0 0 10px;
  }
  .decay-stat-chip {
    border: 1px solid #E8E6DC;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
    color: #6B6962;
    background: #FAF9F5;
  }
  .decay-stat-chip strong { color: #B96748; font-weight: 600; }
  .memory-actions {
    opacity: 0;
    transition: opacity 0.15s;
    position: absolute;
    right: 0;
    top: 8px;
    display: flex;
    gap: 4px;
  }
  .memory-actions button {
    background: none;
    border: 1px solid #E8E6DC;
    color: #B0AEA5;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
  }
  .memory-actions button:hover { border-color: #B96748; color: #B96748; }
  .memory-actions button.del:hover { border-color: #c0392b; color: #c0392b; }
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
    z-index: 100;
    justify-content: center;
    align-items: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 24px;
    width: 500px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  }
  .modal h3 { color: #B96748; margin-bottom: 16px; font-size: 16px; }
  .modal textarea {
    width: 100%;
    min-height: 100px;
    padding: 8px 12px;
    border: 1px solid #E8E6DC;
    border-radius: 8px;
    font-size: 13px;
    color: #3D3D3A;
    resize: vertical;
    font-family: inherit;
  }
  .modal textarea:focus { outline: none; border-color: #B96748; }
  .modal-row { display: flex; gap: 12px; margin-top: 12px; }
  .modal-row select, .modal-row input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid #E8E6DC;
    border-radius: 6px;
    font-size: 13px;
    color: #3D3D3A;
  }
  .modal-field { flex: 1; min-width: 0; }
  .modal-field label {
    display: block;
    color: #B0AEA5;
    font-size: 11px;
    margin-bottom: 4px;
  }
  .modal-field input, .modal-field select {
    width: 100%;
  }
  .modal-checks {
    display: flex;
    gap: 16px;
    margin-top: 12px;
    color: #6B6962;
    font-size: 13px;
  }
  .modal-checks label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .modal-buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  .modal-buttons button {
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    border: 1px solid #E8E6DC;
    background: #FFFFFF;
    color: #3D3D3A;
  }
  .modal-buttons button.save { background: #B96748; color: #FFFFFF; border-color: #B96748; }
  .modal-buttons button.save:hover { background: #a05538; }
  .log-btn {
    background: none;
    border: 1px solid #E8E6DC;
    color: #B0AEA5;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    margin-top: 4px;
  }
  .log-btn:hover { border-color: #B96748; color: #B96748; }
  .lang-btn {
    position: absolute;
    right: 20px;
    top: 16px;
    background: none;
    border: none;
    color: #3D3D3A;
    font-size: 15px;
    cursor: pointer;
    transition: opacity 0.2s;
    opacity: 0.6;
  }
  .lang-btn:hover { opacity: 1; }
  .tasks-section {
    max-width: 900px;
    margin: 20px auto;
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 20px;
  }
  .tasks-section h2 {
    font-size: 18px;
    margin-bottom: 12px;
    color: #B96748;
  }
  .task-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid #E8E6DC;
    font-size: 13px;
  }
  .task-item:last-child { border-bottom: none; }
  .task-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #B96748;
    box-shadow: 0 0 6px rgba(185,103,72,0.3);
    flex-shrink: 0;
  }
  .heatmap-row {
    display: flex;
    gap: 12px;
    max-width: 900px;
    margin: 20px auto;
    align-items: stretch;
  }
  .heatmap-section {
    flex: 3;
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 20px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .heatmap-section h2 {
    font-size: 18px;
    margin-bottom: 4px;
    color: #B96748;
  }
  .heatmap-subtitle {
    font-size: 12px;
    color: #B0AEA5;
    margin-bottom: 14px;
  }
  .heatmap-sidebar {
    flex: 2;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    overflow: hidden;
  }
  .sidebar-card {
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 16px 20px;
    transition: border-color 0.3s;
  }
  .sidebar-card:hover { border-color: #C97B5A; }
  .sidebar-card h3 {
    font-size: 16px;
    color: #B96748;
    margin-bottom: 10px;
  }
  .status-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .status-item {
    text-align: center;
    padding: 8px 4px;
    background: #FAF9F5;
    border-radius: 8px;
  }
  .status-item .num {
    font-size: 24px;
    font-weight: 300;
    color: #B96748;
    line-height: 1.2;
  }
  .status-item .label {
    font-size: 11px;
    color: #B0AEA5;
    margin-top: 2px;
  }
  .fragment-card { padding: 14px 20px; }
  .fragment-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .fragment-header h3 { font-size: 16px; color: #B96748; margin: 0; }
  .fragment-header .fragment-date { font-size: 11px; color: #B0AEA5; }
  .fragment-body {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    overflow: hidden;
  }
  .fragment-content {
    font-size: 13px;
    color: #3D3D3A;
    line-height: 1.5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }
  .fragment-refresh {
    background: none;
    border: none;
    color: #B0AEA5;
    cursor: pointer;
    font-size: 13px;
    transition: color 0.2s;
  }
  .fragment-refresh:hover { color: #B96748; }
  .heatmap-wrap {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .heatmap-months {
    display: flex;
    font-size: 10px;
    color: #B0AEA5;
    margin-bottom: 4px;
    margin-left: 32px;
  }
  .heatmap-months span {
    flex: 1;
    min-width: 0;
  }
  .heatmap-days {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 10px;
    color: #B0AEA5;
    padding-top: 1px;
  }
  .heatmap-days span {
    height: 12px;
    line-height: 12px;
    width: 24px;
    text-align: right;
    padding-right: 4px;
  }
  .heatmap-grid {
    display: flex;
    gap: 3px;
    overflow-x: auto;
  }
  .heatmap-col {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .heatmap-cell {
    width: 12px; height: 12px;
    border-radius: 2px;
    background: #EBEAE2;
    position: relative;
    cursor: default;
  }
  .heatmap-cell[data-level="1"] { background: #F0D1C2; }
  .heatmap-cell[data-level="2"] { background: #DDA58A; }
  .heatmap-cell[data-level="3"] { background: #C97B5A; }
  .heatmap-cell[data-level="4"] { background: #B96748; }
  .heatmap-cell .tooltip {
    display: none;
    position: absolute;
    bottom: 18px; left: 50%;
    transform: translateX(-50%);
    background: #3D3D3A;
    color: #fff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    white-space: nowrap;
    z-index: 10;
  }
  .heatmap-cell:hover .tooltip { display: block; }
  .heatmap-legend {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 10px;
    font-size: 11px;
    color: #B0AEA5;
    justify-content: flex-end;
  }
  .heatmap-legend .heatmap-cell { cursor: default; width: 10px; height: 10px; }
  .task-name { font-weight: 600; color: #3D3D3A; }
  .task-desc { color: #B0AEA5; font-size: 12px; }
  .log-box {
    background: #FFFFFF;
    border-radius: 6px;
    padding: 8px;
    font-family: monospace;
    font-size: 11px;
    color: #B0AEA5;
    max-height: 150px;
    overflow-y: auto;
    margin-top: 8px;
    white-space: pre-wrap;
    display: none;
  }
  .todos-section {
    max-width: 900px;
    margin: 20px auto;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .todo-card {
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 14px 18px;
    transition: border-color 0.3s;
  }
  .todo-card:hover { border-color: #C97B5A; }
  .todo-card h3 {
    font-size: 17px;
    font-weight: 600;
    color: #B96748;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #F0EDE4;
  }
  .todo-content {
    font-size: 13px;
    color: #3D3D3A;
    line-height: 1.75;
    min-height: 50px;
    max-height: 180px;
    overflow-y: auto;
  }
  .todo-edit-area {
    width: 100%;
    min-height: 200px;
    padding: 8px 12px;
    border: 1px solid #E8E6DC;
    border-radius: 8px;
    font-size: 13px;
    color: #3D3D3A;
    resize: vertical;
    font-family: 'SF Mono', Monaco, monospace;
    line-height: 1.7;
    background: #FAFAF8;
    display: none;
  }
  .todo-edit-area:focus { outline: none; border-color: #B96748; }
  .todo-edit-btn {
    background: none;
    border: 1px solid #E8E6DC;
    color: #B0AEA5;
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    margin-top: 10px;
  }
  .todo-edit-btn:hover { border-color: #B96748; color: #B96748; }
  .todo-edit-btn.primary { background: #B96748; color: #fff; border-color: #B96748; }
  .todo-edit-btn.primary:hover { background: #a05538; }
  .live-files-section {
    margin: 20px auto;
    max-width: 900px;
    background: #FFFFFF;
    border: 1px solid #E8E6DC;
    border-radius: 12px;
    padding: 20px;
  }
  .live-files-section h2 {
    font-size: 18px;
    color: #B96748;
    margin-bottom: 4px;
  }
  .live-file-card {
    border-bottom: 1px solid #E8E6DC;
    overflow: hidden;
  }
  .live-file-card:last-child { border-bottom: none; }
  .live-file-header {
    padding: 10px 0;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
    transition: color 0.15s;
  }
  .live-file-header:hover .live-file-label { color: #B96748; }
  .live-file-label { font-weight: 600; font-size: 14px; transition: color 0.15s; }
  .live-file-meta { font-size: 11px; color: #B0AEA5; display: flex; gap: 10px; align-items: center; }
  .live-file-meta .stale { color: #C97B5A; font-weight: 400; }
  .live-file-meta .fresh { color: #2B8A3E; }
  .live-file-desc { font-size: 11px; color: #B0AEA5; margin-left: 8px; }
  .live-file-content {
    display: none;
    padding: 0 0 12px;
    max-height: 500px;
    overflow-y: auto;
    font-family: 'SF Mono', Monaco, monospace;
    font-size: 12px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    color: #6B6962;
  }
  .live-file-card.open .live-file-content { display: block; }
  .live-file-card.open .live-file-label { color: #B96748; }
  .live-file-missing { color: #B0AEA5; font-style: italic; }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #C97B5A; border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: #B96748; }
  * { scrollbar-width: thin; scrollbar-color: #C97B5A transparent; }
  #stream-section .heatmap-subtitle { margin-bottom: 0; }
  @media (max-width: 720px) {
    .heatmap-row { flex-direction: column; }
    .todos-section { grid-template-columns: 1fr; }
    .heatmap-section { overflow: hidden; }
    .heatmap-days span { width: 16px; font-size: 9px; padding-right: 2px; }
    .heatmap-wrap { gap: 4px; }
    .heatmap-months { margin-left: 22px; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>Claude Imprint</h1>
  <button class="lang-btn" onclick="toggleLang()" title="Switch language"><span id="lang-label">EN</span></button>
</div>

<div class="grid" id="components"></div>

<div class="info-bar">
  <div class="info-chip">
    <div class="label">Tunnel URL</div>
    <div class="value" id="tunnel-url">-</div>
  </div>
  <div class="info-chip">
    <div class="label">Memories</div>
    <div class="value" id="memory-count">-</div>
  </div>
  <div class="info-chip">
    <div class="label">Today's Logs</div>
    <div class="value" id="today-logs">-</div>
  </div>
</div>

<div class="heatmap-row">
  <div class="heatmap-section">
    <h2>Interaction History</h2>
    <div class="heatmap-subtitle">Darker = more activity that day</div>
    <div id="heatmap">Loading...</div>
    <div class="heatmap-legend">
      <span>Less</span>
      <div class="heatmap-cell"></div>
      <div class="heatmap-cell" data-level="1"></div>
      <div class="heatmap-cell" data-level="2"></div>
      <div class="heatmap-cell" data-level="3"></div>
      <div class="heatmap-cell" data-level="4"></div>
      <span>More</span>
    </div>
  </div>
  <div class="heatmap-sidebar">
    <div class="sidebar-card fragment-card">
      <div class="fragment-header">
        <h3>Memory Fragment</h3>
        <span class="fragment-date" id="fragment-date"></span>
      </div>
      <div class="fragment-body">
        <div class="fragment-content" id="fragment-text">Loading...</div>
        <button class="fragment-refresh" onclick="fetchFragment()" title="Refresh">&#x21bb;</button>
      </div>
    </div>
    <div class="sidebar-card" style="flex:1;">
      <h3>System</h3>
      <div class="status-grid">
        <div class="status-item"><div class="num" id="ns-days">-</div><div class="label">days</div></div>
        <div class="status-item"><div class="num" id="ns-total">-</div><div class="label">messages</div></div>
        <div class="status-item"><div class="num" id="ns-today">-</div><div class="label">today</div></div>
        <div class="status-item"><div class="num" id="ns-heartbeat">-</div><div class="label">heartbeat</div></div>
      </div>
    </div>
  </div>
</div>

<div class="memory-section" id="stream-section">
  <h2>Stream</h2>
  <div class="heatmap-subtitle">conversation_log — full message archive</div>
  <div id="stream-stats" style="margin-top:12px;">Loading...</div>
</div>

<div class="tasks-section">
  <h2>Scheduled Tasks</h2>
  <div id="tasks-list">Loading...</div>
</div>

<div class="todos-section">
  <div class="todo-card">
    <h3>System Tasks</h3>
    <div class="todo-content" id="system-todo-content">Loading...</div>
  </div>
  <div class="todo-card">
    <h3>Backlog</h3>
    <div class="todo-content" id="backlog-display">Loading...</div>
    <textarea class="todo-edit-area" id="backlog-edit-area" placeholder="Use Markdown, e.g.:&#10;- [ ] Task to do&#10;- [x] Completed task"></textarea>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button class="todo-edit-btn" id="backlog-edit-btn" onclick="toggleBacklogEdit()">Edit</button>
      <button class="todo-edit-btn primary" id="backlog-save-btn" style="display:none;" onclick="saveBacklog()">Save</button>
      <button class="todo-edit-btn" id="backlog-cancel-btn" style="display:none;" onclick="cancelBacklogEdit()">Cancel</button>
    </div>
  </div>
</div>

<div class="memory-section" id="stm-section">
  <h2>Horizon</h2>
  <div class="heatmap-subtitle" id="stm-meta">Loading...</div>
  <div id="stm-summaries" style="margin-bottom:12px;"></div>
  <details id="stm-details">
    <summary style="cursor:pointer;color:#B96748;font-size:13px;margin-bottom:8px;">Show raw messages</summary>
    <div id="stm-messages" style="max-height:400px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.6;color:#6B6962;"></div>
  </details>
</div>

<div class="tasks-section">
  <h2>Remote Tool Log</h2>
  <div class="heatmap-subtitle">Tool calls from Claude.ai chat</div>
  <div id="remote-tools" style="margin-top:12px;max-height:400px;overflow-y:scroll;">Loading...</div>
</div>

<div class="memory-section" id="summaries-section">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px;">
    <div>
      <h2 style="margin-bottom:4px;">对话摘要</h2>
      <div class="heatmap-subtitle">rolling summary — 跨窗口上下文</div>
    </div>
    <button class="fragment-refresh" onclick="fetchSummaries()" title="Refresh">&#x21bb;</button>
  </div>
  <input class="search-box" type="text" placeholder="搜索摘要..." id="summary-search" oninput="fetchSummaries()">
  <div id="summaries-list">Loading...</div>
</div>

<div class="memory-section" id="memory-section">
  <div class="memory-title-row">
    <h2>Memory</h2>
    <span class="search-mode-pill unknown" id="search-mode" title="Checking retrieval mode...">Checking...</span>
  </div>
  <div class="decay-stat-row" id="decay-status">Loading...</div>
  <input class="search-box" type="text" placeholder="Search memories..." id="memory-search" oninput="searchMemories()">
  <div id="memory-list" style="max-height:500px;overflow-y:auto;"></div>
</div>

<div class="live-files-section">
  <h2>Live Files</h2>
  <div class="heatmap-subtitle">Dynamically-updated config and memory files</div>
  <div id="live-files" style="margin-top:12px;">Loading...</div>
</div>

<div class="modal-overlay" id="edit-modal">
  <div class="modal">
    <h3>Edit Memory</h3>
    <input type="hidden" id="edit-id">
    <textarea id="edit-content"></textarea>
    <div class="modal-row">
      <select id="edit-category">
        <option value="core_profile">core_profile</option>
        <option value="task_state">task_state</option>
        <option value="episode">episode</option>
        <option value="atomic">atomic</option>
        <option value="facts">facts</option>
        <option value="events">events</option>
        <option value="tasks">tasks</option>
        <option value="experience">experience</option>
        <option value="general">general</option>
      </select>
      <input type="number" id="edit-importance" min="1" max="10" placeholder="Importance 1-10">
    </div>
    <div class="modal-row">
      <div class="modal-field">
        <label for="edit-valence">valence</label>
        <input type="number" id="edit-valence" min="0" max="1" step="0.05">
      </div>
      <div class="modal-field">
        <label for="edit-arousal">arousal</label>
        <input type="number" id="edit-arousal" min="0" max="1" step="0.05">
      </div>
      <div class="modal-field">
        <label for="edit-decay-rate">decay_rate</label>
        <input type="number" id="edit-decay-rate" min="0" step="0.01">
      </div>
    </div>
    <div class="modal-checks">
      <label><input type="checkbox" id="edit-resolved"> resolved</label>
      <label><input type="checkbox" id="edit-pinned"> pinned</label>
    </div>
    <div class="modal-buttons">
      <button onclick="closeEditModal()">Cancel</button>
      <button class="save" onclick="saveMemory()">Save</button>
    </div>
  </div>
</div>

<div class="modal-overlay" id="summary-edit-modal">
  <div class="modal">
    <h3>编辑摘要</h3>
    <input type="hidden" id="summary-edit-id">
    <textarea id="summary-edit-content"></textarea>
    <div class="modal-row">
      <input type="text" id="summary-edit-platform" placeholder="platform">
      <input type="number" id="summary-edit-turn-count" min="0" placeholder="turn_count">
    </div>
    <div class="modal-buttons">
      <button onclick="closeSummaryEditModal()">Cancel</button>
      <button class="save" onclick="saveSummary()">Save</button>
    </div>
  </div>
</div>

<script>
// ─── i18n ───
const i18n = {
  en: {
    loading: 'Loading...',
    running: 'Running', stopped: 'Stopped',
    terminal: 'Terminal', background: 'Background',
    logs: 'Logs',
    tunnelUrl: 'Tunnel URL', memories: 'Memories', todayLogs: "Today's Logs",
    notRunning: 'Not running',
    heatmapTitle: 'Interaction History',
    heatmapSub: 'Darker = more activity that day',
    less: 'Less', more: 'More',
    interactions: 'interactions', quietDay: 'quiet day',
    scheduledTasks: 'Scheduled Tasks',
    noTasks: 'No scheduled tasks',
    remoteLog: 'Remote Tool Log',
    remoteLogSub: 'Tool calls from Claude.ai chat',
    noRemote: 'No remote calls yet',
    streamTitle: 'Stream',
    streamSub: 'conversation_log — full message archive',
    streamTotal: 'total',
    streamToday: 'today',
    streamLast: 'Latest',
    horizonTitle: 'Horizon',
    summariesTitle: '对话摘要',
    summariesSub: 'rolling summary — 跨窗口上下文',
    summarySearchPlaceholder: '搜索摘要...',
    noSummariesPanel: '暂无摘要',
    editSummary: '编辑摘要',
    confirmDeleteSummary: '删除这条摘要？',
    turns: 'turns',
    memoryTitle: 'Memory',
    searchPlaceholder: 'Search memories...',
    searchModeChecking: 'Checking...',
    searchModeVector: 'Vector Search',
    searchModeFallback: 'Text-only (Fallback)',
    searchModeUnknown: 'Search status unavailable',
    searchModeVectorTip: 'Vector engine is responding; semantic retrieval is available.',
    searchModeFallbackTip: 'Vector engine is not responding; current searches use text-only retrieval.',
    noMemories: 'No memories yet',
    edit: 'Edit', delete: 'Delete', cancel: 'Cancel', save: 'Save',
    editMemory: 'Edit Memory',
    importance: 'Importance 1-10',
    confirmDelete: 'Delete this memory?',
    actionFailed: 'Action failed',
    noData: 'No data',
    noFragment: 'No memories yet',
    fragmentTitle: 'Memory Fragment',
    systemTitle: 'System',
    daysLabel: 'days', messagesLabel: 'messages', todayLabel: 'today', heartbeatLabel: 'heartbeat',
    systemTasks: 'System Tasks',
    backlog: 'Backlog',
    editBtn: 'Edit', saveBtn: 'Save', cancelBtn: 'Cancel',
    liveFiles: 'Live Files',
    liveFilesSub: 'Dynamically-updated config and memory files',
    noFiles: 'No files',
    fileMissing: 'File not found',
    noSummaries: 'No compression summaries yet',
    summaryHeader: 'Compressed Summaries',
    showMessages: 'Show raw messages',
    noMessages: 'No messages',
    stmMissing: 'recent_context.md not found',
    summaries: 'summaries', originals: 'originals', compressed: 'compressed',
    days: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],
    months: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  },
  zh: {
    loading: '加载中...',
    running: '运行中', stopped: '已停止',
    terminal: '终端', background: '后台',
    logs: '日志',
    tunnelUrl: '隧道地址', memories: '记忆数', todayLogs: '今日日志',
    notRunning: '未运行',
    heatmapTitle: '互动历史',
    heatmapSub: '颜色越深 = 当天互动越多',
    less: '少', more: '多',
    interactions: '次互动', quietDay: '无互动',
    scheduledTasks: '定时任务',
    noTasks: '暂无定时任务',
    remoteLog: '远程工具日志',
    remoteLogSub: '来自 Claude.ai chat 的工具调用',
    noRemote: '暂无远程调用',
    streamTitle: 'Stream 对话流',
    streamSub: 'conversation_log 全量原文归档',
    streamTotal: '条总记录',
    streamToday: '条今日',
    streamLast: '最新',
    horizonTitle: 'Horizon 视野',
    summariesTitle: '对话摘要',
    summariesSub: 'rolling summary — 跨窗口上下文',
    summarySearchPlaceholder: '搜索摘要...',
    noSummariesPanel: '暂无摘要',
    editSummary: '编辑摘要',
    confirmDeleteSummary: '确定删除这条摘要？',
    turns: 'turns',
    memoryTitle: '记忆库',
    searchPlaceholder: '搜索记忆...',
    searchModeChecking: '检测中...',
    searchModeVector: '向量检索',
    searchModeFallback: '纯文本检索（降级）',
    searchModeUnknown: '检索状态不可用',
    searchModeVectorTip: '向量引擎响应正常，语义检索可用。',
    searchModeFallbackTip: '向量引擎未响应，当前使用纯文本检索。',
    noMemories: '暂无记忆',
    edit: '编辑', delete: '删除', cancel: '取消', save: '保存',
    editMemory: '编辑记忆',
    importance: '重要性 1-10',
    confirmDelete: '确定删除这条记忆？',
    actionFailed: '操作失败',
    noData: '暂无数据',
    noFragment: '暂无记忆',
    fragmentTitle: '记忆碎片',
    systemTitle: '系统状态',
    daysLabel: '天', messagesLabel: '条消息', todayLabel: '今日互动', heartbeatLabel: '上次心跳',
    systemTasks: '系统待办',
    backlog: '待办清单',
    editBtn: '编辑', saveBtn: '保存', cancelBtn: '取消',
    liveFiles: '系统文件监控',
    liveFilesSub: '所有动态更新的配置和记忆文件',
    noFiles: '暂无文件',
    fileMissing: '文件不存在',
    noSummaries: '暂无压缩总结',
    summaryHeader: '压缩总结',
    showMessages: '展开原文消息',
    noMessages: '暂无消息',
    stmMissing: 'recent_context.md 不存在',
    summaries: '条摘要', originals: '条原文', compressed: '压缩',
    days: ['日','一','二','三','四','五','六'],
    months: ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'],
  }
};
let lang = localStorage.getItem('imprint-lang') || 'en';
function t(key) { return i18n[lang][key] || i18n.en[key] || key; }
function toggleLang() {
  lang = lang === 'en' ? 'zh' : 'en';
  localStorage.setItem('imprint-lang', lang);
  document.getElementById('lang-label').textContent = lang === 'en' ? 'EN' : '中文';
  refreshAll();
}
function applyStaticI18n() {
  document.getElementById('lang-label').textContent = lang === 'en' ? 'EN' : '中文';
  document.querySelector('.heatmap-section h2').textContent = t('heatmapTitle');
  document.querySelector('.heatmap-section .heatmap-subtitle').textContent = t('heatmapSub');
  const legend = document.querySelectorAll('.heatmap-legend > span');
  if (legend.length >= 2) { legend[0].textContent = t('less'); legend[legend.length-1].textContent = t('more'); }
  const taskSections = document.querySelectorAll('.tasks-section h2');
  if (taskSections[0]) taskSections[0].textContent = t('scheduledTasks');
  if (taskSections[1]) taskSections[1].textContent = t('remoteLog');
  const remoteSub = document.querySelectorAll('.tasks-section .heatmap-subtitle');
  if (remoteSub[0]) remoteSub[0].textContent = t('remoteLogSub');
  const streamH2 = document.querySelector('#stream-section h2');
  if (streamH2) streamH2.textContent = t('streamTitle');
  const streamSub = document.querySelector('#stream-section .heatmap-subtitle');
  if (streamSub) streamSub.textContent = t('streamSub');
  const stmH2 = document.querySelector('#stm-section h2');
  if (stmH2) stmH2.textContent = t('horizonTitle');
  const summariesH2 = document.querySelector('#summaries-section h2');
  if (summariesH2) summariesH2.textContent = t('summariesTitle');
  const summariesSub = document.querySelector('#summaries-section .heatmap-subtitle');
  if (summariesSub) summariesSub.textContent = t('summariesSub');
  const summarySearch = document.getElementById('summary-search');
  if (summarySearch) summarySearch.placeholder = t('summarySearchPlaceholder');
  const memTitle = document.querySelector('#memory-section .memory-title-row h2');
  if (memTitle) memTitle.textContent = t('memoryTitle');
  document.getElementById('memory-search').placeholder = t('searchPlaceholder');
  document.querySelector('.modal h3').textContent = t('editMemory');
  const summaryModalTitle = document.querySelector('#summary-edit-modal h3');
  if (summaryModalTitle) summaryModalTitle.textContent = t('editSummary');
  document.getElementById('edit-importance').placeholder = t('importance');
  const modalBtns = document.querySelectorAll('.modal-buttons button');
  if (modalBtns[0]) modalBtns[0].textContent = t('cancel');
  if (modalBtns[1]) modalBtns[1].textContent = t('save');
  const summaryModalBtns = document.querySelectorAll('#summary-edit-modal .modal-buttons button');
  if (summaryModalBtns[0]) summaryModalBtns[0].textContent = t('cancel');
  if (summaryModalBtns[1]) summaryModalBtns[1].textContent = t('save');
  const infoLabels = document.querySelectorAll('.info-chip .label');
  if (infoLabels[0]) infoLabels[0].textContent = t('tunnelUrl');
  if (infoLabels[1]) infoLabels[1].textContent = t('memories');
  if (infoLabels[2]) infoLabels[2].textContent = t('todayLogs');
  // sidebar cards
  const fragH3 = document.querySelector('.fragment-header h3');
  if (fragH3) fragH3.textContent = t('fragmentTitle');
  const sysH3 = document.querySelectorAll('.heatmap-sidebar .sidebar-card h3');
  if (sysH3.length >= 2) sysH3[1].textContent = t('systemTitle');
  // status labels
  const statusLabels = document.querySelectorAll('.status-item .label');
  if (statusLabels.length >= 4) {
    statusLabels[0].textContent = t('daysLabel');
    statusLabels[1].textContent = t('messagesLabel');
    statusLabels[2].textContent = t('todayLabel');
    statusLabels[3].textContent = t('heartbeatLabel');
  }
  // todos
  const todoH3s = document.querySelectorAll('.todo-card h3');
  if (todoH3s[0]) todoH3s[0].textContent = t('systemTasks');
  if (todoH3s[1]) todoH3s[1].textContent = t('backlog');
  document.getElementById('backlog-edit-btn').textContent = t('editBtn');
  document.getElementById('backlog-save-btn').textContent = t('saveBtn');
  document.getElementById('backlog-cancel-btn').textContent = t('cancelBtn');
  // live files
  const lfH2 = document.querySelector('.live-files-section h2');
  if (lfH2) lfH2.textContent = t('liveFiles');
  const lfSub = document.querySelector('.live-files-section .heatmap-subtitle');
  if (lfSub) lfSub.textContent = t('liveFilesSub');
}
function refreshAll() {
  applyStaticI18n();
  fetchStatus();
  fetchHeatmap();
  fetchSystemStatus();
  fetchSearchStatus();
  fetchFragment();
  fetchStreamStats();
  fetchSummaries();
  fetchShortTermMemory();
  fetchTodos();
  searchMemories();
  fetchRemoteTools();
  fetchLiveFiles();
}

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    renderComponents(data.components);
    renderTasks(data.tasks || []);
    document.getElementById('tunnel-url').textContent = data.tunnel_url ? data.tunnel_url : t('notRunning');
    document.getElementById('memory-count').textContent = data.memory.count;
    document.getElementById('today-logs').textContent = data.memory.today_logs;
  } catch(e) {
    console.error(e);
  }
}

function renderComponents(components) {
  const grid = document.getElementById('components');
  let html = '';
  for (const [key, comp] of Object.entries(components)) {
    const dotClass = comp.running ? 'on' : 'off';
    const statusText = comp.running ? t('running') : t('stopped');
    const checked = comp.running ? 'checked' : '';
    const typeLabel = comp.type === 'terminal' ? t('terminal') : t('background');
    html += `
      <div class="card">
        <div class="card-header">
          <span>
            <span class="status-dot ${dotClass}"></span>
            <span class="card-name">${comp.name}</span>
          </span>
          <label class="toggle">
            <input type="checkbox" ${checked} onchange="toggleComponent('${key}', this)">
            <span class="slider"></span>
          </label>
        </div>
        <div class="card-info">
          ${statusText} · ${typeLabel}${comp.pid ? ' · PID ' + comp.pid : ''}
          ${comp.type === 'background' ? '<br><button class="log-btn" onclick="toggleLog(\\'' + key + '\\')">' + t('logs') + '</button><div class="log-box" id="log-' + key + '"></div>' : ''}
        </div>
      </div>`;
  }
  grid.innerHTML = html;
}

function renderTasks(tasks) {
  const list = document.getElementById('tasks-list');
  if (!tasks.length) {
    list.innerHTML = '<div style="color:#B0AEA5;text-align:center;padding:12px">' + t('noTasks') + '</div>';
    return;
  }
  list.innerHTML = tasks.map(t => `
    <div class="task-item">
      <span class="task-dot"></span>
      <span>
        <span class="task-name">${t.name}</span>
        <div class="task-desc">${t.description}</div>
      </span>
    </div>
  `).join('');
}

async function toggleComponent(key, toggle) {
  const on = toggle.checked;
  const action = on ? 'start' : 'stop';
  toggle.disabled = true;
  try {
    const r = await fetch(`/api/${key}/${action}`, { method: 'POST' });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.ok === false) {
      toggle.checked = !on;
      alert(data.error || t('actionFailed'));
      await fetchStatus();
      return;
    }
    setTimeout(fetchStatus, 1500);
  } catch (e) {
    toggle.checked = !on;
    alert((e && e.message) ? e.message : t('actionFailed'));
    await fetchStatus();
  } finally {
    toggle.disabled = false;
  }
}

async function toggleLog(key) {
  const box = document.getElementById('log-' + key);
  if (box.style.display === 'block') {
    box.style.display = 'none';
    return;
  }
  const r = await fetch(`/api/logs/${key}`);
  const data = await r.json();
  box.textContent = data.logs;
  box.style.display = 'block';
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(text) {
  return String(text === null || text === undefined ? '' : text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function fetchSummaries() {
  try {
    const q = document.getElementById('summary-search')?.value || '';
    const r = await fetch(`/api/summaries?q=${encodeURIComponent(q)}&limit=10`);
    if (!r.ok) throw new Error('summary fetch failed');
    const summaries = await r.json();
    renderSummaries(summaries);
  } catch(e) { console.error('summaries fetch error:', e); }
}

let allSummaries = [];
function renderSummaries(summaries) {
  allSummaries = summaries || [];
  const list = document.getElementById('summaries-list');
  if (!list) return;
  if (!summaries || !summaries.length) {
    list.innerHTML = '<div style="color:#B0AEA5;padding:12px 0;text-align:center">' + t('noSummariesPanel') + '</div>';
    return;
  }
  list.innerHTML = summaries.map(s => {
    const turns = (s.turn_count || 0) > 0 ? ' · ' + s.turn_count + ' ' + t('turns') : '';
    return '<div class="memory-item">'
      + '<div class="memory-meta">[' + escapeHtml(s.platform || 'unknown') + '] ' + escapeHtml(s.created_at || '') + turns + '</div>'
      + '<div style="padding-right:80px;margin-top:6px;white-space:pre-wrap;line-height:1.6;">' + escapeHtml(s.content) + '</div>'
      + '<div class="memory-actions">'
      + '<button onclick="openSummaryEditModal(' + s.id + ')">' + t('edit') + '</button>'
      + '<button class="del" onclick="deleteSummary(' + s.id + ')">' + t('delete') + '</button>'
      + '</div>'
      + '</div>';
  }).join('');
}

async function deleteSummary(id) {
  if (!confirm(t('confirmDeleteSummary'))) return;
  const r = await fetch('/api/summaries/' + id, {method: 'DELETE'});
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    alert(data.error || t('actionFailed'));
    return;
  }
  fetchSummaries();
}

function openSummaryEditModal(id) {
  const s = allSummaries.find(x => x.id === id);
  if (!s) return;
  document.getElementById('summary-edit-id').value = s.id;
  document.getElementById('summary-edit-content').value = s.content || '';
  document.getElementById('summary-edit-platform').value = s.platform || 'unknown';
  document.getElementById('summary-edit-turn-count').value = s.turn_count || 0;
  document.getElementById('summary-edit-modal').classList.add('active');
}

function closeSummaryEditModal() {
  document.getElementById('summary-edit-modal').classList.remove('active');
}

async function saveSummary() {
  const id = document.getElementById('summary-edit-id').value;
  const body = {
    content: document.getElementById('summary-edit-content').value,
    platform: document.getElementById('summary-edit-platform').value,
    turn_count: parseInt(document.getElementById('summary-edit-turn-count').value) || 0,
  };
  const r = await fetch('/api/summaries/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    alert(data.error || t('actionFailed'));
    return;
  }
  closeSummaryEditModal();
  fetchSummaries();
}

async function searchMemories() {
  try {
    const q = document.getElementById('memory-search').value;
    const r = await fetch(`/api/memories?q=${encodeURIComponent(q)}&limit=20`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'memory fetch failed');
    renderMemories(data.memories || []);
    fetchDecayStatus();
  } catch(e) {
    console.error('memory fetch error:', e);
  }
}

let allMemories = [];
function formatMemoryNumber(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toFixed(digits).replace(/\.?0+$/, '');
}

function memoryDecayStatus(m) {
  const ds = m.decay_status || {key: 'decaying', label: 'Decaying', zh: '衰减中'};
  return {
    key: ds.key || 'decaying',
    label: lang === 'zh' ? (ds.zh || ds.label || ds.key) : (ds.label || ds.key),
  };
}

function renderMemories(memories) {
  allMemories = memories || [];
  const list = document.getElementById('memory-list');
  if (!allMemories.length) {
    list.innerHTML = '<div style="color:#666;padding:20px;text-align:center">' + t('noMemories') + '</div>';
    return;
  }
  list.innerHTML = allMemories.map(m => {
    const ds = memoryDecayStatus(m);
    const resolved = m.resolved ? (lang === 'zh' ? '已解决' : 'resolved') : (lang === 'zh' ? '未解决' : 'open');
    const pinned = m.pinned ? (lang === 'zh' ? 'pinned 是' : 'pinned yes') : (lang === 'zh' ? 'pinned 否' : 'pinned no');
    const lastActive = m.last_active ? escapeHtml(m.last_active) : '-';
    const decayRate = m.decay_rate === null || m.decay_rate === undefined ? '-' : formatMemoryNumber(m.decay_rate, 3);
    const activationCount = m.activation_count === null || m.activation_count === undefined ? '-' : m.activation_count;
    const meta = '[' + escapeHtml(m.category || 'general') + '|' + escapeHtml(m.source || '') + '] '
      + escapeHtml(m.created_at || '') + ' · importance ' + escapeHtml(m.importance || 5);
    return `
      <div class="memory-item">
        <div class="memory-content">${escapeHtml(m.content || '')}</div>
        <div class="memory-meta">${meta}</div>
        <div class="memory-badges">
          <span class="memory-badge ${escapeHtml(ds.key)}">${escapeHtml(ds.label)}</span>
          <span class="memory-badge">V ${formatMemoryNumber(m.valence)}</span>
          <span class="memory-badge">A ${formatMemoryNumber(m.arousal)}</span>
          <span class="memory-badge">${resolved}</span>
          <span class="memory-badge">${pinned}</span>
          <span class="memory-badge">decay ${decayRate}</span>
          <span class="memory-badge">act ${escapeHtml(activationCount)}</span>
          <span class="memory-badge">last ${lastActive}</span>
        </div>
        <div class="memory-actions">
          <button onclick="openEditModal(${m.id})">${t('edit')}</button>
          <button class="del" onclick="deleteMemory(${m.id})">${t('delete')}</button>
        </div>
      </div>
    `;
  }).join('');
}

async function deleteMemory(id) {
  if (!confirm(t('confirmDelete'))) return;
  const r = await fetch('/api/memories/' + id, {method: 'DELETE'});
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    alert(data.error || t('actionFailed'));
    return;
  }
  searchMemories();
}

function openEditModal(id) {
  const m = allMemories.find(x => x.id === id);
  if (!m) return;
  document.getElementById('edit-id').value = m.id;
  document.getElementById('edit-content').value = m.content || '';
  const categorySelect = document.getElementById('edit-category');
  if (![...categorySelect.options].some(o => o.value === (m.category || 'general'))) {
    const option = document.createElement('option');
    option.value = m.category || 'general';
    option.textContent = m.category || 'general';
    categorySelect.appendChild(option);
  }
  categorySelect.value = m.category || 'general';
  document.getElementById('edit-importance').value = m.importance || 5;
  document.getElementById('edit-valence').value = formatMemoryNumber(m.valence ?? 0.5);
  document.getElementById('edit-arousal').value = formatMemoryNumber(m.arousal ?? 0.3);
  document.getElementById('edit-resolved').checked = !!m.resolved;
  document.getElementById('edit-pinned').checked = !!m.pinned;
  document.getElementById('edit-decay-rate').value = m.decay_rate === null || m.decay_rate === undefined ? '' : formatMemoryNumber(m.decay_rate, 3);
  document.getElementById('edit-modal').classList.add('active');
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('active');
}

async function saveMemory() {
  const id = document.getElementById('edit-id').value;
  const body = {
    content: document.getElementById('edit-content').value,
    category: document.getElementById('edit-category').value,
    importance: parseInt(document.getElementById('edit-importance').value) || 5,
    valence: parseFloat(document.getElementById('edit-valence').value),
    arousal: parseFloat(document.getElementById('edit-arousal').value),
    resolved: document.getElementById('edit-resolved').checked,
    pinned: document.getElementById('edit-pinned').checked,
    decay_rate: document.getElementById('edit-decay-rate').value,
  };
  const r = await fetch('/api/memories/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) {
    alert(data.error || t('actionFailed'));
    return;
  }
  closeEditModal();
  searchMemories();
}

async function fetchDecayStatus() {
  try {
    const el = document.getElementById('decay-status');
    if (!el) return;
    const r = await fetch('/api/decay-status');
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'decay status fetch failed');
    const labels = lang === 'zh'
      ? [['total','总数'], ['protected','保护'], ['surfacing','主动浮现'], ['resolved','已解决'], ['archived','已归档'], ['low_score','低分'], ['decaying','衰减中']]
      : [['total','total'], ['protected','protected'], ['surfacing','surfacing'], ['resolved','resolved'], ['archived','archived'], ['low_score','low score'], ['decaying','decaying']];
    el.innerHTML = labels.map(([key, label]) => '<span class="decay-stat-chip">' + escapeHtml(label) + ' <strong>' + escapeHtml(data[key] || 0) + '</strong></span>').join('');
  } catch(e) {
    console.error('decay status error:', e);
  }
}

async function fetchSystemStatus() {
  try {
    const r = await fetch('/api/system-status');
    const data = await r.json();
    document.getElementById('ns-days').textContent = data.days_active || '0';
    document.getElementById('ns-total').textContent = data.total_messages || '0';
    document.getElementById('ns-today').textContent = data.today_messages || '0';
    if (data.last_heartbeat) {
      document.getElementById('ns-heartbeat').textContent = data.last_heartbeat.substring(11, 16);
    } else {
      document.getElementById('ns-heartbeat').textContent = '-';
    }
  } catch(e) { console.error(e); }
}

async function fetchSearchStatus() {
  const el = document.getElementById('search-mode');
  if (!el) return;
  try {
    const r = await fetch('/api/search-status');
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || 'search status fetch failed');
    const isVector = data.mode === 'vector' && !data.fallback;
    el.className = 'search-mode-pill ' + (isVector ? 'vector' : 'fallback');
    el.textContent = isVector ? t('searchModeVector') : t('searchModeFallback');
    const baseTip = isVector ? t('searchModeVectorTip') : t('searchModeFallbackTip');
    const detail = [data.provider, data.model].filter(Boolean).join(' · ');
    const reason = data.reason ? ' · ' + data.reason : '';
    el.title = baseTip + (detail ? ' · ' + detail : '') + reason;
  } catch(e) {
    el.className = 'search-mode-pill unknown';
    el.textContent = t('searchModeUnknown');
    el.title = t('searchModeFallbackTip');
    console.error('search status error:', e);
  }
}

async function fetchFragment() {
  try {
    const r = await fetch('/api/memory-fragment');
    const data = await r.json();
    if (data.fragment) {
      document.getElementById('fragment-text').textContent = data.fragment.content;
      document.getElementById('fragment-date').textContent = data.fragment.date + ' · ' + data.fragment.category;
    } else {
      document.getElementById('fragment-text').textContent = t('noFragment');
      document.getElementById('fragment-date').textContent = '';
    }
  } catch(e) { console.error(e); }
}

async function fetchHeatmap() {
  try {
    const r = await fetch('/api/heatmap');
    const data = await r.json();
    renderHeatmap(data.days);
  } catch(e) { console.error(e); }
}

function renderHeatmap(days) {
  const container = document.getElementById('heatmap');
  if (!days || !days.length) {
    container.innerHTML = '<div style="color:#B0AEA5;text-align:center">' + t('noData') + '</div>';
    return;
  }

  const counts = days.map(d => d.count).filter(c => c > 0);
  const max = Math.max(...counts, 1);
  const q1 = max * 0.25, q2 = max * 0.5, q3 = max * 0.75;

  function level(c) {
    if (c === 0) return 0;
    if (c <= q1) return 1;
    if (c <= q2) return 2;
    if (c <= q3) return 3;
    return 4;
  }

  const firstDate = new Date(days[0].date + 'T00:00:00');
  const firstDay = firstDate.getDay();

  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  days.forEach(d => cells.push(d));

  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }

  const months = [];
  let lastMonth = '';
  weeks.forEach((week, wi) => {
    const realDay = week.find(d => d !== null);
    if (realDay) {
      const m = realDay.date.substring(0, 7);
      if (m !== lastMonth) {
        const monthNames = t('months');
        months.push({ index: wi, label: monthNames[parseInt(m.split('-')[1]) - 1] });
        lastMonth = m;
      }
    }
  });

  const dayLabels = t('days');
  const totalGridWidth = weeks.length * 15 - 3;

  // Day labels (fixed left)
  let daysHtml = '<div class="heatmap-days">';
  for (let i = 0; i < 7; i++) {
    daysHtml += '<span>' + (i % 2 === 1 ? dayLabels[i] : '') + '</span>';
  }
  daysHtml += '</div>';

  // Scrollable area: month labels + grid
  let scrollHtml = '<div class="heatmap-scroll" style="overflow-x:auto;flex:1;min-width:0;">';
  scrollHtml += '<div class="heatmap-months" style="display:flex;width:' + totalGridWidth + 'px;">';
  months.forEach((m, i) => {
    const next = months[i + 1] ? months[i + 1].index : weeks.length;
    const span = next - m.index;
    scrollHtml += '<span style="width:' + (span * 15) + 'px;flex-shrink:0">' + m.label + '</span>';
  });
  scrollHtml += '</div>';

  scrollHtml += '<div class="heatmap-grid" style="overflow-x:visible;">';
  weeks.forEach(week => {
    scrollHtml += '<div class="heatmap-col">';
    for (let i = 0; i < 7; i++) {
      const d = i < week.length ? week[i] : null;
      if (d === null) {
        scrollHtml += '<div class="heatmap-cell" style="visibility:hidden"></div>';
      } else {
        const lv = level(d.count);
        const tip = d.date + ': ' + (d.count > 0 ? d.count + ' ' + t('interactions') : t('quietDay'));
        scrollHtml += '<div class="heatmap-cell" data-level="' + lv + '"><span class="tooltip">' + tip + '</span></div>';
      }
    }
    scrollHtml += '</div>';
  });
  scrollHtml += '</div></div>';

  container.innerHTML = '<div class="heatmap-wrap">' + daysHtml + scrollHtml + '</div>';

  // Auto-scroll to latest
  const scrollEl = container.querySelector('.heatmap-scroll');
  if (scrollEl) scrollEl.scrollLeft = scrollEl.scrollWidth;
}

async function fetchStreamStats() {
  try {
    const r = await fetch('/api/stream-stats');
    const data = await r.json();
    const el = document.getElementById('stream-stats');
    if (!el) return;

    const platformTags = Object.entries(data.platforms || {}).map(([p, c]) => {
      const colors = {cc:'#B96748', telegram:'#0088cc', discord:'#5865F2', slack:'#4A154B', heartbeat:'#B0AEA5', channel:'#6A3EA1'};
      const color = colors[p] || '#6B6962';
      return '<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;border:1px solid '+color+';color:'+color+';margin:2px 4px 2px 0;">'+p+' '+c+'</span>';
    }).join('');

    let lastLine = '';
    if (data.last_message) {
      const lm = data.last_message;
      const arrow = lm.direction === 'in' ? '\\u2190' : '\\u2192';
      lastLine = '<div style="margin-top:10px;padding:8px 12px;background:#F5F4EF;border-radius:8px;font-size:12px;color:#6B6962;">'
        + '<span style="color:#B0AEA5;">' + t('streamLast') + '</span> '
        + '<span style="color:#B96748;font-weight:600;">[' + lm.platform + ' ' + arrow + ']</span> '
        + lm.content.replace(/</g,'&lt;')
        + '<span style="float:right;color:#B0AEA5;">' + (lm.time||'') + '</span>'
        + '</div>';
    }

    el.innerHTML = '<div style="display:flex;gap:20px;align-items:baseline;flex-wrap:wrap;">'
      + '<span style="font-size:28px;font-weight:700;color:#B96748;">' + (data.total||0).toLocaleString() + '</span>'
      + '<span style="color:#B0AEA5;font-size:13px;">' + t('streamTotal') + '</span>'
      + '<span style="font-size:20px;font-weight:600;color:#3D3D3A;">+' + (data.today||0) + '</span>'
      + '<span style="color:#B0AEA5;font-size:13px;">' + t('streamToday') + '</span>'
      + '</div>'
      + '<div style="margin-top:8px;">' + platformTags + '</div>'
      + lastLine;
  } catch(e) { console.error('stream stats error:', e); }
}

async function fetchShortTermMemory() {
  try {
    const r = await fetch('/api/short-term-memory');
    const data = await r.json();
    const meta = document.getElementById('stm-meta');
    const sumEl = document.getElementById('stm-summaries');
    const msgEl = document.getElementById('stm-messages');

    if (!data.exists) {
      meta.textContent = t('stmMissing');
      sumEl.innerHTML = '';
      msgEl.innerHTML = '';
      return;
    }

    const pct = Math.round((data.msg_count / data.threshold) * 100);
    const barColor = pct >= 90 ? '#c0392b' : pct >= 70 ? '#F59E0B' : '#B96748';
    const origCount = data.msg_count - (data.summarized_count || 0);
    meta.innerHTML = 'Updated: ' + data.updated + ' · ' + (data.summarized_count || 0) + ' ' + t('summaries') + ' + ' + origCount + ' ' + t('originals') + ' · ' + t('compressed') + ' ' + data.msg_count + '/' + data.threshold
      + '<div style="margin-top:6px;background:#EBEAE2;border-radius:4px;height:6px;max-width:300px;">'
      + '<div style="width:' + Math.min(pct,100) + '%;height:100%;background:' + barColor + ';border-radius:4px;transition:width 0.3s;"></div></div>';

    if (data.summaries.length) {
      sumEl.innerHTML = '<div style="background:#FFF8F0;border:1px solid #F0D1C2;border-radius:8px;padding:12px;font-size:13px;line-height:1.6;">'
        + '<div style="font-weight:600;color:#B96748;margin-bottom:6px;">' + t('summaryHeader') + '</div>'
        + data.summaries.map(s => '<div style="color:#6B6962;">' + s.replace(/</g,'&lt;') + '</div>').join('')
        + '</div>';
    } else {
      sumEl.innerHTML = '<div style="color:#B0AEA5;font-size:13px;">' + t('noSummaries') + '</div>';
    }

    if (data.messages.length) {
      msgEl.innerHTML = data.messages.map(m => {
        const escaped = m.replace(/</g, '&lt;');
        const isSummary = escaped.toLowerCase().includes('[summary]') || escaped.includes('[摘要]');
        let styled = escaped
          .replace(/\\[(.*?)(cc\\/in)\\]/,  '<span style="color:#B96748">[$1$2]</span>')
          .replace(/\\[(.*?)(cc\\/out)\\]/, '<span style="color:#7B8794">[$1$2]</span>')
          .replace(/\\[(.*?)(tg\\/in)\\]/,  '<span style="color:#0088cc">[$1$2]</span>')
          .replace(/\\[(.*?)(tg\\/out)\\]/, '<span style="color:#006699">[$1$2]</span>');
        if (isSummary) {
          styled = styled.replace(/\\[(summary|摘要)\\]/i, '<span style="background:#E8DEF8;color:#6A3EA1;padding:1px 4px;border-radius:3px;font-size:11px;margin-right:2px;">$1</span>');
        }
        const bg = isSummary ? 'background:#FAFAFE;' : '';
        return '<div style="padding:2px 0;border-bottom:1px solid #F5F4EF;' + bg + '">' + styled + '</div>';
      }).join('');
    } else {
      msgEl.innerHTML = '<div style="color:#B0AEA5;">' + t('noMessages') + '</div>';
    }
  } catch(e) { console.error('STM fetch error:', e); }
}

async function fetchLiveFiles() {
  try {
    const r = await fetch('/api/live-files');
    const data = await r.json();
    const el = document.getElementById('live-files');
    if (!data.files || !data.files.length) {
      el.innerHTML = '<div style="color:#B0AEA5;">' + t('noFiles') + '</div>';
      return;
    }
    const openKeys = new Set();
    el.querySelectorAll('.live-file-card.open').forEach(c => openKeys.add(c.dataset.key));

    let html = '';
    data.files.forEach(f => {
      const isOpen = openKeys.has(f.key) ? ' open' : '';
      const sizeStr = f.size > 1024 ? (f.size/1024).toFixed(1)+'KB' : f.size+'B';
      const timeClass = f.stale ? 'stale' : 'fresh';

      html += '<div class="live-file-card' + isOpen + '" data-key="' + f.key + '">';
      html += '<div class="live-file-header" onclick="this.parentElement.classList.toggle(&quot;open&quot;)">';
      html += '<div><span class="live-file-label">' + f.label + '</span>';
      html += '<span class="live-file-desc">' + f.desc + '</span></div>';

      if (f.exists) {
        html += '<div class="live-file-meta">';
        html += '<span>' + sizeStr + '</span>';
        html += '<span class="' + timeClass + '">' + f.mtime + '</span>';
        html += '</div>';
      } else {
        html += '<div class="live-file-meta"><span class="stale">' + t('fileMissing') + '</span></div>';
      }

      html += '</div>';
      if (f.exists && f.content) {
        const escaped = f.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        html += '<div class="live-file-content">' + escaped + '</div>';
      } else {
        html += '<div class="live-file-content live-file-missing">(' + t('fileMissing') + ')</div>';
      }
      html += '</div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error('live-files error:', e); }
}

async function fetchRemoteTools() {
  try {
    const r = await fetch('/api/remote-tools');
    const data = await r.json();
    const el = document.getElementById('remote-tools');
    if (!data.tasks || !data.tasks.length) {
      el.innerHTML = '<div style="color:#B0AEA5">' + t('noRemote') + '</div>';
      return;
    }
    const icons = {pending:'\\u25cb',running:'\\u25ce',completed:'\\u2713',error:'\\u2717',timeout:'\\u25cc'};
    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    data.tasks.forEach(t => {
      const icon = t.status in icons ? icons[t.status] : '?';
      const prompt = t.prompt.length > 60 ? t.prompt.substring(0,60)+'...' : t.prompt;
      const result = t.result ? (t.result.length > 120 ? t.result.substring(0,120)+'...' : t.result) : '';
      html += '<div style="padding:10px 0;border-bottom:1px solid #E8E6DC;font-size:13px;">';
      html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">';
      html += '<span style="color:#3D3D3A;">' + icon + ' <span style="color:#B96748;font-weight:400;">#' + t.id + '</span> ' + prompt + '</span>';
      html += '<span style="color:#B0AEA5;font-size:11px;white-space:nowrap;flex-shrink:0;">' + (t.created_at||'') + '</span>';
      html += '</div>';
      if (result) {
        html += '<div style="margin-top:6px;color:#8B8780;font-size:12px;line-height:1.6;white-space:pre-wrap;max-height:80px;overflow-y:auto;">' + result.replace(/</g,'&lt;') + '</div>';
      }
      html += '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

// ─── Todos ───
let backlogOrigContent = '';

function renderTodoMarkdown(text) {
  if (!text || !text.trim()) return '<span style="color:#B0AEA5;font-size:13px;">(empty)</span>';
  const lines = text.split('\\n');
  const out = [];
  for (const raw of lines) {
    const line = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    if (line.startsWith('&lt;!--')) continue;
    if (/^# /.test(line)) {
      continue;
    } else if (/^## /.test(line)) {
      out.push('<div style="font-weight:600;color:#6B6962;margin:6px 0 3px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;">' + line.slice(3) + '</div>');
    } else if (/^- \\[x\\] /.test(line)) {
      out.push('<div style="color:#B0AEA5;text-decoration:line-through;margin:2px 0;padding-left:4px;">\\u2611 ' + line.slice(6) + '</div>');
    } else if (/^- \\[ \\] /.test(line)) {
      out.push('<div style="color:#3D3D3A;margin:2px 0;padding-left:4px;">\\u2610 ' + line.slice(6) + '</div>');
    } else if (/^- /.test(line)) {
      out.push('<div style="color:#3D3D3A;margin:2px 0;padding-left:4px;">\\u2022 ' + line.slice(2) + '</div>');
    } else if (line.trim() === '') {
      out.push('<div style="height:4px"></div>');
    } else {
      out.push('<div style="color:#6B6962;font-size:12px;">' + line + '</div>');
    }
  }
  return out.join('');
}

async function fetchTodos() {
  const sysEl = document.getElementById('system-todo-content');
  const backlogEl = document.getElementById('backlog-display');
  try {
    const [sysR, backlogR] = await Promise.all([
      fetch('/api/todos/system'),
      fetch('/api/todos/backlog'),
    ]);
    const sysData = await sysR.json();
    const backlogData = await backlogR.json();

    if (sysEl) sysEl.innerHTML = renderTodoMarkdown(sysData.content || '');
    const editArea = document.getElementById('backlog-edit-area');
    const isEditing = editArea && editArea.style.display === 'block';
    if (!isEditing) {
      backlogOrigContent = backlogData.content || '';
      if (backlogEl) backlogEl.innerHTML = renderTodoMarkdown(backlogOrigContent);
      if (editArea) editArea.value = backlogOrigContent;
    }
  } catch(e) {
    console.error('todos fetch error:', e);
    if (sysEl) sysEl.innerHTML = '<span style="color:#c0392b;font-size:12px;">Load failed</span>';
    if (backlogEl) backlogEl.innerHTML = '<span style="color:#c0392b;font-size:12px;">Load failed</span>';
  }
}

function toggleBacklogEdit() {
  document.getElementById('backlog-display').style.display = 'none';
  document.getElementById('backlog-edit-area').style.display = 'block';
  document.getElementById('backlog-edit-area').value = backlogOrigContent;
  document.getElementById('backlog-edit-btn').style.display = 'none';
  document.getElementById('backlog-save-btn').style.display = 'inline-block';
  document.getElementById('backlog-cancel-btn').style.display = 'inline-block';
  document.getElementById('backlog-edit-area').focus();
}

function cancelBacklogEdit() {
  document.getElementById('backlog-display').style.display = 'block';
  document.getElementById('backlog-edit-area').style.display = 'none';
  document.getElementById('backlog-edit-btn').style.display = 'inline-block';
  document.getElementById('backlog-save-btn').style.display = 'none';
  document.getElementById('backlog-cancel-btn').style.display = 'none';
}

async function saveBacklog() {
  const content = document.getElementById('backlog-edit-area').value;
  try {
    const r = await fetch('/api/todos/backlog', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content}),
    });
    const data = await r.json();
    if (data.ok) {
      backlogOrigContent = content;
      document.getElementById('backlog-display').innerHTML = renderTodoMarkdown(content);
      cancelBacklogEdit();
    }
  } catch(e) { console.error('save backlog error:', e); }
}

// Init
applyStaticI18n();
fetchStatus();
fetchHeatmap();
fetchSystemStatus();
fetchSearchStatus();
fetchFragment();
fetchStreamStats();
fetchSummaries();
fetchShortTermMemory();
fetchTodos();
searchMemories();
fetchRemoteTools();
fetchLiveFiles();
setInterval(fetchStatus, 3000);
setInterval(fetchSystemStatus, 10000);
setInterval(fetchSearchStatus, 30000);
setInterval(fetchStreamStats, 10000);
setInterval(fetchSummaries, 10000);
setInterval(fetchShortTermMemory, 5000);
setInterval(fetchTodos, 15000);
setInterval(fetchRemoteTools, 10000);
setInterval(fetchLiveFiles, 10000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("Claude Imprint Dashboard: http://localhost:3000", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=3000, log_level="warning")
