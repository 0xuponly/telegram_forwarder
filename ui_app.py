#!/usr/bin/env python3
"""
Local web UI: forwarded messages + per-destination filters + master sound toggle.

Run from project directory (loads .env if present):
  python ui_app.py
  # or: .venv/bin/python ui_app.py

Open http://127.0.0.1:8765
Master sound toggle writes logs/ui_state.json; forwarder must be running to respect it.
"""

import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
UI_STATE_FILE = os.path.join(LOG_DIR, "ui_state.json")
FORWARDS_JSONL = os.path.join(LOG_DIR, "forwards.jsonl")

app = Flask(__name__)


def _default_state():
    return {"sounds_enabled": True}


def _read_state():
    try:
        with open(UI_STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("sounds_enabled", True)
            return d
    except (OSError, json.JSONDecodeError):
        pass
    return _default_state()


def _write_state(d):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(UI_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def _destinations():
    out = []
    for i in (1, 2, 3):
        d = os.environ.get(f"TELEGRAM_FORWARD_TO_{i}")
        k = os.environ.get(f"TELEGRAM_KEYWORDS_{i}", "").strip()
        if d and k:
            out.append({"id": d, "label": f"Channel {i}: {d}"})
    return out


def _load_forwards(limit=800):
    if not os.path.isfile(FORWARDS_JSONL):
        return []
    rows = []
    try:
        with open(FORWARDS_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


@app.route("/")
def index():
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Forwards</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9bb4; --accent:#3d8bfd; --border:#2a3544; }
    * { box-sizing: border-box; }
    body { font-family: ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 16px; line-height: 1.45; }
    h1 { font-size: 1.15rem; font-weight: 600; margin: 0 0 12px; }
    .bar { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; padding: 12px 14px; background: var(--card); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 14px; }
    .bar label { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; font-size: 0.9rem; }
    .bar input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent); }
    .sound-master { font-weight: 600; padding-left: 8px; border-left: 2px solid var(--border); margin-left: 4px; }
    #list { display: flex; flex-direction: column; gap: 10px; }
    .row { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; font-size: 0.88rem; }
    .meta { color: var(--muted); font-size: 0.8rem; margin-bottom: 6px; word-break: break-all; }
    .meta strong { color: #a8c4ff; }
    .text { white-space: pre-wrap; word-break: break-word; }
    .empty { color: var(--muted); padding: 24px; text-align: center; }
    .hint { font-size: 0.75rem; color: var(--muted); margin-top: 8px; }
  </style>
</head>
<body>
  <h1>Forwarded messages</h1>
  <div class="bar" id="bar">
    <span class="sound-master"><label><input type="checkbox" id="soundsOn"/> Sounds on (forwarder)</label></span>
    <span id="destToggles"></span>
    <button type="button" id="refresh" style="margin-left:auto;padding:6px 12px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);cursor:pointer;">Refresh</button>
  </div>
  <p class="hint">Sound toggle writes <code>logs/ui_state.json</code>. Run the forwarder on this Mac so it can play sounds and append <code>forwards.jsonl</code>.</p>
  <div id="list"></div>
<script>
const dests = """ + json.dumps(_destinations()) + """;
let visible = {};
dests.forEach(d => { visible[d.id] = true; });

async function loadState() {
  const r = await fetch('/api/state');
  const j = await r.json();
  document.getElementById('soundsOn').checked = !!j.sounds_enabled;
}

async function saveSounds(on) {
  await fetch('/api/state', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ sounds_enabled: on }) });
}

function buildDestToggles() {
  const el = document.getElementById('destToggles');
  dests.forEach(d => {
    const lab = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = true; cb.dataset.dest = d.id;
    cb.addEventListener('change', () => { visible[d.id] = cb.checked; render(); });
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(' ' + d.label));
    el.appendChild(lab);
  });
}

async function loadForwards() {
  const r = await fetch('/api/forwards');
  const rows = await r.json();
  const list = document.getElementById('list');
  const filtered = rows.filter(row => visible[row.dest] !== false);
  if (!filtered.length) {
    list.innerHTML = '<div class="empty">No messages yet (or all destinations hidden).</div>';
    return;
  }
  list.innerHTML = filtered.slice().reverse().map(row => {
    const ts = row.ts || '';
    const dest = escapeHtml(row.dest || '');
    const src = escapeHtml(row.source || '');
    const txt = escapeHtml(row.text || '');
    return '<div class="row"><div class="meta"><strong>' + escapeHtml(ts) + '</strong> → ' + dest + ' · from ' + src + '</div><div class="text">' + txt + '</div></div>';
  }).join('');
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

document.getElementById('soundsOn').addEventListener('change', e => saveSounds(e.target.checked));
document.getElementById('refresh').addEventListener('click', loadForwards);

buildDestToggles();
loadState();
loadForwards();
setInterval(loadForwards, 8000);
</script>
</body>
</html>"""
    )


@app.route("/api/state", methods=["GET", "POST"])
def api_state():
    if request.method == "POST":
        d = _read_state()
        body = request.get_json(silent=True) or {}
        if "sounds_enabled" in body:
            d["sounds_enabled"] = bool(body["sounds_enabled"])
        _write_state(d)
        return jsonify(d)
    return jsonify(_read_state())


@app.route("/api/forwards")
def api_forwards():
    return jsonify(_load_forwards())


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.isfile(UI_STATE_FILE):
        _write_state(_default_state())
    port = int(os.environ.get("TELEGRAM_UI_PORT", "8765"))
    print("Open http://127.0.0.1:" + str(port) + "  (master sound + forwards)", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
