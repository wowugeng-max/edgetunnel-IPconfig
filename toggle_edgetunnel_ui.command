#!/bin/zsh

set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${EDGETUNNEL_UI_HOST:-127.0.0.1}"
PORT="${EDGETUNNEL_UI_PORT:-8765}"
OPEN_BROWSER="${EDGETUNNEL_UI_OPEN:-1}"
PID_FILE="${DIR}/.edgetunnel-ui.pid"
LOG_FILE="${DIR}/.edgetunnel-ui.log"
APP="${DIR}/edgetunnel_region_ui.py"
URL="http://${HOST}:${PORT}/"

pause() {
  echo
  echo "Press Enter to close this window."
  read -r _
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

stop_pid() {
  local pid="$1"
  echo "Stopping edgetunnel IP Config UI on ${HOST}:${PORT} (PID ${pid})..."
  kill "$pid" 2>/dev/null || true
  for _i in {1..20}; do
    if ! is_running "$pid"; then
      rm -f "$PID_FILE"
      echo "Stopped."
      return 0
    fi
    sleep 0.2
  done
  echo "Process did not stop cleanly. Trying SIGKILL..."
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Stopped."
}

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if is_running "$pid"; then
    stop_pid "$pid"
    pause
    exit 0
  fi
  rm -f "$PID_FILE"
fi

existing_pid="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)"
if [[ -n "$existing_pid" ]]; then
  command_line="$(ps -p "$existing_pid" -o command= 2>/dev/null || true)"
  if [[ "$command_line" == *"edgetunnel_region_ui.py"* ]]; then
    stop_pid "$existing_pid"
    pause
    exit 0
  fi
  echo "Port ${PORT} is already in use by PID ${existing_pid}:"
  echo "$command_line"
  echo
  echo "Set EDGETUNNEL_UI_PORT to another port or stop that process first."
  pause
  exit 1
fi

if [[ ! -f "$APP" ]]; then
  echo "Cannot find ${APP}"
  pause
  exit 1
fi

echo "Starting edgetunnel IP Config UI on ${URL}"
echo "Log: ${LOG_FILE}"
nohup python3 "$APP" --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" > "$PID_FILE"

started=0
for _i in {1..20}; do
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -q "$pid"; then
    started=1
    break
  fi
  if ! is_running "$pid"; then
    break
  fi
  sleep 0.25
done

if [[ "$started" == "1" ]]; then
  echo "Started. PID: ${pid}"
  if [[ "$OPEN_BROWSER" != "0" ]]; then
    open "http://${HOST}:${PORT}/"
  fi
  pause
  exit 0
fi

echo "Failed to start. Recent log:"
tail -n 40 "$LOG_FILE" 2>/dev/null || true
rm -f "$PID_FILE"
pause
exit 1
