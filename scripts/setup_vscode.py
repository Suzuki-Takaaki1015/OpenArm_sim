#!/usr/bin/env python3
"""Install missing host VS Code and Dev Containers; never upgrade existing Code."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

EXTENSION = 'ms-vscode-remote.remote-containers'
DOWNLOAD = 'https://update.code.visualstudio.com/latest/linux-deb-x64/stable'


def run(args, timeout=600):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout).stdout.strip()


def setup():
    offline = os.environ.get('OPENARM_OFFLINE') == '1'
    code = shutil.which('code')
    if not code:
        if offline:
            raise RuntimeError('Offline: host VS Code is missing. Connect to the internet and rerun bash start.sh. Simulation was not started.')
        print('[CHECK] Installing host VS Code from the official Microsoft download (sudo required)', flush=True)
        # TemporaryDirectory also removes partial downloads on failure.
        with tempfile.TemporaryDirectory(prefix='openarm-vscode-') as directory:
            package = Path(directory) / 'code.deb'
            with urllib.request.urlopen(DOWNLOAD, timeout=30) as response, package.open('wb') as target:
                shutil.copyfileobj(response, target)
            if run(['dpkg-deb', '-f', str(package), 'Package']) != 'code':
                raise RuntimeError('Downloaded package is not VS Code; installation cancelled.')
            if run(['dpkg-deb', '-f', str(package), 'Architecture']) != 'amd64':
                raise RuntimeError('Downloaded VS Code architecture is not amd64.')
            # apt's sandbox user must be able to read the local package.
            Path(directory).chmod(0o755)
            package.chmod(0o644)
            subprocess.run(['sudo', 'apt-get', '-o', 'DPkg::Lock::Timeout=120', 'update'], check=True)
            subprocess.run(['sudo', 'env', 'DEBIAN_FRONTEND=noninteractive', 'apt-get',
                            '-o', 'DPkg::Lock::Timeout=120', 'install', '-y', str(package)], check=True)
        code = shutil.which('code')
        if not code:
            raise RuntimeError('VS Code installation finished but code is not on PATH.')
    print('[OK   ] Host VS Code available', flush=True)
    extensions = run([code, '--list-extensions'], timeout=120).lower().splitlines()
    if EXTENSION not in extensions:
        if offline:
            raise RuntimeError('Offline: Dev Containers extension is missing. Connect to the internet and rerun bash start.sh. Simulation was not started.')
        print('[CHECK] Installing Dev Containers for the current user', flush=True)
        run([code, '--install-extension', EXTENSION], timeout=300)
        if EXTENSION not in run([code, '--list-extensions'], timeout=120).lower().splitlines():
            raise RuntimeError('Dev Containers installation could not be verified.')
    print('[OK   ] Host VS Code and Dev Containers ready for oa-code', flush=True)


if __name__ == '__main__':
    try:
        setup()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, 'stdout', None) or str(exc)
        print('[FAIL ] VS Code setup failed: ' + detail + '\nRerun bash start.sh after resolving the error. Simulation was not started.', file=sys.stderr)
        sys.exit(1)
