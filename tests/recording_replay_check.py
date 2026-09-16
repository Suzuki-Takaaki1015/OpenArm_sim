"""Read-only playback validation on a separate ROS domain."""
import os
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
assert os.environ.get('ROS_DOMAIN_ID')=='184'
import subprocess
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image
from tf2_msgs.msg import TFMessage
from recording import TOPICS
rclpy.init();node=Node('recording_replay_check')
counts={'clock':0,'image':0,'static':0}
def received(key):
    def cb(msg):counts[key]+=1
    return cb
node.create_subscription(Clock,'/clock',received('clock'),10)
node.create_subscription(Image,'/camera/camera/color/image_raw',received('image'),10)
node.create_subscription(TFMessage,'/tf_static',received('static'),QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE))
process=subprocess.Popen(['ros2','bag','play','/workspaces/OpenArm_dev/recordings/rgbd/bag','--delay','2','--topics',*TOPICS],cwd='/workspaces/OpenArm_dev')
try:
    end=time.monotonic()+25
    while time.monotonic()<end and process.poll() is None:rclpy.spin_once(node,timeout_sec=.1)
    assert process.wait(timeout=5)==0
    assert all(counts.values()),counts
    topics=dict(node.get_topic_names_and_types())
    assert not any('command' in t or 'trajectory' in t for t in topics),topics
    print('PASS ISOLATED PLAYBACK',counts,flush=True)
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=5)
    node.destroy_node();rclpy.shutdown()
