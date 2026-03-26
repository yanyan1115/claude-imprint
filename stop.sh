#!/bin/bash
# Claude Imprint — Stop heartbeat agent

cd "$(dirname "$0")"

if [ -f .pid-heartbeat ]; then
    PID=$(cat .pid-heartbeat)
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm .pid-heartbeat
        echo "Agent stopped (PID: $PID)"
    else
        rm .pid-heartbeat
        echo "Process already gone, cleaned up PID file"
    fi
else
    echo "No running agent found"
fi
