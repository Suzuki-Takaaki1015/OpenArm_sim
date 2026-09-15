#!/usr/bin/env python3
"""Open VS Code attached to the running OpenArm container."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

NAME = 'openarm-auto'
WORKSPACE = '/workspaces/OpenArm_dev'
EXTENSION = 'ms-vscode-remote.remote-containers'

def run(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout.strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true', help='check prerequisites without opening a window')
    args = p.parse_args()
    code = shutil.which('code')
    if not code:
        raise RuntimeError('VS Code is not installed on the Ubuntu host. Install it from https://code.visualstudio.com/download and rerun oa-code.')
    if not shutil.which('docker'):
        raise RuntimeError('Docker command not found on the host.')
    info = json.loads(run(['docker', 'inspect', NAME]))[0]
    if not info['State']['Running']:
        raise RuntimeError('OpenArm is stopped. Run bash start.sh from your checkout first.')
    owner = (info['Config'].get('Labels') or {}).get('org.openarm.launcher')
    if not owner:
        raise RuntimeError('This container was not created by the OpenArm launcher.')
    if not any(m['Destination'] == WORKSPACE and m.get('RW') and m['Source'] == str(Path(owner)/'.openarm/dev_ws') for m in info['Mounts']):
        raise RuntimeError('The development folder is not mounted. Restart once with bash start.sh in ' + owner)
    extensions = run([code, '--list-extensions']).lower().splitlines()
    if EXTENSION not in extensions:
        print('[CHECK] Installing the Microsoft Dev Containers extension...', flush=True)
        run([code, '--install-extension', EXTENSION])
    # Use the host uid when it has a matching container account; this keeps bind-mounted files writable.
    uid = str(os.getuid())
    entry = run(['docker', 'exec', NAME, 'getent', 'passwd', uid]).split(':')
    user, home = entry[0], entry[5]
    env = json.loads(run(['docker', 'exec', NAME, '/opt/openarm/scripts/entrypoint.sh', 'python', '-c', 'import os,json;print(json.dumps(dict(os.environ)))']))
    keys = ['PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'AMENT_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'ROS_DISTRO', 'ROS_VERSION', 'ROS_PYTHON_VERSION', 'ROS_DOMAIN_ID', 'ROS_AUTOMATIC_DISCOVERY_RANGE']
    remote_env = {k: env[k] for k in keys if k in env}
    remote_env['HOME'] = WORKSPACE + '/.home'
    directory = Path.home() / '.config/Code/User/globalStorage/ms-vscode-remote.remote-containers/nameConfigs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (NAME + '.json')
    config = json.loads(path.read_text()) if path.exists() else {}
    config.update({'workspaceFolder': WORKSPACE, 'remoteUser': user, 'remoteEnv': {**config.get('remoteEnv', {}), **remote_env}})
    settings = config.setdefault('settings', {})
    settings['terminal.integrated.cwd'] = WORKSPACE
    settings['window.title'] = 'OpenArm Docker | ${rootName}${separator}${appName}'
    profiles = settings.setdefault('terminal.integrated.profiles.linux', {})
    profiles['OpenArm ROS 2'] = {'path': '/opt/openarm/scripts/entrypoint.sh', 'args': ['bash']}
    settings['terminal.integrated.defaultProfile.linux'] = 'OpenArm ROS 2'
    settings.setdefault('python.defaultInterpreterPath', '/opt/venv/bin/python')
    path.write_text(json.dumps(config, indent=2) + '\n')
    authority = json.dumps({'containerName': info['Id']}, separators=(',', ':')).encode().hex()
    uri = 'vscode-remote://attached-container+' + authority + WORKSPACE
    print('[OK] Execution: Docker ' + NAME + '; workspace: ' + WORKSPACE, flush=True)
    print('[OK] Persistent storage: ' + owner + '/.openarm/dev_ws', flush=True)
    if args.check:
        print('[OK] VS Code, Dev Containers, shared workspace and ROS terminal configuration ready')
        return
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise RuntimeError('Run oa-code from an Ubuntu desktop terminal with a GUI session.')
    subprocess.Popen([code, '--new-window', '--folder-uri', uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print('[OK] Opening VS Code attached to OpenArm')

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print('[FAIL] ' + str(exc), file=sys.stderr)
        sys.exit(1)
