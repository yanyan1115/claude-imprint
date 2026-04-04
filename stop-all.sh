#!/bin/bash
# Claude Imprint — Stop all services

cd "$(dirname "$0")"
echo "Stopping Claude Imprint..."

# Stop Heartbeat
if [ -f .pid-heartbeat ]; then
    kill $(cat .pid-heartbeat) 2>/dev/null && echo "   Heartbeat stopped" || echo "   Heartbeat not running"
    rm -f .pid-heartbeat
fi

# Stop Memory HTTP
if [ -f .pid-http ]; then
    kill $(cat .pid-http) 2>/dev/null && echo "   Memory HTTP stopped" || echo "   Memory HTTP not running"
    rm -f .pid-http
fi

# Stop Tunnel
if [ -f .pid-tunnel ]; then
    kill $(cat .pid-tunnel) 2>/dev/null && echo "   Tunnel stopped" || echo "   Tunnel not running"
    rm -f .pid-tunnel
fi

# Cleanup
pkill -f "imprint-memory --http" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null

echo "   Telegram window: close manually (Ctrl+C)"
echo ""
echo "Done"
