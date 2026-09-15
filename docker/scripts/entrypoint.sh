#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
if [[ -f /opt/openarm/demo_ws/install/setup.bash ]]; then source /opt/openarm/demo_ws/install/setup.bash; fi
case "${1:-web}" in
  native|web|headless)
    if [[ -d /workspaces/OpenArm_sim/docker/demos/openarm_demos ]]; then
      python /opt/openarm/scripts/prepare_dev.py
      (cd /workspaces/OpenArm_dev && colcon build --symlink-install --packages-select openarm_demos)
    fi ;;
esac
if [[ -f /workspaces/OpenArm_dev/install/setup.bash ]]; then source /workspaces/OpenArm_dev/install/setup.bash; fi
case "${1:-web}" in
  web) exec /opt/openarm/scripts/web.sh ;;
  native) exec python /opt/openarm/app/supervisor.py --gui ;;
  headless) exec python /opt/openarm/app/supervisor.py ;;
  *) exec "$@" ;;
esac
