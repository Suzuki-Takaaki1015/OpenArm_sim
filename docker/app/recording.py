"""Explicit, bounded-lifecycle rosbag2 recording. No actuator topics or replay."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time

ROOT = Path('/workspaces/OpenArm_dev/recordings')
MIN_FREE = 1024 ** 3
STOP_FREE = 512 * 1024 ** 2
TOPICS = ['/clock', '/joint_states', '/mujoco/joint_states',
          '/openarm/sim_state', '/openarm/object_state', '/tf', '/tf_static'] + [
    '/camera/camera/' + stream + '/' + leaf
    for stream in ('color', 'depth', 'aligned_depth_to_color')
    for leaf in (('image_rect_raw' if stream == 'depth' else 'image_raw'), 'camera_info')]


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_root():
    for part in [ROOT.parent, ROOT]:
        if part.is_symlink():
            raise ValueError('保存先のシンボリックリンクは使用できません')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    return ROOT


def valid_name(name):
    if not re.fullmatch(r'[\w -]{1,64}', name, re.UNICODE) or not name.strip():
        raise ValueError('名前は1～64文字の文字・数字・空白・_・-で指定してください')
    return name


def atomic_json(path, data):
    temporary = path.with_suffix('.tmp')
    with open(temporary, 'x', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def previous_status():
    """Read only; never delete or resume incomplete user sessions."""
    try:
        root = safe_root()
        unfinished = []
        for directory in root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            path = directory / 'openarm.json'
            if path.is_symlink():
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('state') not in ('complete', 'error'):
                    unfinished.append(path.parent.name)
            except (OSError, ValueError):
                unfinished.append(path.parent.name)
        return ('未完了または別画面で記録中: ' + ', '.join(unfinished[-3:]) + '。自動再開しません。') if unfinished else '停止中（自動記録なし）'
    except Exception as exc:
        return '保存先を確認してください: ' + str(exc)


def emit(state, message, **extra):
    try:
        print(json.dumps(dict(state=state, message=message, **extra), ensure_ascii=False), flush=True)
    except BrokenPipeError:
        pass


def record(name):
    import rclpy
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from rosgraph_msgs.msg import Clock
    from std_srvs.srv import Trigger

    stopping = False
    reason = 'user_stop'
    def stop_signal(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    root = safe_root()
    valid_name(name)
    # Never unlink the lock: all launchers must lock the same inode.
    fd = os.open(root / '.recording.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    node = None
    proc = None
    session = None
    data = None
    log = None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('記録ロックが通常ファイルではありません')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('このworkspaceでは既に記録中です')
        if shutil.disk_usage(root).free < MIN_FREE:
            raise RuntimeError('空き容量が1 GiB未満のため開始できません')
        if os.path.lexists(root / name):
            raise FileExistsError('同名の記録が存在します。別の名前にしてください')
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = Node('openarm_recording_monitor')
        latest = [None, time.monotonic()]
        clock_reset = [False]
        def clock(msg):
            value = msg.clock.sec * 1000000000 + msg.clock.nanosec
            if latest[0] is not None and value < latest[0]:
                clock_reset[0] = True
            latest[:] = value, time.monotonic()
        node.create_subscription(Clock, '/clock', clock, 10)
        def status(service):
            client = node.create_client(Trigger, service)
            try:
                deadline = time.monotonic() + 5
                while not client.wait_for_service(timeout_sec=.1):
                    if stopping or time.monotonic() >= deadline:
                        raise RuntimeError('状態サービスに接続できません: ' + service)
                future = client.call_async(Trigger.Request())
                while not future.done():
                    rclpy.spin_once(node, timeout_sec=.1)
                    if stopping or time.monotonic() >= deadline:
                        raise RuntimeError('状態取得が時間切れです: ' + service)
                response = future.result()
                if not response.success:
                    raise RuntimeError(response.message)
                return json.loads(response.message)
            finally:
                node.destroy_client(client)
        scene = status('/openarm/scene/status')
        camera = status('/openarm/camera/status')
        deadline = time.monotonic() + 5
        while latest[0] is None or latest[0] == 0:
            rclpy.spin_once(node, timeout_sec=.1)
            if stopping or time.monotonic() > deadline:
                raise RuntimeError('シミュレーション時計を受信できません')
        if stopping:
            return
        session = root / name
        session.mkdir(mode=0o700)  # Exclusive; no overwrite, including dangling links.
        config = session / 'config'
        config.mkdir()
        hashes = {}
        sources = list(Path(os.environ['OPENARM_CONFIG']).glob('*'))
        sources += [Path(os.environ['OPENARM_SCENE']), Path(os.environ['OPENARM_MODEL'])]
        sources += [Path(__file__).with_name(n) for n in ('camera_mount.py', 'environment_assets.py', 'scene_objects.py')]
        for index, source in enumerate(sources):
            if source.is_file():
                dest = config / (str(index) + '-' + source.name)
                content = source.read_bytes()
                dest.write_bytes(content)
                hashes[str(source)] = {'copy': str(dest.relative_to(session)), 'sha256': hashlib.sha256(content).hexdigest()}
        runtime_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in Path(__file__).parent.glob('*.py')}
        data = dict(runtime_sha256=runtime_hashes, schema='openarm.recording', version=1, state='starting', started_utc=utc(),
                    model=os.environ['OPENARM_VERSION'], ros_distro=os.environ.get('ROS_DISTRO'),
                    ros_domain_id=os.environ.get('ROS_DOMAIN_ID'), simulation_start_ns=latest[0],
                    topics=TOPICS, camera_start=camera, scene_start=scene, files=hashes,
                    time_basis='ROS simulation time; wall time only in this manifest',
                    replay='Use an isolated ROS_DOMAIN_ID. No control topics are recorded.',
                    free_bytes_start=shutil.disk_usage(root).free)
        atomic_json(session / 'openarm.json', data)
        qos = session / 'qos.yaml'
        qos.write_text('/tf_static:\n  history: keep_all\n  reliability: reliable\n  durability: transient_local\n', encoding='utf-8')
        log = open(session / 'recorder.log', 'x', encoding='utf-8')
        command = ['ros2', 'bag', 'record', '--storage', 'mcap', '--output', str(session / 'bag'),
                   '--node-name', 'openarm_bag_' + str(os.getpid()),
                   '--use-sim-time', '--disable-keyboard-controls', '--max-cache-size', '16777216',
                   '--qos-profile-overrides-path', str(qos), '--topics', *TOPICS]
        # The recorder also holds the lock if this monitor is killed abruptly.
        child = [sys.executable, str(Path(__file__)), '--recorder-child', str(os.getpid()), *command]
        proc = subprocess.Popen(child, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, pass_fds=(fd,), cwd=session)
        warning = 'カメラON：RGBDを記録します' if camera['enabled'] else 'カメラOFF：画像は届きません（自動でONにしません）'
        started = time.monotonic()
        announced = False
        while not stopping:
            rclpy.spin_once(node, timeout_sec=.1)
            if proc.poll() is not None:
                raise RuntimeError('rosbag2が終了しました。recorder.logを確認してください')
            if clock_reset[0]:
                reason = 'clock_reset'; break
            if time.monotonic() - latest[1] > 5:
                reason = 'clock_timeout'; break
            if shutil.disk_usage(root).free < STOP_FREE:
                reason = 'low_disk'; break
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline()
                if not line or line.strip() == 'stop':
                    reason = 'gui_closed' if not line else 'user_stop'; break
            if (not announced and list((session / 'bag').glob('*.mcap'))
                    and all(any(info.node_name == 'openarm_bag_' + str(os.getpid())
                                for info in node.get_subscriptions_info_by_topic(topic)) for topic in TOPICS)):
                data['state'] = 'recording'
                atomic_json(session / 'openarm.json', data)
                emit('recording', '記録中 — ' + warning, path=str(session))
                announced = True
            if not announced and time.monotonic() - started > 10:
                raise RuntimeError('rosbag2の開始を確認できません')
        emit('stopping', '記録を保存しています…')
        os.killpg(proc.pid, signal.SIGINT)
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            raise RuntimeError('保存終了が時間切れです。記録は未完了の可能性があります')
        if code not in (0, 130) or not (session / 'bag/metadata.yaml').is_file():
            raise RuntimeError('rosbag2の正常保存を確認できません')
        import yaml
        bag_meta = yaml.safe_load((session / 'bag/metadata.yaml').read_text())['rosbag2_bagfile_information']
        if bag_meta.get('message_count', 0) == 0:
            raise RuntimeError('記録メッセージが0件です。開始準備後に停止してください')
        data['message_count'] = bag_meta['message_count']
        data.update(state='complete' if reason in ('user_stop', 'gui_closed') else 'error',
                    stop_reason=reason, ended_utc=utc(), simulation_end_ns=latest[0],
                    bag_finalized=True, recorder_exit_code=code)
        atomic_json(session / 'openarm.json', data)
        reasons = {'low_disk': '空き容量が512 MiB未満', 'clock_timeout': '時計を5秒間受信できません', 'clock_reset': '時計が後戻りしました'}
        emit(data['state'], ('保存完了' if data['state'] == 'complete' else '保護停止: ' + reasons.get(reason, reason)) + ' — ' + str(session))
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        if data is not None:
            data.update(state='error', error=str(exc), ended_utc=utc())
            try:
                atomic_json(session / 'openarm.json', data)
            except OSError:
                pass
        emit('error', str(exc))
        return 1
    finally:
        if log is not None: log.close()
        if node is not None:
            node.destroy_node()
            if rclpy.ok(): rclpy.shutdown()
        os.close(fd)
    return 0 if data is None or data.get('state') == 'complete' else 1


class Controller:
    """GUI owns stdin; GUI death/close requests a normal recorder shutdown."""
    def __init__(self):
        self.proc = None
        self.events = queue.Queue()
        self.stopping = False

    def active(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, name):
        if self.active():
            raise RuntimeError('既に記録中です')
        valid_name(name)
        self.stopping = False
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__)), name],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
        proc = self.proc
        def reader():
            last = ''
            terminal = False
            for line in proc.stdout:
                last = line.strip()
                try:
                    event = json.loads(line)
                    terminal |= event.get('state') in ('complete', 'error')
                    self.events.put(event)
                except ValueError:
                    pass
            proc.wait()
            if not terminal:
                self.events.put(dict(state='error', message='記録処理が終了しました: ' + last[-200:]))
            self.events.put(dict(state='idle', message=''))
            proc.stdout.close()
            proc.stdin.close()
        threading.Thread(target=reader, daemon=True).start()

    def stop(self):
        if self.active() and not self.stopping:
            self.stopping = True
            try:
                self.proc.stdin.write('stop\n'); self.proc.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--recorder-child':
        # Linux parent-death signal protects an abruptly killed monitor too.
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGINT, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'prctl')
        if os.getppid() != int(sys.argv[2]):
            sys.exit(1)
        os.execvp(sys.argv[3], sys.argv[3:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    sys.exit(record(parser.parse_args().name))
