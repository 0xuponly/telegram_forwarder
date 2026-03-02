#!/bin/bash
# Wrapper script for launchd: loads .env and runs the forwarder.

set -e
cd "$(dirname "$0")"
mkdir -p logs

# .env is loaded by Python's load_dotenv() - don't source here (breaks values with spaces)

# Prefer venv Python if available
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python forward_channel_messages.py "$@"
else
    exec python3 forward_channel_messages.py "$@"
fi
