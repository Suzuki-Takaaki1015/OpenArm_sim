"""Supervise the simulation stack; restart requests stay inside this container."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import re
import tempfile

SOCKET = '/tmp/openarm-supervisor.sock'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gui', action='store_true')
    args=parser.parse_args()
    stopping=False
    def stop_signal(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    mounted=False
    mobile = os.getenv('HAPPY_MOBILE') == '1'
    from room_layout import ACTIVE, EMPTY, compose, read, write
    runtime = tempfile.TemporaryDirectory(prefix='happy-room-stack-') if mobile else None
    layout = EMPTY
    if mobile and ACTIVE.exists():
        try:
            layout = read(ACTIVE)
        except (ValueError, OSError) as exc:
            print(f'[room] Saved room could not be loaded: {exc}. Starting with an empty room.', flush=True)
    def start_stack(start_lidar=False):
        from lidar_variant import detached
        env=dict(os.environ,OPENARM_LIDAR_MOUNTED='1' if mounted else '0',
                 OPENARM_LIDAR_AUTOSTART='1' if mounted and start_lidar else '0')
        if not mounted:
            for key in ('OPENARM_MODEL','OPENARM_SCENE'):
                env[key]=str(detached(env[key]))
        if mobile and layout['items']:
            env['OPENARM_SCENE'] = str(compose(env['OPENARM_SCENE'], layout, runtime.name))
            snapshot = Path(runtime.name) / 'room.json'
            write(snapshot, layout)
            env['HAPPY_ROOM_SNAPSHOT'] = str(snapshot)
        print('[supervisor] Starting complete ROS/MoveIt/MuJoCo stack', flush=True)
        return subprocess.Popen(['ros2','launch','/opt/openarm/app/simulation.launch.py',f'gui:={str(args.gui).lower()}'],env=env,start_new_session=True)
    def stop_stack(process):
        if process is None or process.poll() is not None:return
        os.killpg(process.pid,signal.SIGINT)
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    # A live supervisor must never be displaced.
    if Path(SOCKET).exists():
        probe=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:probe.connect(SOCKET)
        except OSError:Path(SOCKET).unlink()
        else:raise RuntimeError('A supervisor is already running')
        finally:probe.close()
    server.bind(SOCKET);os.chmod(SOCKET,0o600);server.listen(2);server.settimeout(0.25)
    stack=None;panel=None
    try:
        stack=start_stack()
        if args.gui:panel=subprocess.Popen(['python','/opt/openarm/app/scene_panel.py'],start_new_session=True)
        reported=False
        while not stopping:
            if stack.poll() is not None and not reported:
                print('[supervisor] Stack stopped; use Restart in the scene panel to recover',flush=True);reported=True
                if not args.gui:break
            try:client,_=server.accept()
            except socket.timeout:continue
            with client:
                client.settimeout(1)
                try:request=client.recv(32).strip()
                except socket.timeout:continue
                start_lidar = request == b'lidar-start'
                if start_lidar:
                    if mounted and stack.poll() is None:
                        try:
                            client.sendall(b'mounted\n')
                        except OSError:
                            pass  # The requesting GUI may have closed during the previous restart.
                        continue
                    mounted = True
                elif request in (b'lidar-attach',b'lidar-detach'):
                    mounted=request==b'lidar-attach'
                elif mobile and re.fullmatch(rb'room-[0-9a-f]{16}', request):
                    token = request.decode()[5:]
                    try:
                        candidate = read(Path('/tmp') / f'happy-room-{token}.json')
                        write(ACTIVE, candidate)
                    except (ValueError, OSError) as exc:
                        client.sendall(str(exc).encode()[:900])
                        continue
                    layout = candidate
                elif request!=b'restart':
                    client.sendall(b'unknown request\n');continue
                try:
                    client.sendall(b'restarting\n')
                except OSError:
                    pass  # Apply an accepted request even if the editor was closed.
            stop_stack(stack)
            if not stopping:stack=start_stack(start_lidar);reported=False
    finally:
        stop_stack(stack)
        if panel is not None and panel.poll() is None:
            panel.terminate()
            try:panel.wait(timeout=3)
            except subprocess.TimeoutExpired:panel.kill();panel.wait()
        server.close();Path(SOCKET).unlink(missing_ok=True)
        if runtime is not None:runtime.cleanup()

if __name__=='__main__':main()
