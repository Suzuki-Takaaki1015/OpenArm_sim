#!/usr/bin/env bash
set -euo pipefail
sudo -v
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey -o "$work/key"
gpg --batch --dearmor -o "$work/key.gpg" "$work/key"
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list -o "$work/list"
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' "$work/list" > "$work/signed.list"
sudo install -m 644 "$work/key.gpg" /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
sudo install -m 644 "$work/signed.list" /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
printf '\nNVIDIA Container Toolkit setup complete\n'
