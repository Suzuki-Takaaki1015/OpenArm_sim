#!/usr/bin/env bash
# Ubuntu bootstrap. Run as your desktop/login user: bash start.sh
set -Eeuo pipefail
trap 'printf "[FAIL ] Bootstrap failed at line %s. Fix the error above and rerun bash start.sh.\n" "$LINENO" >&2' ERR
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
say() { printf '[%-5s] %s\n' "$1" "$2"; }
fail() { say FAIL "$*" >&2; exit 1; }
if [[ ${1:-} == --help ]]; then
    printf 'Usage: bash start.sh [--offline | --setup-only | launcher options]\nInstalls missing Ubuntu 24.04 dependencies, then launches OpenArm.\nLauncher options: --cpu --gpu --headless --display auto|native|browser --check --rebuild --stop --logs --robot-version 1|2\n'
    exit 0
fi
[[ $(uname -s) == Linux ]] || fail 'Automatic installation supports Ubuntu 24.04 only.'
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || fail 'Automatic installation supports Ubuntu 24.04 only.'
[[ $(dpkg --print-architecture) == amd64 ]] || fail 'This simulation release supports amd64 only.'
[[ $EUID != 0 ]] || fail 'Run bash start.sh as your normal user, without sudo. The script requests sudo when needed.'
say OK 'Ubuntu 24.04 / amd64'

# Probe HTTPS without requiring Python, pip or extra host packages.
# --offline is useful when network access is intentionally disabled.
forward=()
for arg in "$@"; do
    if [[ $arg == --offline ]]; then export OPENARM_OFFLINE=1
    else forward+=("$arg"); fi
 done
set -- "${forward[@]}"
if [[ ${OPENARM_OFFLINE:-0} != 1 ]]; then
    say CHECK 'Checking internet connectivity (up to 8 seconds)'
    online=0
    for endpoint in https://archive.ubuntu.com/ubuntu/ https://registry-1.docker.io/v2/; do
        if command -v curl >/dev/null; then
            # HTTP 401 at the registry still proves DNS/TLS connectivity.
            if curl --silent --output /dev/null --connect-timeout 2 --max-time 4 "$endpoint"; then online=1; break; fi
        else
            host=${endpoint#https://}; host=${host%%/*}
            if timeout 4 /usr/bin/bash -c 'exec 3<>/dev/tcp/"$1"/443' _ "$host" 2>/dev/null; then online=1; break; fi
        fi
    done
    [[ $online == 1 ]] || export OPENARM_OFFLINE=1
fi
if [[ ${OPENARM_OFFLINE:-0} == 1 ]]; then
    say WARN 'Offline: skipping package updates, installations and Docker image builds'
else
    say OK 'Internet connectivity detected'
fi

installed() { [[ $(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true) == 'install ok installed' ]]; }
packages=()
for pkg in python3 python3-venv git ca-certificates; do
    installed "$pkg" || packages+=("$pkg")
done
if ! command -v docker >/dev/null; then
    packages+=(docker.io docker-compose-v2)
elif ! docker compose version >/dev/null 2>&1; then
    if installed docker-ce-cli; then packages+=(docker-compose-plugin)
    elif installed docker.io; then packages+=(docker-compose-v2)
    else fail 'Existing Docker has no Compose v2. Install its matching Compose plugin; this script will not replace a custom Docker installation.'
    fi
fi
if ((${#packages[@]})); then
    [[ ${OPENARM_OFFLINE:-0} != 1 ]] || fail "Offline and required host packages are missing: ${packages[*]}. Connect to the internet and rerun. Simulation was not started."
    say CHECK "Installing missing host packages: ${packages[*]}"
    say INFO 'sudo is needed for package installation and Docker setup.'
    sudo -v
    sudo apt-get -o DPkg::Lock::Timeout=120 update
    # Ubuntu minimal installations may not enable Universe.
    if ! apt-cache show python3-venv >/dev/null 2>&1 || ! apt-cache show docker.io >/dev/null 2>&1; then
        sudo apt-get -o DPkg::Lock::Timeout=120 install -y software-properties-common
        sudo add-apt-repository -y universe
        sudo apt-get -o DPkg::Lock::Timeout=120 update
    fi
    sudo apt-get -o DPkg::Lock::Timeout=120 install -y "${packages[@]}"
fi
python3 -c 'import venv' >/dev/null 2>&1 || fail 'Python venv is unavailable.'
say OK 'Python, venv, Git and Docker Compose installed'
# Stop/log operations must remain usable without installing a desktop editor.
case "${1:-}" in
    --stop|--logs) ;;
    *) python3 "$ROOT/scripts/setup_vscode.py" ;;
esac
if ! docker info >/dev/null 2>&1; then
    endpoint=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}
    [[ $endpoint == unix:///var/run/docker.sock || $endpoint == unix:///run/docker.sock ]] || fail "Docker endpoint is unavailable: $endpoint. Start that Docker daemon first."
    say CHECK 'Starting local Docker service'
    sudo systemctl enable --now docker
    if ! docker info >/dev/null 2>&1; then
        sudo docker info >/dev/null || fail 'Docker daemon failed to start.'
        user=$(id -un)
        if ! id -nG "$user" | tr ' ' '\n' | grep -qx docker; then
            say INFO 'Adding your user to docker group (administrator-equivalent Docker access).'
            sudo usermod -aG docker "$user"
        fi
        [[ ${OPENARM_GROUP_REFRESH:-0} != 1 ]] || fail 'Docker access failed after group refresh.'
        say CHECK 'Refreshing Docker group for this launch; no logout needed'
        export OPENARM_GROUP_REFRESH=1
        printf -v command '%q ' bash "$ROOT/start.sh" "$@"
        exec sg docker -c "$command"
    fi
fi
say OK 'Docker daemon accessible'
python3 "$ROOT/install_shell.py"
if [[ ${1:-} == --setup-only ]]; then
    say OK 'Host setup complete. Start with: bash start.sh'
    exit 0
fi
exec python3 "$ROOT/start.py" "$@"
