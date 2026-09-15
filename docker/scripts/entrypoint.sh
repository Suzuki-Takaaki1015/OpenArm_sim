#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
case "${1:-web}" in
  web) exec /opt/openarm/scripts/web.sh ;;
  native) exec python /opt/openarm/app/supervisor.py --gui ;;
  headless) exec python /opt/openarm/app/supervisor.py ;;
  *) exec "$@" ;;
esac
