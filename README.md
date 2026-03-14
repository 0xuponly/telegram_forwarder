# Third Gulf War Alerts – Telegram channel forwarder

Forwards messages from **broadcast Telegram channels only** (groups and private chats are ignored) when the text matches keyword lists. Each destination channel has its own keyword set; a message can be forwarded to more than one destination if it matches multiple sets.

Uses [Telethon](https://docs.telethon.dev/) (user session, not the Bot API).

---

## Prerequisites

- **Python 3.8+** (3.10+ recommended)
- A **Telegram user account**
- **API ID & API Hash** from [my.telegram.org](https://my.telegram.org) → API development tools

---

## Setup

1. Clone the repo and enter the project directory (paths below assume this folder).

2. **Dependencies** (virtualenv recommended):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Environment** – copy the example and edit **from the project directory**:

   ```bash
   cp .env.example .env
   ```

   Set at least **API ID/Hash** and **one** destination + keywords (`TELEGRAM_FORWARD_TO_1` + `TELEGRAM_KEYWORDS_1`).  
   Optional: up to **three** destinations (`_1`, `_2`, `_3`).

   **Important:** Do **not** `source .env` in the shell if keywords contain spaces (e.g. `abu dhabi`). The app loads `.env` via `python-dotenv` when you run `run.sh` or `forward_channel_messages.py`.

---

## Run

### Manual (terminal)

```bash
cd /path/to/epstein_coalition_tg_alerts_0.1
./run.sh
# or: python forward_channel_messages.py
```

First run: Telegram will ask for phone number and login code. Session is stored next to the script (see `TELEGRAM_SESSION`).

### Background on macOS (launchd)

1. **Edit the plist** `com.epstein.tg-alerts.plist`: every path must match **your** machine (project path, same as in the repo or your clone).

2. **Create logs directory** (launchd needs it before the job can attach stdout/stderr):

   ```bash
   cd /path/to/epstein_coalition_tg_alerts_0.1
   mkdir -p logs
   ```

3. **Install and start** (run from project dir so `cp` finds the plist):

   ```bash
   cp com.epstein.tg-alerts.plist ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.epstein.tg-alerts.plist
   ```

   Older macOS may still accept:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.epstein.tg-alerts.plist
   ```

4. **Check**

   ```bash
   launchctl list | grep epstein
   ```

   A **numeric PID** in the first column means the process is running. Status column can show a past non-zero exit until the next clean run.

5. **Stop**

   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.epstein.tg-alerts.plist
   ```

   After code or `.env` changes, **bootout then bootstrap again** (or unload/load).

`run.sh` uses `.venv/bin/python` if present; otherwise `python3`. It does **not** shell-`source` `.env` (avoids breaking comma/spaced keywords).

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_API_ID` | Yes | From my.telegram.org |
| `TELEGRAM_API_HASH` | Yes | From my.telegram.org |
| `TELEGRAM_FORWARD_TO_1` | Yes* | Destination 1 (`@channel`, id, or invite link) |
| `TELEGRAM_KEYWORDS_1` | Yes* | Comma-separated keywords; word-boundary match |
| `TELEGRAM_FORWARD_TO_2` | No | Destination 2 |
| `TELEGRAM_KEYWORDS_2` | No | Keywords for destination 2 |
| `TELEGRAM_FORWARD_TO_3` | No | Destination 3 |
| `TELEGRAM_KEYWORDS_3` | No | Keywords for destination 3 |
| `TELEGRAM_SESSION` | No | Session filename (default: `epstein_coalition_alerts_session`) |
| `TELEGRAM_CASE_INSENSITIVE` | No | `true` / `false` (default: `true`) |
| `TELEGRAM_NEAR_DUP_WINDOW` | No | Recent forwards per dest used for near-dup compare (default: `80`) |
| `TELEGRAM_NEAR_DUP_SEQ_RATIO` | No | Sequence similarity 0–1, higher = stricter (default: `0.82`) |
| `TELEGRAM_NEAR_DUP_JACCARD` | No | Word-overlap similarity 0–1 (default: `0.68`) |
| `TELEGRAM_NEAR_DUP_COMPARE_CHARS` | No | Max characters compared per message (default: `1200`) |
| `TELEGRAM_FILTERED_LOG_MAX_BYTES` | No | Max size of `filtered.log` before rotate (default: 10MB) |
| `TELEGRAM_PLAY_SOUND_1` | No | `true` / `on` → play sound when a message is forwarded to channel 1 (default: off) |
| `TELEGRAM_SOUND_NAME_1` | No | Sound for channel 1 (default: `Glass`) |
| `TELEGRAM_PLAY_SOUND_2` | No | Same for destination 2 |
| `TELEGRAM_SOUND_NAME_2` | No | (default: `Glass`) |
| `TELEGRAM_PLAY_SOUND_3` | No | Same for destination 3 |
| `TELEGRAM_SOUND_NAME_3` | No | (default: `Glass`) |

\*At least one full pair `_FORWARD_TO_1` + `_KEYWORDS_1` must be set.

### Sounds (macOS only)

When a forward **succeeds**, the script runs **`afplay`** on the machine running the process (your Mac). Set `TELEGRAM_PLAY_SOUND_N=true` for that destination row, and pick a sound with `TELEGRAM_SOUND_NAME_N`.

**Built-in names** (no path, no `.aiff`):  
`Basso`, `Blow`, `Bottle`, `Frog`, `Funk`, `Glass`, `Hero`, `Morse`, `Ping`, `Pop`, `Purr`, `Sosumi`, `Submarine`, `Tink`  
(files live under `/System/Library/Sounds/`).

**Custom file:** set `TELEGRAM_SOUND_NAME_N` to a full path, e.g. `/Users/you/Music/alert.aiff` (or other formats `afplay` supports).

Linux/Windows: play sound is skipped (log warns if you enabled it).

---

## Local UI (forward list + sound mute)

A small browser UI lists **every successful forward** (UTC timestamp, destination, source channel, full text sample) from `logs/forwards.jsonl`. It also:

- **Per destination** – checkboxes to show/hide rows for each configured `TELEGRAM_FORWARD_TO_N` (display only).
- **Sounds on (forwarder)** – one master switch. When off, the forwarder **does not** call `afplay` (writes `logs/ui_state.json`). Per-channel `TELEGRAM_PLAY_SOUND_N` must still be on for sound when master is on.

**Homebrew Python** blocks `pip install --user` (PEP 668). Use the project venv:

```bash
cd /path/to/project
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python ui_app.py
```

Or one step:

```bash
./run_ui.sh
```

Open **http://127.0.0.1:8765** (set `TELEGRAM_UI_PORT` to change port).

Run the UI on the **same machine** as the forwarder so mute applies to that process. Refresh runs every 8s automatically.

### Keep UI running after closing Terminal

Background jobs die when the terminal closes (SIGHUP). Use either:

**A. `nohup` (quick)** — survives tab/window close; survives logout only if you stay logged in… actually nohup survives terminal close while session lasts:

```bash
cd /path/to/project
mkdir -p logs
nohup env TELEGRAM_UI_QUIET=1 ./run_ui.sh >>logs/ui.out 2>>logs/ui.err &
```

**B. LaunchAgent (best on macOS)** — survives closing Terminal, logout/login, reboot (after login). Edit paths in `com.epstein.tg-alerts-ui.plist` to match your project, then:

```bash
mkdir -p logs
cp com.epstein.tg-alerts-ui.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.epstein.tg-alerts-ui.plist
```

Stop UI service:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.epstein.tg-alerts-ui.plist
```

Logs: `logs/ui_launchd.out.log`, `logs/ui_launchd.err.log`. Open **http://127.0.0.1:8765** as usual.

---

## Dedupe behaviour

1. **Same Telegram event** – Same `(chat_id, message_id)` is only handled once (stops duplicate client updates).
2. **Exact same text → same destination** – Already forwarded that normalized text to that channel → skip.
3. **Near duplicate → same destination** – New message is very similar (sequence + word overlap) to a recent forward to that channel → skip (reposts / paraphrases from other sources).

Tune near-dup env vars if you see false positives or misses.

---

## Logs

| File | Purpose |
|------|--------|
| `logs/forwarder.log` | Connects, config summary, successful forwards, errors (rotating) |
| `logs/filtered.log` | Messages **not** forwarded + reason + text of the **prior forward** (or note) that caused the skip |
| `logs/out.log` | launchd stdout (if plist points here) |
| `logs/err.log` | launchd stderr |
| `logs/forwards.jsonl` | One JSON object per forward (UI + audit); trimmed after ~12k lines |
| `logs/ui_state.json` | UI master sound on/off (`sounds_enabled`) |

```bash
tail -n 100 logs/forwarder.log
tail -n 100 logs/filtered.log
```

---

## Troubleshooting

- **`launchctl list` shows `-` and exit `1`** – process died; run `./run.sh` in the project dir to see the error; fix `.env` or Python deps.
- **Exit `127`** – program path in plist wrong or missing venv/script.
- **Only one Telethon session** – Don’t run two copies with the same session file at once.
- **plist paths** – Must match the real project path on disk after clone/move.

---

## Notes

- Only **broadcast channels** are considered; you must be joined to sources you care about.
- Keywords use **word boundaries** (e.g. `dubai` does not match `dubaiairport`).
- One message matching several keyword sets is forwarded **once per matching destination**; dedupe is **per destination**.
