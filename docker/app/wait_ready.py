"""Wait for valid physics feedback before activating the trajectory controllers."""
import math, time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
rclpy.init();node=Node('wait_for_mujoco');ready=False

def callback(msg):
    global ready
    ready=bool(msg.name) and len(msg.name)==len(msg.position) and all(math.isfinite(v) for v in msg.position)
node.create_subscription(JointState,'/mujoco/joint_states',callback,10)
deadline=time.monotonic()+90
while rclpy.ok() and not ready and time.monotonic()<deadline:rclpy.spin_once(node,timeout_sec=.1)
node.destroy_node();rclpy.shutdown()
if not ready:raise SystemExit('Timed out waiting for MuJoCo feedback')
print('MuJoCo feedback ready; activating controllers',flush=True)
