#!/bin/bash
# Remote Input launcher - supports both GUI terminal and headless (autostart) modes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load config from .env file (create from .env.example)
if [ -f .env ]; then
    source .env
else
    echo "Error: .env file not found. Copy .env.example to .env and set your token."
    exit 1
fi

TOKEN="${TOKEN:?Error: TOKEN not set in .env}"
PORT="${PORT:-8080}"
LOG_FILE="$SCRIPT_DIR/remote_input.log"

# If not headless and no terminal, open one
if [ -z "$REMOTE_INPUT_HEADLESS" ]; then
    if [ -z "$TERM" ] || [ "$TERM" = "dumb" ]; then
        gnome-terminal -- bash -c "cd '$SCRIPT_DIR' && python3 remote_input.py --auth --token '$TOKEN' --port $PORT; echo 'Service stopped. Press Enter to close.'; read" 2>/dev/null || \
        xterm -title "Remote Input" -e "cd '$SCRIPT_DIR' && python3 remote_input.py --auth --token '$TOKEN' --port $PORT; echo 'Press Enter to close.'; read" 2>/dev/null || \
        python3 remote_input.py --auth --token "$TOKEN" --port "$PORT"
        exit $?
    fi
fi

# Headless mode (autostart)
exec python3 remote_input.py --auth --token "$TOKEN" --port "$PORT" >> "$LOG_FILE" 2>&1
