"""Named scene storage and ROS transaction client used by the GUI."""
import argparse
import json
import sys
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from scene_presets import Store, decode, validate
from environment_assets import ITEMS
from scene_objects import OBJECTS
import os


def call(node, kind, name, request):
    client = node.create_client(kind, name)
    try:
        if not client.wait_for_service(timeout_sec=5):
            raise RuntimeError('シーンサービスに接続できません')
        future = client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=15)
        if not future.done():
            raise RuntimeError('応答期限切れ。状態を更新して結果を確認してください')
        return future.result()
    finally:
        node.destroy_client(client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['save', 'load'])
    parser.add_argument('name')
    args = parser.parse_args()
    store = Store()
    document = None
    if args.action == 'load':
        document = validate(store.load(args.name), ITEMS, OBJECTS, os.environ['OPENARM_VERSION'])
    rclpy.init()
    node = Node('openarm_scene_preset_client')
    try:
        if args.action == 'save':
            response = call(node, Trigger, '/openarm/scene/capture', Trigger.Request())
            if not response.success:
                raise RuntimeError(response.message)
            document = validate(decode(response.message), ITEMS, OBJECTS, os.environ['OPENARM_VERSION'])
            print('保存しました: ' + str(store.save(args.name, document)))
        else:
            parameter = Parameter(name='document', value=ParameterValue(type=ParameterType.PARAMETER_STRING,
                string_value=json.dumps(document, allow_nan=False)))
            response = call(node, SetParametersAtomically, '/openarm/scene/restore',
                SetParametersAtomically.Request(parameters=[parameter])).result
            if not response.successful:
                raise RuntimeError(response.reason)
            print(response.reason)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
