#!/usr/bin/env bash
# Source from ~/.bashrc. No privileged Docker options.
unalias oa 2>/dev/null || true
oa() { docker exec -it --user "$(id -u):$(id -g)" --workdir /workspaces/OpenArm_dev -e HOME=/workspaces/OpenArm_dev/.home openarm-auto /opt/openarm/scripts/entrypoint.sh bash; }
alias oa-logs='docker logs --tail 100 -f openarm-auto'
oa-ros() { docker exec -i openarm-auto /opt/openarm/scripts/entrypoint.sh ros2 "$@"; }
oa-scene() { if (( $# == 0 )); then set -- status; fi; docker exec -i openarm-auto /opt/openarm/scripts/entrypoint.sh python /opt/openarm/app/scene_cli.py "$@"; }

oa-code() { python3 "$HOME/.config/openarm/oa_code.py" "$@"; }

# Read-only diagnostics, also available while the container is stopped.
oa-doctor() { python3 "$HOME/.config/openarm/oa_doctor.py" "$@"; }
