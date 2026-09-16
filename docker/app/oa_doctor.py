#!/usr/bin/env python3
"""Read-only OpenArm diagnostics. Host and container share this implementation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def emit(label, state, detail, next_step=''):
    print(f'[{state}] {label}: {detail}', flush=True)
    if next_step:
        print(f'  次の操作: {next_step}', flush=True)


def run(command, timeout=5, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)


def host(args):
    try:
        result = run(['docker', 'inspect', args.container])
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        info = json.loads(result.stdout)[0]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        emit('Docker', '要確認', str(exc), 'Dockerの起動・権限とコンテナ名を確認してください。起動はリポジトリで bash start.sh。')
        emit('ROS診断', '未確認', 'コンテナに接続できないため省略しました。')
        return 1
    if not info['State']['Running']:
        emit('Docker', '要確認', 'コンテナは停止中です。', 'リポジトリで bash start.sh を実行してください。')
        emit('ROS診断', '未確認', '停止中のため省略しました。')
        return 1
    emit('Docker', '正常', f'{args.container} は稼働中')
    env = dict(v.split('=', 1) for v in info['Config'].get('Env', []) if '=' in v)
    version = env.get('OPENARM_VERSION', '1')
    model_bad = version not in ('1', '2')
    emit('選択モデル', '正常' if not model_bad else '要確認', f'コンテナ OpenArm {version}.0')
    root = next((m['Source'] for m in info.get('Mounts', []) if m['Destination'] == '/workspaces/OpenArm_sim'), None)
    if root:
        try:
            selected = str(json.loads((Path(root)/'.openarm/environment.json').read_text())['robot_version'])
            if selected != version:
                model_bad = True
                emit('モデル選択の一致', '要確認', f'起動設定 {selected}.0 / 実行中 {version}.0', '実行中モデルを確認し、切替が必要なら終了後に start.sh --robot-version 1 または 2 を実行してください。')
        except (OSError, ValueError, KeyError):
            emit('起動設定', '未確認', '保存されたモデル設定を読めません。コンテナの設定を表示しています。')
    # stdin avoids changing files in the container or requiring a rebuilt image.
    command = ['docker', 'exec', '-i', args.container, '/opt/openarm/scripts/entrypoint.sh',
               'timeout', '--kill-after=1s', '13s', 'python', '-', '--probe']
    try:
        result = run(command, timeout=17, input=Path(__file__).read_text(encoding='utf-8'))
        print(result.stdout, end='', flush=True)
        if result.returncode not in (0, 1):
            emit('ROS診断', '要確認', '診断が終了できませんでした（時間切れ、起動中、または依存関係の不足）。', 'oa-logs で起動ログを確認し、起動完了後に再診断してください。')
            if result.stderr:
                print(result.stderr[-1200:])
        return int(model_bad or result.returncode != 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        emit('ROS診断', '要確認', f'接続失敗または時間切れ: {exc}', 'Dockerの状態を確認してから再診断してください。')
        return 1


def probe():
    sys.path.insert(0, '/opt/openarm/app')
    import rclpy
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from std_msgs.msg import String
    from sensor_msgs.msg import Image
    from std_srvs.srv import Trigger
    from controller_manager_msgs.srv import ListControllers
    from moveit_msgs.srv import GetPlanningScene
    from moveit_msgs.msg import PlanningSceneComponents
    from environment_assets import ITEMS
    from scene_objects import OBJECTS

    rclpy.init(args=[])
    node = Node('oa_doctor_' + str(os.getpid()), start_parameter_services=False, parameter_overrides=[Parameter('use_sim_time', value=True)])
    received = {'clock': [], 'state': [], 'images': {}, 'image_wall': {}, 'clock_wall': 0, 'state_wall': 0}
    def clock(msg):
        received['clock_wall'] = time.monotonic()
        received['clock'].append(msg.clock.sec * 1000000000 + msg.clock.nanosec)
    def snapshot(msg):
        received['state_wall'] = time.monotonic()
        received['state'].append(json.loads(msg.data))
        received['state'][:] = received['state'][-2:]
    node.create_subscription(Clock, '/clock', clock, qos_profile_sensor_data)
    node.create_subscription(String, '/openarm/sim_state', snapshot, qos_profile_sensor_data)
    for stream in ('color', 'depth', 'aligned_depth_to_color'):
        topic = f'/camera/camera/{stream}/' + ('image_rect_raw' if stream == 'depth' else 'image_raw')
        def image(msg, key=stream):
            received['image_wall'][key] = time.monotonic()
            samples = received['images'].setdefault(key, [])
            samples.append((msg.header.stamp.sec, msg.header.stamp.nanosec))
            samples[:] = samples[-2:]
        node.create_subscription(Image, topic, image, qos_profile_sensor_data)
    request = GetPlanningScene.Request()
    request.components.components = (PlanningSceneComponents.WORLD_OBJECT_GEOMETRY |
                                     PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS)
    pending = {}
    clients = {
        'controllers': (node.create_client(ListControllers, '/controller_manager/list_controllers'), ListControllers.Request()),
        'scene': (node.create_client(GetPlanningScene, '/get_planning_scene'), request),
        'camera': (node.create_client(Trigger, '/openarm/camera/status'), Trigger.Request()),
    }
    end = time.monotonic() + 7
    while time.monotonic() < end:
        for key, (client, req) in clients.items():
            if key == 'scene' and time.monotonic() < end - 2:
                continue
            if key not in pending and client.service_is_ready():
                pending[key] = client.call_async(req)
        rclpy.spin_once(node, timeout_sec=.1)
    results = {}
    for key, future in pending.items():
        if future.done() and future.exception() is None:
            results[key] = future.result()
    bad = False
    def report(label, ok, detail, hint):
        nonlocal bad
        bad |= not ok
        emit(label, '正常' if ok else '要確認', detail, '' if ok else hint)
    names = set(node.get_node_names())
    required = {'openarm_mujoco', 'controller_manager', 'move_group', 'openarm_object_scene_sync', 'openarm_d435_sim'}
    missing = sorted(required - names)
    report('ROSグラフ', not missing, '必要ノードを検出' if not missing else '未検出: ' + ', '.join(missing), '起動完了を待ち、oa-logs で該当ノードのエラーを確認してください。')
    times = received['clock']
    ticking = len(times) > 1 and times[-1] > times[0] and time.monotonic() - received['clock_wall'] < 1.5
    report('/clock 更新', ticking, f'{len(times)} 件受信' + (f' / 進行 {(times[-1]-times[0])/1e9:.2f} 秒' if times else ''), 'MuJoCoの起動・一時停止状態とログを確認してください。')
    controllers = {c.name: c.state for c in results['controllers'].controller} if 'controllers' in results else {}
    for name in ('joint_state_broadcaster', 'left_arm_controller', 'right_arm_controller', 'left_gripper_controller', 'right_gripper_controller'):
        state = controllers.get(name, '応答なし／未検出')
        label = {'joint_state_broadcaster': '関節状態配信', 'left_arm_controller': '左腕', 'right_arm_controller': '右腕', 'left_gripper_controller': '左指', 'right_gripper_controller': '右指'}[name]
        report(f'{label} ({name})', state == 'active', '稼働中（active）' if state == 'active' else state, 'oa-logs でコントローラー初期化とモデル設定を確認してください。')
    version = os.environ.get('OPENARM_VERSION', '1')
    report('モデル設定', version in ('1', '2'), 'OpenArm ' + version + '.0', '対応モデルは1.0/2.0です。起動設定を確認してください。')
    if 'controllers' in results and version in ('1', '2'):
        actual = {c.name: set(c.claimed_interfaces) for c in results['controllers'].controller}
        wrong = []
        for side in ('left', 'right'):
            expected = {f'openarm_{side}_finger_joint{i}/position' for i in ((1, 2) if version == '1' else (1,))}
            if actual.get(side + '_gripper_controller') != expected:wrong.append(side)
        report('モデルと指制御の一致', not wrong, '1.0の2関節／2.0の1関節構成と一致' if not wrong else '指の制御関節が不一致: ' + ', '.join(wrong), 'モデル切替とコントローラー設定を確認してください。')
    services = dict(node.get_service_names_and_types())
    moveit = 'scene' in results and '/move_action/_action/send_goal' in services
    report('MoveIt', moveit, 'PlanningScene応答・計画アクションを検出' if moveit else 'PlanningScene応答または計画アクションを確認できません', 'MoveItの起動ログを確認してください。診断は運動・計画要求を送りません。')
    if received['state'] and time.monotonic() - received['state_wall'] < 1.5 and 'scene' in results:
        state = received['state'][-1]
        scene = results['scene'].scene
        world = {o.id: o for o in scene.world.collision_objects}
        attached = {o.object.id for o in scene.robot_state.attached_collision_objects}
        mismatch = []
        for table in OBJECTS:
            if bool(state.get('obstacles')) != (table['id'] in world):
                mismatch.append('作業台: 表示不一致')
        for key, item in ITEMS.items():
            current = state['objects'].get(key)
            if current is None:
                mismatch.append(key + ': 状態なし'); continue
            ident = item['id']
            if ident in attached:
                continue
            if current['enabled'] != (ident in world):
                mismatch.append(key + ': 表示不一致')
            elif current['enabled']:
                pose = world[ident].pose.position
                if max(abs(a-b) for a,b in zip(current['position'], (pose.x, pose.y, pose.z))) > .03:
                    mismatch.append(key + ': 位置差 > 3 cm')
        report('物体同期', not mismatch and 'openarm_object_scene_sync' in names, ', '.join(mismatch[:8]) if mismatch else f'配置状態・位置を照合（把持中 {len(attached)} 件は除外）', '移動中は差が出る場合があります。腕が停止してから再診断し、同期ノードのログを確認してください。')
    else:
        report('物体同期', False, 'sim_state または MoveIt の応答がありません', 'MuJoCo・MoveIt・物体同期ノードの起動ログを確認してください。')
    response = results.get('camera')
    if response and response.success:
        camera = json.loads(response.message)
        if camera.get('error'):
            report('カメラ', False, camera['error'], 'カメラの描画エラーをログで確認してください。')
        elif not camera['enabled']:
            emit('カメラ', '正常・待機', 'OFF（初期状態）。画像が流れていなくても正常です。', '画像を使う場合だけGUIの「配信開始」を押してください。')
        else:
            streams = received['images']
            missing = [k for k in ('color', 'depth', 'aligned_depth_to_color') if len(set(streams.get(k, []))) < 2 or time.monotonic() - received['image_wall'].get(k, 0) > 1.5]
            report('カメラ', not missing, 'ON・RGB/深度/整列深度の時刻更新を確認' if not missing else '画像更新なし: ' + ', '.join(missing), 'カメラログと /clock を確認してください。')
    else:
        report('カメラ', False, '状態サービスに応答がありません（OFFとは判定できません）', 'カメラノードの起動ログを確認してください。')
    node.destroy_node()
    rclpy.shutdown()
    print('診断完了。変更・修復・再起動は行っていません。')
    return int(bad)


def main():
    parser = argparse.ArgumentParser(description='OpenArm 読み取り専用診断（約7秒、ホスト実行は最大約22秒）')
    parser.add_argument('--container', default='openarm-auto', help='診断するコンテナ名')
    parser.add_argument('--probe', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.probe:print('OpenArm 環境診断（読み取り専用）', flush=True)
    if args.probe:
        return probe()
    if args.inside:
        emit('Docker', '正常', 'GUIを実行しているコンテナ内（ホストDockerデーモンは未確認）')
        version = os.environ.get('OPENARM_VERSION', '1')
        emit('選択モデル', '正常' if version in ('1', '2') else '要確認', f'OpenArm {version}.0')
        try:
            result = run(['timeout', '--kill-after=1s', '13s', sys.executable, __file__, '--probe'], timeout=16)
            print(result.stdout, end='')
            if result.returncode not in (0, 1):
                emit('ROS診断', '要確認', '診断プロセスの時間切れまたはエラー', '起動ログを確認してください。')
                print(result.stderr[-1200:])
            return int(result.returncode != 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            emit('ROS診断', '要確認', str(exc), '起動ログを確認してください。')
            return 1
    return host(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        emit('診断', '要確認', f'{type(exc).__name__}: {exc}', '起動完了後に再実行し、繰り返す場合はログを確認してください。')
        sys.exit(1)
