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
if [[ ${HAPPY_MOBILE:-0} == 1 ]]; then
    export OPENARM_MODEL=/opt/openarm/models/mobile/simulation_robot.xml OPENARM_SCENE=/opt/openarm/models/mobile/simulation_scene.xml OPENARM_CONFIG=/opt/openarm/config/mobile
fi
source /opt/ros/jazzy/setup.bash
if [[ -f /opt/openarm/demo_ws/install/setup.bash ]]; then source /opt/openarm/demo_ws/install/setup.bash; fi
case "${1:-web}" in
  native|web|headless)
    if [[ ${HAPPY_MOBILE:-0} == 1 ]]; then
      bash /opt/happy/prepare_robot_pc.sh
    elif [[ -d /workspaces/OpenArm_sim/docker/demos/openarm_demos ]]; then
      python /opt/openarm/scripts/prepare_dev.py
      (cd /workspaces/OpenArm_dev && colcon build --symlink-install --packages-select openarm_demos)
    fi ;;
esac
if [[ -f /workspaces/OpenArm_dev/install/setup.bash ]]; then source /workspaces/OpenArm_dev/install/setup.bash; fi
if [[ ${HAPPY_MOBILE:-0} == 1 ]]; then
    for workspace in external_ws happy_ws; do
        setup=/workspaces/OpenArm_dev/$workspace/install/local_setup.bash
        if [[ -f $setup ]]; then source "$setup"; fi
    done
fi
case "${1:-web}" in
  web) exec /opt/openarm/scripts/web.sh ;;
  native) exec python /opt/openarm/app/supervisor.py --gui ;;
  headless) exec python /opt/openarm/app/supervisor.py ;;
  *) exec "$@" ;;
esac
