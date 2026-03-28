#!/bin/bash
# imprint-heartbeat — Stop heartbeat agent

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PID_FILE="$PROJECT_ROOT/.pid-heartbeat"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Heartbeat agent stopped (PID: $PID)"
    else
        echo "Process $PID not running"
    fi
    rm -f "$PID_FILE"
else
    echo "No PID file found"
fi
