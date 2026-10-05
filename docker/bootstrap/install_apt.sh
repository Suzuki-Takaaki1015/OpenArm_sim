#!/bin/sh
# Download with bounded retries before starting dpkg; keep APT signature checks.
set -eu
primary=${ROS_APT_MIRROR:-http://packages.ros.org/ros2/ubuntu}
previous=$primary
for source in "$primary" https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu; do
    printf '[CHECK] ROS package source: %s\n' "$source"
    if [ "$source" != "$previous" ]; then
        find -L /etc/apt/sources.list.d -type f -exec sed -i "s|$previous|$source|g" {} +
    fi
    previous=$source
    if timeout 180 apt-get -o APT::Update::Error-Mode=any update && timeout 360 apt-get install -y --download-only --no-install-recommends "$@"; then
        # No timeout during unpack/configuration: do not interrupt dpkg transactions.
        exec apt-get install -y --no-download --no-install-recommends "$@"
    fi
    printf '[WARN] Package download failed or timed out; retaining cache and trying fallback.\n' >&2
done
printf '[FAIL] Could not download dependencies from the configured ROS sources. Check VM networking and rerun.\n' >&2
exit 1
