"""Run in the mobile simulator with the operations RViz open and MID-360S streaming."""
from collections import deque
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from tf2_ros import Buffer, TransformListener
import yaml


def main():
    config = yaml.safe_load(Path('/opt/happy/navigation/operations.rviz').read_text())
    manager = config['Visualization Manager']
    fixed = manager['Global Options']['Fixed Frame']
    topic = '/lidar/points'
    assert any(display['Class'] == 'rviz_default_plugins/PointCloud2' and display['Enabled']
               and display['Topic']['Value'] == topic for display in manager['Displays'])

    rclpy.init()
    node = rclpy.create_node('check_mobile_lidar_rviz')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    pending = deque(maxlen=10)
    stamps = set()
    node.create_subscription(PointCloud2, topic, lambda msg: pending.append(msg), qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.2)
            while pending:
                cloud = pending[0]
                stamp = Time.from_msg(cloud.header.stamp)
                if not buffer.can_transform(fixed, cloud.header.frame_id, stamp):
                    break
                pending.popleft()
                if cloud.width == 0:
                    continue
                assert cloud.header.frame_id == 'mid360s_link'
                assert cloud.point_step == 12 and [field.name for field in cloud.fields] == ['x', 'y', 'z']
                xyz = np.frombuffer(cloud.data, dtype='<f4').reshape(-1, 3)
                assert np.isfinite(xyz).all() and len(xyz) == cloud.width * cloud.height
                stamps.add(stamp.nanoseconds)
            if len(stamps) >= 3 and any(endpoint.node_name == 'navigation_rviz'
                                        for endpoint in node.get_subscriptions_info_by_topic(topic)):
                print(f'PASS operations RViz subscribed to {topic}; {len(stamps)} XYZ clouds with TF to {fixed}')
                return
        raise AssertionError(f'Expected the operations RViz subscriber and transformable XYZ scans; got {len(stamps)} stamps')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
