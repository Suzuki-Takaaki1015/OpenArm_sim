#!/usr/bin/env python3
"""OpenArm environment check and launcher. Python 3.10+; no pip dependency."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import venv

ROOT = Path(__file__).resolve().parent
STATE = ROOT / '.openarm'
IMAGE = 'openarm-sim:0.6.0'
NAME = 'openarm-auto'
LABEL = 'org.openarm.launcher'

def status(kind, message):
    colors = {'OK': '\033[32m', 'CHECK': '\033[36m', 'WARN': '\033[33m', 'FAIL': '\033[31m'}
    color = colors.get(kind, '') if sys.stdout.isatty() and not os.getenv('NO_COLOR') else ''
    end = '\033[0m' if color else ''
    print(f'{color}[{kind:5}]{end} {message}', flush=True)

def run(args, timeout=60, check=True):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed:\n{result.stdout[-5000:]}')
    return result

def docker(*args, **kwargs):
    return run(['docker', *args], **kwargs)

def bootstrap():
    env = ROOT / '.venv'
    executable = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if Path(sys.prefix).resolve() == env.resolve():
        return
    status('CHECK', 'Creating/checking launcher venv (.venv; standard library only)')
    if not executable.exists():
        try:
            venv.EnvBuilder(with_pip=False).create(env)
        except Exception as exc:
            raise RuntimeError(f'venv creation failed: {exc}. On Ubuntu install python3-venv.') from exc
    code = subprocess.call([str(executable), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(code)

def fingerprint():
    h = hashlib.sha256()
    for p in sorted((ROOT / 'docker').rglob('*')):
        if p.is_file() and not {'__pycache__', 'release'}.intersection(p.parts):
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()

def build_image(rebuild):
    digest = fingerprint()
    found = docker('image', 'inspect', IMAGE, check=False)
    label = None
    if found.returncode == 0:
        label = (json.loads(found.stdout)[0]['Config'].get('Labels') or {}).get('org.openarm.source')
    if os.environ.get('OPENARM_OFFLINE') == '1':
        if found.returncode:
            raise RuntimeError(f'Offline and required Docker image {IMAGE} is missing. Connect to the internet and run start.sh once. Simulation was not started.')
        if rebuild:
            raise RuntimeError('Cannot rebuild offline. Remove --rebuild to use the local image, or connect to the internet.')
        if label != digest:
            status('WARN', 'Offline: using the existing image; local source changes will be built when online')
        status('OK', f'Offline image ready: {IMAGE}; no build or download')
        return
    if rebuild or label != digest:
        status('CHECK', 'Building Ubuntu 24.04 / ROS 2 / container venv (first run downloads dependencies)')
        logfile = STATE / 'build.log'
        spec=STATE/'build.json'
        spec.write_text(json.dumps({'services':{'sim':{'image':IMAGE,'build':{'context':str(ROOT/'docker'),'labels':{'org.openarm.source':digest}}}}}),encoding='utf-8')
        with logfile.open('w', encoding='utf-8') as log:
            proc = subprocess.Popen(['docker', 'compose', '--progress', 'plain', '-f', str(spec), 'build'], stdout=log, stderr=subprocess.STDOUT)
            try:
                while proc.poll() is None:
                    with logfile.open('rb') as progress:
                        progress.seek(0, 2)
                        progress.seek(max(0, progress.tell() - 4096))
                        lines = progress.read().decode('utf-8', errors='replace').splitlines()
                    latest = next((line.strip() for line in reversed(lines) if line.strip()), '')
                    status('CHECK', f'Build running: {latest[-240:]}' if latest else f'Build running; log: {logfile}')
                    time.sleep(5)
            except KeyboardInterrupt:
                proc.terminate(); proc.wait(); raise
        if proc.returncode:
            raise RuntimeError(f'Build failed; see {logfile}\n{logfile.read_text(encoding="utf-8", errors="replace")[-3000:]}')
    status('OK', f'Image ready: {IMAGE} (MuJoCo venv: /opt/venv)')

def desktop_options(system, endpoint):
    # Native GPU rendering needs an accessible host X display. Xvfb is software-only.
    if system != 'Linux' or not endpoint.startswith('unix://'):
        return None, 'No supported local Linux desktop connection'
    display = os.environ.get('DISPLAY', '')
    if not display.startswith(':') or not Path('/tmp/.X11-unix').is_dir():
        return None, 'No active local X11/XWayland session (Server/headless or SSH)'
    auth = Path(os.environ.get('XAUTHORITY', str(Path.home()/'.Xauthority')))
    if not auth.is_file() or not os.access(auth, os.R_OK):
        return None, 'Desktop authentication unavailable; browser fallback'
    shared = ['--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp', '--workdir', '/tmp',
              '-e', f'DISPLAY={display}', '-e', 'XAUTHORITY=/tmp/openarm.xauth',
              '-e', 'LIBGL_ALWAYS_SOFTWARE=0', '-e', 'QT_X11_NO_MITSHM=1',
              '-v', '/tmp/.X11-unix:/tmp/.X11-unix:ro',
              '-v', f'{auth}:/tmp/openarm.xauth:ro']
    return shared, 'Local desktop session detected'

def gpu_candidates(system, endpoint):
    shared, reason = desktop_options(system, endpoint)
    if shared is None:
        return [], reason
    choices = []
    if shutil.which('nvidia-smi'):
        runtimes = json.loads(docker('info', '--format', '{{json .Runtimes}}').stdout)
        runtime = ['--runtime', 'nvidia'] if 'nvidia' in runtimes else []
        if not runtime:
            status('WARN', 'NVIDIA Container Toolkit/runtime is not configured on the host; see scripts/setup_nvidia.sh')
        # Apply offload to both the probe and the simulation container.
        # This selects the NVIDIA driver, not a particular RTX model.
        choices.append(('NVIDIA', [*runtime, '--gpus', 'all',
                                  '-e', 'NVIDIA_DRIVER_CAPABILITIES=graphics,display,utility',
                                  '-e', '__NV_PRIME_RENDER_OFFLOAD=1',
                                  '-e', '__GLX_VENDOR_LIBRARY_NAME=nvidia', *shared]))
    dri = Path('/dev/dri')
    if dri.is_dir():
        groups = sorted({p.stat().st_gid for p in dri.iterdir() if p.name.startswith(('renderD','card'))})
        opts = ['--device', '/dev/dri:/dev/dri', *shared]
        for group in groups:
            opts += ['--group-add', str(group)]
        choices.append(('Mesa/DRI', opts))
    return choices, 'No GPU device exposed to this Linux host' if not choices else ''

def hardware_renderer(text):
    lines = [s for s in text.splitlines() if 'OpenGL renderer string:' in s]
    return bool(lines) and not any(x in lines[0].lower() for x in ('llvmpipe','softpipe','swrast','software rasterizer'))

def select_backend(args, system, endpoint):
    if args.cpu:
        return 'cpu', [], 'CPU explicitly requested'
    candidates, reason = gpu_candidates(system, endpoint)
    for name, opts in candidates:
        status('CHECK', f'{name}: checking actual OpenGL renderer inside container')
        try:
            result = docker('run','--rm',*opts,IMAGE,'glxinfo','-B',timeout=30,check=False)
            (STATE/f'gpu-{name.split("/")[0]}.log').write_text(result.stdout,encoding='utf-8')
            renderer_lines = [line for line in result.stdout.splitlines() if 'OpenGL renderer string:' in line]
            matches_backend = name != 'NVIDIA' or any('nvidia' in line.lower() for line in renderer_lines)
            if result.returncode == 0 and hardware_renderer(result.stdout) and matches_backend:
                renderer = next(s.strip() for s in result.stdout.splitlines() if 'OpenGL renderer string:' in s)
                return 'gpu', opts, renderer
            reason = f'{name} OpenGL unavailable or software renderer; see .openarm/gpu-*.log'
        except subprocess.TimeoutExpired:
            reason = f'{name} OpenGL probe timed out'
        status('WARN', reason)
    if args.gpu:
        raise RuntimeError(f'GPU requested but not usable: {reason}')
    return 'cpu', [], reason

def select_presentation(args, system, endpoint):
    if getattr(args, 'headless', False):
        if args.gpu: raise RuntimeError('--headless has no GPU viewer; remove --gpu')
        return 'headless', [], 'No GUI; ROS actions and services remain available'
    if args.display == 'browser':
        if args.gpu:
            raise RuntimeError('--gpu requires native display; cannot combine with --display browser')
        return 'cpu', [], 'Browser display explicitly requested'
    mode, opts, reason = select_backend(args, system, endpoint)
    if mode == 'gpu':
        return mode, opts, reason
    shared, desktop_reason = desktop_options(system, endpoint)
    if shared is not None:
        shared = ['LIBGL_ALWAYS_SOFTWARE=1' if item == 'LIBGL_ALWAYS_SOFTWARE=0' else item for item in shared]
        status('CHECK', 'Desktop session: testing native CPU OpenGL display')
        try:
            probe = docker('run', '--rm', *shared, IMAGE, 'glxinfo', '-B', timeout=30, check=False)
            (STATE/'desktop-probe.log').write_text(probe.stdout, encoding='utf-8')
            if probe.returncode == 0 and 'OpenGL renderer string:' in probe.stdout:
                return 'native-cpu', shared, 'Desktop display available; CPU rendering'
            desktop_reason = 'Native desktop OpenGL test failed; see .openarm/desktop-probe.log'
        except subprocess.TimeoutExpired:
            desktop_reason = 'Native desktop OpenGL test timed out'
    if args.display == 'native':
        raise RuntimeError(desktop_reason)
    return 'cpu', [], desktop_reason


def existing():
    r=docker('inspect',NAME,check=False)
    if r.returncode:
        return None
    info=json.loads(r.stdout)[0]
    if (info['Config'].get('Labels') or {}).get(LABEL) != str(ROOT):
        raise RuntimeError(f'Container name {NAME} belongs to another checkout; it will not be changed')
    return info

def wait_ready(mode, port):
    status('CHECK', 'Waiting for ROS controllers and display (up to 180 seconds)')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        info=existing()
        if not info or not info['State']['Running']:
            raise RuntimeError('Container exited. Run: python3 start.py --logs')
        try:
            r=docker('exec', NAME, '/opt/openarm/scripts/entrypoint.sh', 'ros2', 'control', 'list_controllers',timeout=15,check=False)
        except subprocess.TimeoutExpired:
            status('CHECK', 'ROS discovery still initializing')
            continue
        required=['left_arm_controller','right_arm_controller','left_gripper_controller','right_gripper_controller','joint_state_broadcaster']
        if r.returncode==0 and all(any(name in line and 'active' in line and 'inactive' not in line for line in r.stdout.splitlines()) for name in required):
            if mode=='cpu':
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/vnc.html',timeout=3) as response:
                        if response.status!=200: continue
                except OSError:
                    time.sleep(3); continue
            status('OK','All 5 ROS controllers active; simulation ready')
            return
        time.sleep(3)
    raise RuntimeError('Startup timeout. Run: python3 start.py --logs')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--cpu',action='store_true');modes.add_argument('--gpu',action='store_true')
    p.add_argument('--rebuild',action='store_true');p.add_argument('--check',action='store_true',help='check/build/probe without starting')
    p.add_argument('--stop',action='store_true');p.add_argument('--logs',action='store_true')
    p.add_argument('--headless', action='store_true', help='ROS and MuJoCo physics without any GUI')
    p.add_argument('--display', choices=['auto','native','browser'], default='auto', help='auto: desktop windows when available; otherwise browser')
    p.add_argument('--robot-version',choices=['1','2'],help='OpenArm model; prompted on interactive startup')
    p.add_argument('--port',type=int,default=6080)
    args=p.parse_args()
    if not 1<=args.port<=65535: p.error('port must be 1..65535')
    bootstrap(); STATE.mkdir(exist_ok=True)
    system=platform.system()
    status('OK', f'Host: {system} {platform.release()} / {platform.machine()}')
    status('OK', f'Launcher venv: {sys.prefix}')
    if not shutil.which('docker'):
        raise RuntimeError('Docker not installed. Linux: https://docs.docker.com/engine/install/ ; Windows/macOS: https://docs.docker.com/desktop/ . Install/start Docker, then rerun this file.')
    docker('compose','version')
    info=json.loads(docker('info','--format','{{json .}}').stdout)
    if info.get('OSType')!='linux': raise RuntimeError('Switch Docker to Linux containers')
    if info.get('Architecture') not in ('x86_64','amd64'):
        raise RuntimeError('This release supports amd64 Docker hosts only. ARM64/Apple Silicon needs a separately validated image.')
    status('OK', f'Docker: {info.get("ServerVersion")} / {info.get("Architecture")} / {info.get("NCPU")} CPUs')
    gib=info.get('MemTotal',0)/(1024**3)
    status('OK' if gib>=7 else 'WARN',f'Docker memory: {gib:.1f} GiB; recommended 8 GiB')
    if args.stop:
        if existing(): docker('stop',NAME)
        status('OK','Stopped'); return
    if args.logs:
        if not existing(): raise RuntimeError('No launcher container exists')
        raise SystemExit(subprocess.call(['docker','logs','--tail','150','-f',NAME]))
    context=json.loads(docker('context','inspect').stdout)[0]
    endpoint=os.environ.get('DOCKER_HOST') or context['Endpoints']['docker']['Host']
    if not endpoint.startswith(('unix://','npipe://')):
        raise RuntimeError('Use a local Docker context. Remote Docker endpoints are not supported by this launcher.')
    if args.robot_version is None:
        if sys.stdin.isatty() and not args.check:
            while args.robot_version not in ('1','2'):
                args.robot_version=input('OpenArm model [1: OpenArm 1.0 / 2: OpenArm 2.0] (1): ').strip() or '1'
        else:
            args.robot_version='1'
            status('CHECK','Noninteractive/check mode: OpenArm 1.0; use --robot-version 2 for 2.0')
    status('OK',f'Robot: OpenArm {args.robot_version}.0')
    build_image(args.rebuild)
    mode, opts, reason=select_presentation(args,system,endpoint)
    status('OK',f'Display: {"none" if mode == "headless" else "browser" if mode == "cpu" else "host desktop"}; rendering: {"GPU" if mode == "gpu" else "CPU"} - {reason}')
    status('OK','Physics: MuJoCo CPU; GPU selection accelerates rendering only')
    (STATE/'environment.json').write_text(json.dumps({'robot_version':args.robot_version,'host':system,'docker':info.get('ServerVersion'),'mode':mode,'reason':reason},indent=2),encoding='utf-8')
    if args.check: return
    old=existing()
    if old:
        docker('stop',NAME);docker('rm',NAME)
    def launch(selected, device_options):
        options=['run','-d','-e',f'OPENARM_VERSION={args.robot_version}','-e',f'LP_NUM_THREADS={min(8, os.cpu_count() or 2)}','-e','OPENARM_VIEWER_FPS=30','--init','--name',NAME,'--label',f'{LABEL}={ROOT}','--shm-size=512m',*device_options]
        dev = STATE / 'dev_ws'
        (dev / 'src').mkdir(parents=True, exist_ok=True)
        (dev / '.home').mkdir(exist_ok=True)
        guide = dev / 'README.md'
        if not guide.exists():
            guide.write_text('# OpenArm development workspace\n\nCommands run inside Docker. Clone ROS packages into src/, then run colcon build --symlink-install here.\nFiles persist on the host under .openarm/dev_ws.\nSimulation source: /workspaces/OpenArm_sim.\n', encoding='utf-8')
        options += ['--mount', f'type=bind,source={ROOT},target=/workspaces/OpenArm_sim',
                    '--mount', f'type=bind,source={dev},target=/workspaces/OpenArm_dev']
        if system == 'Linux':
            options += ['--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/workspaces/OpenArm_dev/.home', '--workdir', '/workspaces/OpenArm_dev']
        if selected=='cpu':options+=['-p',f'127.0.0.1:{args.port}:6080','-e','LIBGL_ALWAYS_SOFTWARE=1']
        docker(*options,IMAGE,'headless' if selected=='headless' else 'web' if selected=='cpu' else 'native')
        wait_ready(selected,args.port)
    try:
        launch(mode,opts)
    except (RuntimeError,subprocess.TimeoutExpired):
        if mode in ('cpu','headless') or args.gpu or args.display=='native': raise
        status('WARN','Native display startup failed; retrying with CPU browser rendering')
        log=docker('logs',NAME,check=False)
        (STATE/'gpu-startup.log').write_text(log.stdout,encoding='utf-8')
        docker('rm','-f',NAME)
        mode='cpu'; reason='Native display startup failed; see .openarm/gpu-startup.log'; launch(mode,[])
    (STATE/'environment.json').write_text(json.dumps({'robot_version':args.robot_version,'host':system,'docker':info.get('ServerVersion'),'mode':mode,'reason':reason},indent=2),encoding='utf-8')
    status('OK', 'Headless simulation ready; use oa or oa-ros' if mode=='headless' else 'Native RViz + MuJoCo windows opened' if mode!='cpu' else f'Open http://localhost:{args.port}/vnc.html?autoconnect=true&resize=scale')
    print('Stop: bash start.sh --stop\nLogs: bash start.sh --logs',flush=True)

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt:
        status('WARN','Interrupted. Existing container may remain; use --stop.');sys.exit(130)
    except (RuntimeError,OSError,subprocess.TimeoutExpired,ValueError) as exc:
        status('FAIL',str(exc));sys.exit(1)
