#!/usr/bin/env python3
"""Read an arm or plan and execute seven joint angles (degrees)."""
import argparse
import json
import math
import os
import signal
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import rclpy
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, MoveItErrorCodes


def names(side):
    return [f'openarm_{side}_joint{i}' for i in range(1, 8)]


def goal_for(side, degrees, speed):
    robot = ET.parse(Path(os.environ['OPENARM_CONFIG'])/'openarm.urdf')
    constraints = Constraints()
    for name, angle in zip(names(side), degrees, strict=True):
        limit = robot.find(f"joint[@name='{name}']/limit")
        value = math.radians(angle)
        if limit is None or not float(limit.get('lower')) <= value <= float(limit.get('upper')):
            raise ValueError(f'{name}: {angle}° is outside the joint limits')
        constraints.joint_constraints.append(JointConstraint(
            joint_name=name, position=value, tolerance_above=.005, tolerance_below=.005, weight=1.))
    goal = MoveGroup.Goal()
    req = goal.request
    req.group_name = side + '_arm'
    req.pipeline_id = 'ompl'
    req.start_state.is_diff = True
    req.goal_constraints = [constraints]
    req.num_planning_attempts = 4
    req.allowed_planning_time = 5.
    req.max_velocity_scaling_factor = req.max_acceleration_scaling_factor = speed
    goal.planning_options.planning_scene_diff.is_diff = True
    goal.planning_options.planning_scene_diff.robot_state.is_diff = True
    return goal


def read(node, side):
    result = []
    def receive(msg):
        pos = dict(zip(msg.name, msg.position))
        if all(k in pos and math.isfinite(pos[k]) for k in names(side)):
            result[:] = [round(math.degrees(pos[k]), 3) for k in names(side)]
    node.create_subscription(JointState, '/joint_states', receive, qos_profile_sensor_data)
    deadline = time.monotonic()+6
    while not result and time.monotonic()<deadline:
        rclpy.spin_once(node, timeout_sec=.1)
    if not result:
        raise RuntimeError('Could not read all seven joints')
    print(json.dumps(result), flush=True)


def execute(node, goal, cancelled):
    client = ActionClient(node, MoveGroup, '/move_action')
    if not client.wait_for_server(timeout_sec=6):
        raise RuntimeError('MoveIt /move_action unavailable')
    if cancelled():raise RuntimeError("姿勢指令を中止しました。")
    pending = client.send_goal_async(goal)
    rclpy.spin_until_future_complete(node,pending,timeout_sec=6)
    if not pending.done() or not pending.result().accepted:
        raise RuntimeError('MoveIt did not accept the posture goal')
    handle = pending.result()
    result = handle.get_result_async()
    try:
        deadline = time.monotonic()+65
        while not result.done() and time.monotonic()<deadline:
            if cancelled():
                raise KeyboardInterrupt()
            rclpy.spin_once(node,timeout_sec=.1)
        if not result.done():
            raise TimeoutError('Posture timed out')
    except (KeyboardInterrupt,TimeoutError):
        if rclpy.ok():
            rclpy.spin_until_future_complete(node,handle.cancel_goal_async(),timeout_sec=2)
        raise RuntimeError('姿勢指令を中止しました。') from None
    code = result.result().result.error_code.val
    if code != MoveItErrorCodes.SUCCESS:
        raise RuntimeError(f'MoveIt error {code}')
    print('姿勢を適用しました。', flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('side',choices=['left','right'])
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--read',action='store_true')
    action.add_argument('--degrees',nargs=7,type=float)
    parser.add_argument('--speed',type=float,default=.25)
    args=parser.parse_args()
    if not 0 < args.speed <= 1:parser.error('speed must be in (0,1]')
    # Let Python handle SIGINT so an active MoveIt goal can be cancelled first.
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node=rclpy.create_node('happy_posture_client')
    interrupted = False
    def stop(signum, frame):
        nonlocal interrupted
        interrupted = True
    signal.signal(signal.SIGINT, stop)
    try:
        if args.read:read(node,args.side)
        else:execute(node,goal_for(args.side,args.degrees,args.speed),lambda:interrupted)
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    try:main()
    except (RuntimeError,ValueError,TimeoutError) as exc:raise SystemExit(str(exc))
