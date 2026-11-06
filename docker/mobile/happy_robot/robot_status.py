#!/usr/bin/env python3
"""Read real ROS endpoints without moving the robot."""
import time
import rclpy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan,JointState
from rclpy.qos import qos_profile_sensor_data
rclpy.init();node=rclpy.create_node('happy_robot_status');seen=set()
def arm(m):
    if 'openarm_left_joint1' in m.name:seen.add('arm')
node.create_subscription(JointState,'/joint_states',arm,10)
node.create_subscription(Odometry,'/odom',lambda m:seen.add('odom'),10)
node.create_subscription(LaserScan,'/scan',lambda m:seen.add('scan') if len(m.ranges)==1081 else None,qos_profile_sensor_data)
end=time.monotonic()+20
while len(seen)<3 and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.2)
print('Received:',', '.join(sorted(seen)));node.destroy_node();rclpy.shutdown()
raise SystemExit(0 if len(seen)==3 else 1)
