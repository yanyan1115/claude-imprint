# Cloud / Linux Deployment

systemd service templates for running Claude Imprint on a Linux server.

## Setup

```bash
# 1. Install Claude Code on the server
# https://docs.anthropic.com/en/docs/claude-code

# 2. Clone and install
git clone https://github.com/Qizhan7/claude-imprint.git
cd claude-imprint
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Authenticate Claude Code
# Option A: OAuth token (for Max Plan)
mkdir -p ~/.claude
echo "your-oauth-token" > ~/.claude/cron-token

# Option B: API key
export ANTHROPIC_API_KEY=sk-...

# 4. Install systemd services
# Edit each .service file to match your paths and env vars first
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 5. Enable and start
sudo systemctl enable --now imprint-memory@$USER
sudo systemctl enable --now imprint-dashboard@$USER
sudo systemctl enable --now imprint-heartbeat@$USER
sudo systemctl enable --now imprint-tunnel@$USER      # if using Cloudflare
sudo systemctl enable --now imprint-telegram@$USER     # if using Telegram

# 6. Check status
sudo systemctl status imprint-memory@$USER
journalctl -u imprint-memory@$USER -f
```

## Quick start (without systemd)

If you just want to run everything without systemd:

```bash
./start.sh    # detects Linux, runs all services as background processes
./stop.sh     # stops everything
```

## Environment variables

Create a `.env` file or edit the service files directly:

```bash
IMPRINT_DATA_DIR=~/.imprint
TZ_OFFSET=0
HEARTBEAT_INTERVAL=900
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Notes

- **WeChat** requires QR code login — not practical on headless servers
- **Spotify control** is macOS-only (AppleScript) — skipped on Linux
- **Embedding**: Use `EMBED_PROVIDER=openai` on servers without GPU, or install Ollama
- **Cron tasks**: Use standard Linux crontab with `cron-task.sh`
