#!/bin/bash
# Claude Imprint — Stop all services
# Works on both macOS and Linux/cloud servers.

cd "$(dirname "$0")"
echo "Stopping Claude Imprint..."

stop_pid() {
    local name="$1" pidfile="$2"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "   ✓ $name stopped (PID: $pid)"
        else
            echo "   - $name not running"
        fi
        rm -f "$pidfile"
    fi
}

stop_pid "Memory HTTP"  .pid-http
stop_pid "Tunnel"       .pid-tunnel
stop_pid "Heartbeat"    .pid-heartbeat
stop_pid "Dashboard"    .pid-dashboard
stop_pid "Telegram"     .pid-telegram

# Cleanup: kill any orphan processes
pkill -f "imprint-memory --http" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true

IS_MAC=false
[[ "$(uname)" == "Darwin" ]] && IS_MAC=true

if $IS_MAC; then
    echo ""
    echo "   Note: Telegram Terminal window should be closed manually (Ctrl+C)"
else
    # On Linux, also kill background Telegram
    pkill -f "channels plugin:telegram" 2>/dev/null || true
fi

echo ""
echo "Done"
