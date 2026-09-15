#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v docker >/dev/null 2>&1 || { echo 'Docker is missing. Run bash start.sh first.' >&2; exit 1; }
owner="$(docker inspect --format '{{index .Config.Labels "org.openarm.launcher"}}' openarm-auto 2>/dev/null)" || { echo 'Start the simulation with bash start.sh first.' >&2; exit 1; }
[[ "$owner" == "$repo" ]] || { echo 'openarm-auto belongs to another checkout. Run this script from its source checkout.' >&2; exit 1; }
[[ "$(docker inspect --format '{{.State.Running}}' openarm-auto)" == true ]] || { echo 'Simulation is stopped. Run bash start.sh first.' >&2; exit 1; }
exec docker exec -i openarm-auto /opt/openarm/scripts/entrypoint.sh ros2 run openarm_demos bimanual_demo "$@"
