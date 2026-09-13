"""MuJoCo physics endpoint for the ros2_control topic hardware interface."""
import argparse
import os
import time
from contextlib import nullcontext

import rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger

from physics import Simulation


class Bridge(Node):
    def __init__(self):
        super().__init__('openarm_mujoco')
        self.sim = Simulation()
        self.states = self.create_publisher(JointState, '/mujoco/joint_states', 10)
        self.clock = self.create_publisher(Clock, '/clock', 10)
        self.create_subscription(JointState, '/mujoco/joint_commands', self.command, 10)
        # Restart the stack to reset time; controller trajectories must reset together.
        self.get_logger().info('Ready: /mujoco/joint_commands; ' + ', '.join(self.sim.names))

    def command(self, msg):
        try:
            if any(abs(v) > 0 for v in msg.velocity) or any(abs(v) > 0 for v in msg.effort):
                raise ValueError('Only name and position are accepted')
            self.sim.command(msg.name, msg.position)
        except ValueError as exc:
            self.get_logger().warning(f'Rejected command: {exc}', throttle_duration_sec=5.0)

    def reset(self, request, response):
        self.sim.reset()
        response.success = True
        response.message = 'Reset; simulation clock returned to zero'
        return response

    def publish_state(self):
        ns = round(self.sim.data.time * 1_000_000_000)
        clock = Clock()
        clock.clock.sec, clock.clock.nanosec = divmod(ns, 1_000_000_000)
        self.clock.publish(clock)
        msg = JointState()
        msg.header.stamp = clock.clock
        msg.name = self.sim.names
        msg.position = self.sim.data.qpos[self.sim.qadr].tolist()
        msg.velocity = self.sim.data.qvel[self.sim.dadr].tolist()
        msg.effort = self.sim.data.qfrc_actuator[self.sim.dadr].tolist()
        self.states.publish(msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gui', action='store_true')
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = Bridge()
    viewer_context = nullcontext(None)
    if args.gui or os.environ.get('OPENARM_GUI', '').lower() == 'true':
        import mujoco.viewer
        viewer_context = mujoco.viewer.launch_passive(node.sim.model, node.sim.data, show_left_ui=False, show_right_ui=False)
    try:
        with viewer_context as viewer:
            if viewer:
                viewer.cam.lookat[:] = [0, 0, 0.43]
                viewer.cam.distance = 1.5
                viewer.cam.azimuth = 135
                viewer.cam.elevation = -20
            tick = 0
            deadline = time.monotonic()
            while rclpy.ok() and (viewer is None or viewer.is_running()):
                rclpy.spin_once(node, timeout_sec=0)
                node.sim.step()
                tick += 1
                if tick % 5 == 0:
                    node.publish_state()
                if viewer and tick % 16 == 0:
                    viewer.sync()
                deadline += node.sim.model.opt.timestep
                delay = deadline - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -0.1:
                    deadline = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
