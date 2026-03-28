#!/bin/bash
# imprint-heartbeat — Start heartbeat agent
# Uses caffeinate to prevent Mac sleep

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd ../.. && pwd)"

export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

if ! command -v claude &>/dev/null; then
    echo "Error: claude CLI not found. Please install Claude Code first."
    exit 1
fi

echo "Starting Heartbeat Agent..."
echo "   Heartbeat interval: ${HEARTBEAT_INTERVAL:-900}s"
echo "   Logs: $PROJECT_ROOT/logs/agent.log"
echo "   Stop: ./stop.sh"
echo ""

mkdir -p "$PROJECT_ROOT/logs" "$PROJECT_ROOT/data"

if command -v caffeinate &>/dev/null; then
    echo "   Sleep prevention: caffeinate enabled"
    nohup caffeinate -i python3 -u agent.py >> "$PROJECT_ROOT/logs/agent.log" 2>&1 &
else
    nohup python3 -u agent.py >> "$PROJECT_ROOT/logs/agent.log" 2>&1 &
fi
echo $! > "$PROJECT_ROOT/.pid-heartbeat"

echo "Agent started (PID: $(cat "$PROJECT_ROOT/.pid-heartbeat"))"
echo "   View logs: tail -f $PROJECT_ROOT/logs/agent.log"
