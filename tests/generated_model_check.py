"""Explicit disposable-container checks; never start a ROS stack or a user workspace."""
import argparse
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_match():
    count = 0
    for local, installed in [('app', '/opt/openarm/app'), ('scripts', '/opt/openarm/scripts'), ('demos', '/opt/openarm/demo_ws/src')]:
        source = Path('/source/docker') / local
        def files(root):
            return {p.relative_to(root): p for p in root.rglob('*') if p.is_file()
                    and '__pycache__' not in p.parts and not any(n.endswith('.egg-info') for n in p.parts)}
        expected, actual = files(source), files(Path(installed))
        require(expected.keys() == actual.keys(), f'{local}: 配布ファイル集合がイメージと不一致。検証イメージを再ビルドしてください')
        for name, path in expected.items():
            require(hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(actual[name].read_bytes()).digest(),
                    f'古いイメージ: {local}/{name} がsourceと不一致。再ビルドしてください')
            count += 1
    print(f'PASS source/image: app/scripts/demo {count}ファイルSHA-256一致（モデル資産全体の同一性証明ではありません）', flush=True)


def generated(version):
    import mujoco as mj
    import numpy as np
    import yaml
    directory = Path(f'/opt/openarm/config/v{version}')
    model_path = Path(f'/opt/openarm/models/v{version}') / ('openarm_bimanual.xml' if version == 1 else 'simulation_robot.xml')
    model = mj.MjModel.from_xml_path(str(model_path))
    urdf = ET.parse(directory / 'openarm.urdf')
    srdf = ET.parse(directory / 'openarm.srdf')
    joints = {j.get('name'): j for j in urdf.findall('joint') if j.get('type') != 'fixed'}
    model_joints = {mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, i): i for i in range(model.njnt)}
    require(joints.keys() == model_joints.keys(), f'v{version}: MJCF/URDF関節集合不一致')
    for name, joint in joints.items():
        index = model_joints[name]
        expected_type = 'prismatic' if model.jnt_type[index] == mj.mjtJoint.mjJNT_SLIDE else 'revolute'
        require(joint.get('type') == expected_type, f'{name}: 関節型不一致')
        limit = joint.find('limit')
        require(np.allclose([float(limit.get('lower')), float(limit.get('upper'))], model.jnt_range[index]), f'{name}: 関節範囲不一致')
    for side in ('left', 'right'):
        for number in (1, 2):
            name = f'openarm_{side}_finger_joint{number}'
            require(joints[name].get('type') == ('prismatic' if version == 1 else 'revolute'), f'{name}: 指の単位/型がモデルと不一致')
            mimic = joints[name].find('mimic')
            require((mimic is not None) == (version == 2 and number == 2), f'{name}: mimic不一致')
            if mimic is not None:
                require(mimic.get('joint') == name[:-1]+'1', f'{name}: mimic先不一致')
    controllers = yaml.safe_load((directory / 'controllers.yaml').read_text())
    moveit = yaml.safe_load((directory / 'moveit_controllers.yaml').read_text())
    limits = yaml.safe_load((directory / 'joint_limits.yaml').read_text())['joint_limits']
    require(controllers['controller_manager']['ros__parameters']['use_sim_time'] is True, 'controller clock must be simulation time')
    expected = {}
    for side in ('left', 'right'):
        expected[f'{side}_arm_controller'] = [f'openarm_{side}_joint{i}' for i in range(1, 8)]
        expected[f'{side}_gripper_controller'] = [f'openarm_{side}_finger_joint{i}' for i in range(1, 3 if version == 1 else 2)]
    require(set(moveit['controller_names']) == set(expected), 'MoveIt controller集合不一致')
    commanded = set()
    for name, names in expected.items():
        require(controllers[name]['ros__parameters']['joints'] == moveit[name]['joints'] == names, f'{name}: 指令関節の不一致')
        commanded.update(names)
    hardware = {j.get('name') for j in urdf.findall('ros2_control/joint')}
    require(hardware == commanded, 'ros2_controlと指令対象不一致（mimicの誤追加等）')
    require(set(limits) == set(joints), 'joint_limits関節集合不一致')
    for name, item in limits.items():
        require(all(math.isfinite(item[k]) and item[k] > 0 for k in ('max_velocity', 'max_acceleration')), f'{name}: 非有限/非正の動作制限')
    links = {n.get('name') for n in urdf.findall('link')}
    for node in srdf.findall('.//joint'):
        require(node.get('name') in joints, f'SRDFの未知関節: {node.get("name")}')
        if node.get('value') is not None:
            value = float(node.get('value')); bounds = model.jnt_range[model_joints[node.get('name')]]
            require(math.isfinite(value) and bounds[0]-1e-8 <= value <= bounds[1]+1e-8, f'SRDFの範囲外姿勢: {node.attrib}')
    for node in srdf.findall('.//chain'):
        require(node.get('base_link') in links and node.get('tip_link') in links, 'SRDF chainの未知リンク')
    for node in srdf.findall('disable_collisions'):
        require(node.get('link1') in links and node.get('link2') in links, 'SRDF collisionの未知リンク')
    for mesh in urdf.findall('.//mesh'):
        require(Path(mesh.get('filename').removeprefix('file://')).is_file(), f'URDFメッシュ参照なし: {mesh.attrib}')
    scene = mj.MjModel.from_xml_path(str(model_path.parent / 'simulation_scene.xml'))
    from environment_assets import ITEMS
    for key, item in ITEMS.items():
        require(mj.mj_name2id(scene, mj.mjtObj.mjOBJ_BODY, item['id']) >= 0, f'v{version}: シーンにカタログ物体なし: {key}')
    print(f'PASS v{version}: MJCF/URDF/SRDF/ros2_control/MoveIt/limits/mesh、カタログ{len(ITEMS)}物体', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('models', 'physics'), required=True)
    args = parser.parse_args()
    require(os.environ.get('OPENARM_ISOLATED_TEST') == '1' and Path('/source').is_dir(), 'scripts/check_dev.py isolated経由で実行してください')
    source_match()
    for version in (1, 2):
        generated(version)
    subprocess.run([sys.executable, '/source/tests/render_model_check.py'], check=True, timeout=120)
    print('未検証: 修正前イメージとの質量・慣性比較（beforeデータはこの導線では生成しません）', flush=True)
    if args.suite == 'physics':
        subprocess.run([sys.executable, '/source/tests/opl_physics_check.py'], check=True, timeout=180)
        for version in (1, 2):
            subprocess.run(['/opt/openarm/scripts/entrypoint.sh', 'python', '/source/tests/presets_transaction_check.py'],
                           env={**os.environ, 'OPENARM_VERSION': str(version)}, check=True, timeout=60)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
