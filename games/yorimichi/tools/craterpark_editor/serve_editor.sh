#!/bin/zsh
# Crater Park editor on the tailnet, at <this Mac's tailnet name>/parkeditor/
# python server on 127.0.0.1:$PORT (editor files + save API), published with tailscale serve (tailnet only).
set -e
PORT=8914   # was 8904: that port's loopback tuples got wedged (thousands of stuck TIME_WAIT), stalling new connections
H=${0:A:h}; TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
if ! lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  # launchd runs it at normal priority (a server started from a niced shell stalls when the Mac is busy)
  launchctl remove com.atelier.parkeditor 2>/dev/null || true
  launchctl submit -l com.atelier.parkeditor -o $H/server.log -e $H/server.log -- $(command -v python3) $H/server.py $PORT
  sleep 1
fi
$TS serve status 2>/dev/null | grep -q "/parkeditor *proxy http://127.0.0.1:$PORT" || $TS serve --bg --set-path /parkeditor http://127.0.0.1:$PORT
echo "editor: http://127.0.0.1:$PORT/ and, on the tailnet, /parkeditor/ (see tailscale serve status)"
