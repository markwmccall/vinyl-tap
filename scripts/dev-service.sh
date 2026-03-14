#!/bin/bash
# Mac-specific dev service manager for vinyl-emulator.
# Runs app.py on port 443 with HTTPS (requires sudo).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="$PROJECT_ROOT/certs"
CERT="$CERTS_DIR/vinyl-mac.local.crt"
KEY="$CERTS_DIR/vinyl-mac.local.key"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP="$PROJECT_ROOT/app.py"
LOG="$PROJECT_ROOT/dev-server.log"
PGREP_PATTERN="python.*app\.py"

_pid() {
  local pid
  pid=$(pgrep -f "$PGREP_PATTERN" 2>/dev/null | head -1)
  [ -n "$pid" ] && echo "$pid"
}

_check_prereqs() {
  if [ ! -f "$VENV_PYTHON" ]; then
    echo "[!] Virtual environment not found. Run ./scripts/dev-setup.sh first."
    exit 1
  fi
  if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "[!] SSL certs not found. Run ./scripts/dev-setup.sh first."
    exit 1
  fi
}

cmd_start() {
  _check_prereqs
  if PID=$(_pid); then
    echo "[OK] Already running (pid $PID)"
    return
  fi
  echo "[+] Starting vinyl-emulator on https://vinyl-mac.local ..."
  sudo -v
  sudo "$VENV_PYTHON" "$APP" \
    --host 0.0.0.0 --port 443 \
    --ssl-cert "$CERT" --ssl-key "$KEY" \
    >> "$LOG" 2>&1 &
  sleep 1
  if PID=$(_pid); then
    echo "[OK] Running (pid $PID) — logs: $LOG"
  else
    echo "[!] Failed to start. Check $LOG"
    exit 1
  fi
}

cmd_stop() {
  PID=$(_pid) || true
  if [ -z "$PID" ]; then
    echo "[OK] Not running"
    return
  fi
  echo "[+] Stopping (pid $PID)..."
  sudo kill -TERM "$PID" 2>/dev/null || true
  for i in $(seq 1 10); do
    sleep 0.5
    if ! _pid > /dev/null 2>&1; then
      echo "[OK] Stopped"
      return
    fi
  done
  echo "[!] Still running — sending KILL..."
  sudo kill -KILL "$PID" 2>/dev/null || true
  echo "[OK] Killed"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_status() {
  if PID=$(_pid); then
    echo "[OK] Running (pid $PID) — https://vinyl-mac.local"
  else
    echo "[ ] Not running"
  fi
}

cmd_logs() {
  if [ ! -f "$LOG" ]; then
    echo "[!] No log file yet: $LOG"
    exit 1
  fi
  tail -f "$LOG"
}

case "${1:-}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
