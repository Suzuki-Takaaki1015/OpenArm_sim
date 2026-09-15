#!/usr/bin/env bash
# Source from ~/.bashrc. No privileged Docker options.
alias oa='docker exec -it openarm-auto /opt/openarm/scripts/entrypoint.sh bash'
alias oa-logs='docker logs --tail 100 -f openarm-auto'
oa-ros() { docker exec -i openarm-auto /opt/openarm/scripts/entrypoint.sh ros2 "$@"; }
oa-scene() { docker exec -i openarm-auto /opt/openarm/scripts/entrypoint.sh python /opt/openarm/app/scene_cli.py "${1:-status}"; }

oa-code() { python3 "$HOME/.config/openarm/oa_code.py" "$@"; }
