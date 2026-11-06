#!/usr/bin/env bash
# Runs as the container's ordinary developer account.
set -e
pc=/workspaces/OpenArm_dev
test -w "$pc" || { echo "Bind mount a writable robot PC workspace at $pc" >&2; exit 1; }
ext="$pc/external_ws"; team="$pc/happy_ws"
mkdir -p "$ext/src" "$team/src/main"
if [[ ! -e "$ext/src/urg_node" ]]; then cp -R /opt/happy/seed/urg_node "$ext/src/urg_node"; chmod -R u+w "$ext/src/urg_node"; fi
if [[ ! -e "$team/src/main/openarm_demos" ]]; then cp -R /opt/openarm/demo_ws/src/openarm_demos "$team/src/main/"; fi
if [[ ! -e "$team/src/main/happy_robot" ]]; then cp -R /opt/happy/happy_robot "$team/src/main/"; fi
if [[ ! -e "$team/src/main/happy_posture" ]]; then
    cp -R /opt/openarm/demo_ws/src/happy_posture "$team/src/main/"
fi
source /opt/ros/jazzy/setup.bash
for ws in "$ext" "$team"; do
    cd "$ws"
    if [[ ! -f install/.happy_initialized ]]; then
        colcon build --symlink-install --cmake-args -DBUILD_TESTING=OFF
        touch install/.happy_initialized
    elif [[ $ws == "$team" && ! -e install/happy_posture/share/happy_posture/package.xml ]]; then
        colcon build --symlink-install --packages-select happy_posture
    fi
    source install/local_setup.bash
done
