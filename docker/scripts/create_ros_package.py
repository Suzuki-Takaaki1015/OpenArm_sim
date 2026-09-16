#!/usr/bin/env python3
"""Create a read-only ROS learning package in the persistent development workspace."""
import argparse
import keyword
from pathlib import Path
import re
import sys

WORKSPACE = Path('/workspaces/OpenArm_dev')

NODE = '''"""Read-only learning example: named joints, model metadata and bounded service calls."""
import json
import math
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger


def model_info():
    # Read the generated definition for THIS running container, not a fixed joint count.
    root = ET.parse(Path(os.environ['OPENARM_CONFIG']) / 'openarm.urdf').getroot()
    joints = {}
    for joint in root.findall('joint'):
        if joint.get('type') == 'fixed':
            continue
        limit, mimic = joint.find('limit'), joint.find('mimic')
        joints[joint.attrib['name']] = {
            'type': joint.attrib['type'],
            'unit': 'm' if joint.get('type') == 'prismatic' else 'rad',
            'limits': dict(limit.attrib) if limit is not None else {},
            'mimic': dict(mimic.attrib) if mimic is not None else None,
        }
    return {'version': os.environ['OPENARM_VERSION'], 'joints': joints}


def positions_by_name(message):
    # Do not assume the incoming array order, or that optional velocity/effort exist.
    if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
        raise ValueError('JointState name/position mismatch or duplicate names')
    if not all(math.isfinite(value) for value in message.position):
        raise ValueError('JointState contains non-finite positions')
    return dict(zip(message.name, message.position))


class ReadExample(Node):
    def __init__(self):
        super().__init__('__PACKAGE___read_example', parameter_overrides=[
            Parameter('use_sim_time', value=True)])
        self.declare_parameter('timeout_sec', 5.0)
        self.declare_parameter('status_service', '/openarm/scene/status')
        self.positions = None
        self.subscription = self.create_subscription(
            JointState, '/mujoco/joint_states', self.on_joints, qos_profile_sensor_data)

    def on_joints(self, message):
        try:
            self.positions = positions_by_name(message)
        except ValueError as error:
            self.get_logger().warning(str(error))

    def read_once(self):
        timeout = float(self.get_parameter('timeout_sec').value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout_sec must be finite and positive')
        info = model_info()
        self.get_logger().info('MODEL ' + json.dumps(info, ensure_ascii=False))
        client = self.create_client(Trigger, self.get_parameter('status_service').value)
        future = None
        # A wall-clock deadline still expires when /clock is missing or paused.
        deadline = time.monotonic() + timeout
        try:
            while rclpy.ok() and not client.service_is_ready():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('scene status service discovery timed out')
                rclpy.spin_once(self, timeout_sec=min(0.1, remaining))
            future = client.call_async(Trigger.Request())
            while rclpy.ok():
                if future.done() and self.positions is not None and self.get_clock().now().nanoseconds > 0:
                    response = future.result()
                    if not response.success:
                        raise RuntimeError(response.message)
                    status = json.loads(response.message)
                    # Look up by name; v1/v2 finger counts and units are in MODEL above.
                    joint = 'openarm_left_joint1'
                    self.get_logger().info(f'{joint}={self.positions[joint]:.6f} rad')
                    self.get_logger().info('FINGERS ' + json.dumps({
                        name: {'position': value, 'unit': info['joints'][name]['unit']}
                        for name, value in self.positions.items() if 'finger' in name}))
                    self.get_logger().info('SCENE ' + json.dumps(status))
                    self.get_logger().info(f'READ_OK use_sim_time={self.get_parameter("use_sim_time").value} '
                                           f'time_ns={self.get_clock().now().nanoseconds}')
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('waiting for service response, JointState or /clock timed out')
                rclpy.spin_once(self, timeout_sec=min(0.1, remaining))
            raise RuntimeError('ROS context stopped')
        finally:
            if future is not None and not future.done():
                client.remove_pending_request(future)
                future.cancel()
            self.destroy_client(client)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = ReadExample()
        node.read_once()
    except (Exception, KeyboardInterrupt) as error:
        if node is not None:
            node.get_logger().error(str(error))
        raise SystemExit(1) from error
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
'''


def create_package(name, workspace=WORKSPACE):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', name) or keyword.iskeyword(name):
        raise ValueError('Use a Python package name: lowercase letters, digits and underscores')
    if name in {'rclpy', 'sensor_msgs', 'std_srvs', 'openarm_demos'} or hasattr(__import__('builtins'), name) or name in sys.stdlib_module_names:
        raise ValueError('Choose a name that does not shadow an existing Python/ROS module')
    workspace = Path(workspace)
    if not workspace.is_dir():
        raise ValueError('Persistent workspace missing. Open an oa-code container terminal first.')
    src = workspace / 'src'
    if src.is_symlink():
        raise ValueError('Refusing a symlinked src directory')
    src.mkdir(exist_ok=True)
    target = src / name
    # Exclusive directory creation also rejects files and broken/existing symlinks.
    target.mkdir()
    files = {
        'package.xml': f'''<?xml version="1.0"?>
<package format="3">
  <name>{name}</name><version>0.0.0</version>
  <description>Read-only OpenArm learning example</description>
  <maintainer email="developer@example.com">Developer</maintainer>
  <license>UNLICENSED</license>
  <buildtool_depend>ament_python</buildtool_depend>
  <exec_depend>rclpy</exec_depend><exec_depend>sensor_msgs</exec_depend>
  <exec_depend>std_srvs</exec_depend>
  <export><build_type>ament_python</build_type></export>
</package>
''',
        'setup.py': f'''from setuptools import setup
setup(name='{name}', version='0.0.0', packages=['{name}'],
      data_files=[('share/ament_index/resource_index/packages', ['resource/{name}']),
                  ('share/{name}', ['package.xml', 'README.md'])],
      install_requires=['setuptools'], zip_safe=True,
      maintainer='Developer', maintainer_email='developer@example.com',
      description='Read-only OpenArm learning example', license='UNLICENSED',
      entry_points={{'console_scripts': ['read_example = {name}.read_example:main']}})
''',
        'setup.cfg': f'[develop]\nscript_dir=$base/lib/{name}\n[install]\ninstall_scripts=$base/lib/{name}\n',
        f'resource/{name}': '',
        f'{name}/__init__.py': '',
        f'{name}/read_example.py': NODE.replace('__PACKAGE__', name),
        'README.md': f'''# {name}

`oa-code`で開いた**コンテナ内ターミナル**で実行します。

```bash
cd /workspaces/OpenArm_dev && colcon build --symlink-install --packages-select {name}
```

```bash
source /workspaces/OpenArm_dev/install/setup.bash && ros2 run {name} read_example
```

読み取りを1回行い終了します。同じ実行コマンドで何度でも読み取れます。
`use_sim_time`は既定true。JointStateは名前で参照し、配列順序に依存しません。
`MODEL`は現在のコンテナの`$OPENARM_CONFIG/openarm.urdf`から関節型・単位・上下限・mimicを取得します。
1.0の指は直動（m）、2.0は回転（rad）でfinger_joint2がmimicです。
この定義は配信値そのものではありません。`FINGERS`が受信した実測位置です。
`SCENE`はstd_srvs/srv/Trigger型の`/openarm/scene/status`のJSON応答です。
ROS型の詳細は以下で確認できます。

```bash
ros2 interface show sensor_msgs/msg/JointState
```

```bash
ros2 interface show std_srvs/srv/Trigger
```

サービス探索・応答・関節・時計の受信は合計5秒の実時間でタイムアウトし、失敗時は終了コード1です。
時計停止中も待ち続けません。継続購読に変更する際はon_jointsを編集し、外側でspinしてください。

```bash
source /workspaces/OpenArm_dev/install/setup.bash && ros2 run {name} read_example --ros-args -p timeout_sec:=10.0
```

生成を同じ名前で再実行すると既存ファイルを保護して停止します。編集内容は上書きされません。
ソースはホストのcheckout/.openarm/dev_ws/srcに永続化されます。
このサンプルは指令を送信せず、状態の健康判定は行いません。環境診断にはホストのoa-doctorを使います。
配布する際はpackage.xmlとsetup.pyの作者・メール・ライセンスを自分のものに変更してください。
''',
    }
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?', default='my_openarm_reader')
    args = parser.parse_args()
    try:
        target = create_package(args.name)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Cannot create package: {error}\nExisting files are never overwritten.\n')
    print(f'Created {target}\nRead {target / "README.md"} for build/run commands.')


if __name__ == '__main__':
    main()
