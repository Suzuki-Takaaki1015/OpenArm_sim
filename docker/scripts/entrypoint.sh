#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
case "${1:-web}" in
  web) exec /opt/openarm/scripts/web.sh ;;
  native) exec ros2 launch /opt/openarm/app/simulation.launch.py gui:=true ;;
  headless) exec ros2 launch /opt/openarm/app/simulation.launch.py gui:=false ;;
  *) exec "$@" ;;
esac
