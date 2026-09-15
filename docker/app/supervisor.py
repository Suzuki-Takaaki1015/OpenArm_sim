"""Supervise the simulation stack; restart requests stay inside this container."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

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
    def start_stack():
        print('[supervisor] Starting complete ROS/MoveIt/MuJoCo stack', flush=True)
        return subprocess.Popen(['ros2','launch','/opt/openarm/app/simulation.launch.py',f'gui:={str(args.gui).lower()}'],start_new_session=True)
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
                if request!=b'restart':
                    client.sendall(b'unknown request\n');continue
                client.sendall(b'restarting\n')
            stop_stack(stack)
            if not stopping:stack=start_stack();reported=False
    finally:
        stop_stack(stack)
        if panel is not None and panel.poll() is None:
            panel.terminate()
            try:panel.wait(timeout=3)
            except subprocess.TimeoutExpired:panel.kill();panel.wait()
        server.close();Path(SOCKET).unlink(missing_ok=True)

if __name__=='__main__':main()
