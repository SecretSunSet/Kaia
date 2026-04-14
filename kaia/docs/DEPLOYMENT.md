# KAIA Deployment Guide

---

## Requirements

### System

- Python 3.11+
- ffmpeg (for voice processing — Phase 6)

### Python Dependencies

All listed in `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| `python-telegram-bot` | >=20.0 | Telegram bot framework (async) |
| `anthropic` | >=0.25.0 | Claude API client |
| `groq` | >=0.5.0 | Groq API client (fallback AI) |
| `supabase` | >=2.0.0 | Supabase client (PostgreSQL) |
| `apscheduler` | >=3.10.0 | Job scheduler (reminders, briefing) |
| `httpx` | >=0.27.0 | Async HTTP client (web scraping) |
| `beautifulsoup4` | >=4.12.0 | HTML parsing (web scraping) |
| `python-dotenv` | >=1.0.0 | .env file loading |
| `loguru` | >=0.7.0 | Structured logging |
| `pydantic` | >=2.0.0 | Data validation |
| `pydantic-settings` | >=2.0.0 | Settings from env vars |
| `edge-tts` | >=6.1.0 | Text-to-speech (Microsoft) |
| `pydub` | >=0.25.1 | Audio format conversion |
| `python-dateutil` | >=2.8.0 | Date arithmetic (monthly recurrence) |

### External Services

| Service | Required | Free Tier | Purpose |
|---------|----------|-----------|---------|
| Telegram Bot API | Yes | Unlimited | Bot communication |
| Anthropic (Claude) | Yes | Pay-per-use | Primary AI engine |
| Supabase | Yes | 500 MB DB | Database |
| Groq | No | 30 req/min | Fallback AI |
| SerpAPI | No | 100/month | Web search (Phase 5) |
| OpenWeather | No | 1,000/day | Briefing weather (Phase 5) |
| NewsAPI | No | 100/day | Briefing headlines (Phase 5) |

---

## Environment Variables

### Required

```env
TELEGRAM_BOT_TOKEN=       # From @BotFather
ANTHROPIC_API_KEY=        # From console.anthropic.com
SUPABASE_URL=             # From Supabase project settings
SUPABASE_KEY=             # Supabase service-role or anon key
```

### Optional — AI

```env
GROQ_API_KEY=             # Enables Claude → Groq fallback
CLAUDE_MODEL=claude-sonnet-4-20250514
CLAUDE_MAX_TOKENS=1024
GROQ_MODEL=llama-3.3-70b-versatile
```

### Optional — Services

```env
SERPAPI_KEY=               # Web search (optional — enables web search skill)
NEWS_API_KEY=              # News headlines (optional — enables news in briefing + web browse)
OPENWEATHER_API_KEY=       # Weather data (optional — enables weather in briefing + web browse)
```

### Optional — Voice

```env
TTS_VOICE=en-US-AriaNeural
VOICE_REPLIES_ENABLED=false
```

### Optional — Briefing

```env
DEFAULT_LOCATION=Manila, Philippines
BRIEFING_TIME=07:00
BRIEFING_ENABLED=true
```

### Optional — Behaviour

```env
ALLOWED_TELEGRAM_IDS=      # Comma-separated, empty = allow all
DEFAULT_TIMEZONE=Asia/Manila
DEFAULT_CURRENCY=PHP
INTENT_CONFIDENCE_THRESHOLD=0.6
MAX_CONVERSATION_HISTORY=20
LOG_LEVEL=INFO
```

---

## Database Setup

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Open the SQL Editor in the dashboard
3. Paste contents of `database/migrations/001_initial.sql`
4. Click Run
5. Copy the project URL and service-role key to your `.env`

---

## Local Development

```bash
cd kaia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python -m bot.telegram_bot
```

---

## Production Deployment

### AWS EC2 (current production — recommended)

**Target:** t4g.small (ARM, 2 vCPU, 2GB RAM, Ubuntu 24.04)
**Host:** `3.106.134.24`
**User:** `ubuntu`
**Key:** `keys/kaia-key.pem` (local, never commit)

Files in `deploy/`:
- `setup-server.sh` — one-time bootstrap (apt update, installs python3/ffmpeg/git, creates `/opt/kaia/` and venv).
- `kaia.service` — systemd unit (auto-restart, MemoryMax=1G, CPUQuota=80%, journal logs).
- `update.sh` — manual pull/install/restart on the server.

**One-time server setup:**

```bash
# From local machine
scp -i keys/kaia-key.pem deploy/setup-server.sh ubuntu@3.106.134.24:~/
ssh -i keys/kaia-key.pem ubuntu@3.106.134.24

# On server
bash ~/setup-server.sh
cd /opt/kaia
git clone https://github.com/YOUR_USERNAME/kaia.git app
cd app
source /opt/kaia/venv/bin/activate
pip install -r kaia/requirements.txt
cp kaia/.env.example kaia/.env
nano kaia/.env                              # fill in API keys

sudo cp deploy/kaia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kaia
sudo systemctl status kaia
journalctl -u kaia -f                       # tail logs
```

**Updates:**

```bash
# Manual
ssh -i keys/kaia-key.pem ubuntu@3.106.134.24 'cd /opt/kaia/app && bash deploy/update.sh'

# Automatic via GitHub Actions
# .github/workflows/deploy.yml runs on every push to main.
# Required repo secrets:
#   SERVER_HOST      = 3.106.134.24
#   SSH_PRIVATE_KEY  = full contents of kaia-key.pem
```

**Service management:**

```bash
sudo systemctl restart kaia
sudo systemctl stop kaia
sudo systemctl status kaia
journalctl -u kaia -f                       # live logs
journalctl -u kaia --since "1 hour ago"
```

---

### Railway

Config files included:
- `Procfile` — `worker: python -m bot.telegram_bot`
- `railway.json` — Nixpacks builder, restart on failure

**Steps:**
1. Push repo to GitHub
2. Create a Railway project and connect the repo
3. Set the root directory to `kaia/` if the repo root isn't `kaia/`
4. Add all required environment variables in the Railway dashboard
5. Railway detects the Procfile and deploys as a worker process

### Render

1. Create a Background Worker service
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `python -m bot.telegram_bot`
4. Add environment variables

### Fly.io

```toml
# fly.toml
[build]
  builder = "paketobuildpacks/builder:base"

[processes]
  worker = "python -m bot.telegram_bot"
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "bot.telegram_bot"]
```

### VPS (systemd)

```ini
# /etc/systemd/system/kaia.service
[Unit]
Description=KAIA Telegram Bot
After=network.target

[Service]
User=kaia
WorkingDirectory=/home/kaia/kaia
ExecStart=/home/kaia/kaia/.venv/bin/python -m bot.telegram_bot
Restart=always
EnvironmentFile=/home/kaia/kaia/.env

[Install]
WantedBy=multi-user.target
```

---

## Health Check

Send `/status` to the bot on Telegram. It returns:
- AI provider and model
- Fallback availability
- External service status (SerpAPI, News, Weather)
- User stats: profile facts, active reminders, transactions, conversations
- Session AI calls and estimated cost

Monitor logs for token usage and errors:
```
2026-04-08 10:00:00 | INFO | bot.telegram_bot:handle_message:123 — msg handled | user=12345 skill=chat provider=claude tokens=500+150
```

## Notes

- **Voice requires Groq API key** — Without `GROQ_API_KEY`, voice messages get a "not available" response. Groq Whisper is free (30 req/min).
- **TTS is free** — edge-tts uses Microsoft Edge voices. No API key needed.
- **Rate limiting** — 20 messages per 60 seconds per user, enforced in-memory. Resets on restart.
- **Data export** — `/export` sends all user data as a JSON Telegram document. No server-side retention.
- **Data reset** — `/reset` requires exact `CONFIRM DELETE` text within 2 minutes. Deletes profile, reminders, transactions, conversations, memory, and budget limits.
