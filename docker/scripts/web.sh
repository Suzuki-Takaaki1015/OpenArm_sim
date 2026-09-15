#!/usr/bin/env bash
set -euo pipefail
pids=()
cleanup() {
  trap - EXIT TERM INT
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
pids+=("$!")
ready=0
for attempt in {1..100}; do
  if xdpyinfo -display :99 >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.1
done
if [[ "$ready" != 1 ]]; then echo 'Xvfb startup failed' >&2; exit 1; fi
openbox --config-file "$OPENARM_CONFIG/openbox.xml" &
pids+=("$!")
x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw &
pids+=("$!")
websockify --web=/usr/share/novnc 6080 localhost:5900 &
pids+=("$!")
python /opt/openarm/app/supervisor.py --gui &
pids+=("$!")
echo 'Open http://localhost:6080/vnc.html?autoconnect=true&resize=scale'
# If any essential process exits, shut down the entire container.
set +e
wait -n "${pids[@]}"
status=$?
set -e
exit "$status"
