#!/usr/bin/env bash
set -e
export OPENARM_VERSION="${OPENARM_VERSION:-1}"
case "$OPENARM_VERSION" in
  1) export OPENARM_MODEL=/opt/openarm/models/v1/openarm_bimanual.xml ;;
  2) export OPENARM_MODEL=/opt/openarm/models/v2/simulation_robot.xml ;;
  *) echo "Unsupported OpenArm version: $OPENARM_VERSION" >&2; exit 1 ;;
esac
export OPENARM_CONFIG=/opt/openarm/config/v$OPENARM_VERSION
export OPENARM_SCENE=/opt/openarm/models/v$OPENARM_VERSION/simulation_scene.xml
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
