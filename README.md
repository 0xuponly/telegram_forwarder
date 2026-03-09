War Alerts by slumcap – Telegram Channel Forwarder

Forwards Telegram messages from **channels only** (ignores chats and groups) when they contain certain keywords.

## Prerequisites

- Python 3.8+
- A Telegram account (user, not bot)
- API credentials from [my.telegram.org](https://my.telegram.org)

## Setup

1. **Create an app** at [my.telegram.org](https://my.telegram.org) → API development tools.
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment** – copy `.env.example` to `.env` and edit, or export:
   ```bash
   cp .env.example .env   # then edit .env
   # OR export directly:
   export TELEGRAM_API_ID=12345678
   export TELEGRAM_API_HASH=your_api_hash
   export TELEGRAM_FORWARD_TO_1=@channel1
   export TELEGRAM_KEYWORDS_1=dubai,uae,u.a.e.,abu dhabi,sharjah
   export TELEGRAM_FORWARD_TO_2=@channel2
   export TELEGRAM_KEYWORDS_2=alert,urgent
   # Optional channel 3
   export TELEGRAM_FORWARD_TO_3=@channel3
   export TELEGRAM_KEYWORDS_3=another,comma,separated,list
   ```

## Run

**One-off / manual:**
```bash
python forward_channel_messages.py
```

On first run you’ll be asked for your phone number and the login code sent to Telegram.

**Background (macOS, for 24/7 uptime):** Use launchd to auto-restart on crash and run at login:

```bash
# Install the plist
cp com.epstein.tg-alerts.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.epstein.tg-alerts.plist

# Check status
launchctl list | grep epstein

# View logs
tail -f logs/out.log
tail -f logs/err.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.epstein.tg-alerts.plist
```

The plist uses `run.sh` to load `.env` and run the script. Logs go to `logs/`.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_API_ID` | Yes | From my.telegram.org |
| `TELEGRAM_API_HASH` | Yes | From my.telegram.org |
| `TELEGRAM_FORWARD_TO_1` | Yes* | Channel 1 destination (username, chat ID, or invite link) |
| `TELEGRAM_KEYWORDS_1` | Yes* | Channel 1 keywords (comma-separated, word-boundary match) |
| `TELEGRAM_FORWARD_TO_2` | No | Channel 2 destination |
| `TELEGRAM_KEYWORDS_2` | No | Channel 2 keywords |
| `TELEGRAM_FORWARD_TO_3` | No | Channel 3 destination |
| `TELEGRAM_KEYWORDS_3` | No | Channel 3 keywords |
| `TELEGRAM_SESSION` | No | Session file name (default: `dubai_alerts_session`) |
| `TELEGRAM_CASE_INSENSITIVE` | No | `true` or `false` (default: `true`) |

*Channel 1 can also use legacy `TELEGRAM_FORWARD_TO` + `TELEGRAM_KEYWORDS`.

## Notes

- Only **broadcast channels** are processed; groups and private chats are ignored.
- You must be a member of the channels you want to monitor.
- Keywords use word boundaries (e.g. `dubai` does not match `dubaiairport`).
- A message matching multiple channel keyword sets is forwarded to each matching channel.
