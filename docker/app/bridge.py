"""MuJoCo physics endpoint for the ros2_control topic hardware interface."""
import argparse
import os
import time
import json
from std_msgs.msg import String
from dynamic_objects import DynamicObjects
from environment_assets import ITEMS
from contextlib import nullcontext
import rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger, SetBool
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import ParameterType
import mujoco
from scene_objects import OBJECTS
from physics import Simulation

class Bridge(Node):
    def __init__(self):
        super().__init__('openarm_mujoco')
        self.sim = Simulation()
        self.objects = DynamicObjects(self.sim)
        self.obstacles_enabled = False
        self.performance = {"real_time_factor": 0.0}
        self.snapshot_pub = self.create_publisher(String, "/openarm/sim_state", 2)
        self.create_service(Trigger, "/openarm/scene/status", self.scene_status)
        for key in ITEMS:
            self.create_service(SetParametersAtomically, f"/openarm/objects/{key}/place", lambda req,res,key=key: self.place_object(key,req,res))
            self.create_service(SetBool, f"/openarm/objects/{key}/set_enabled", lambda req,res,key=key: self.set_object(key,req,res))
            self.create_service(Trigger, f"/openarm/objects/{key}/reposition", lambda req,res,key=key: self.reposition_object(key,req,res))
        self.create_service(SetBool, '/openarm/set_obstacles', self.set_obstacles)
        self.states = self.create_publisher(JointState, '/mujoco/joint_states', 10)
        self.clock = self.create_publisher(Clock, '/clock', 10)
        self.create_subscription(JointState, '/mujoco/joint_commands', self.command, 1)
        # Restart the stack to reset time; controller trajectories must reset together.
        self.get_logger().info('Ready: /mujoco/joint_commands; ' + ', '.join(self.sim.names))
    def scene_status(self, request, response):
        response.success = True
        response.message = json.dumps({'obstacles':self.obstacles_enabled,'objects':self.objects.active,'performance':self.performance})
        return response
    def set_object(self, key, request, response):
        try:
            if request.data and not self.obstacles_enabled:
                raise ValueError('Enable the table first')
            self.objects.set_enabled(key, request.data)
            response.success = True
            response.message = f'{key}: '+('placed' if request.data else 'removed')
        except ValueError as exc:
            response.success = False; response.message = str(exc)
        return response
    def place_object(self,key,request,response):
        try:
            if not self.obstacles_enabled:raise ValueError('Enable the table first')
            values={p.name:p.value.double_value for p in request.parameters if p.value.type==ParameterType.PARAMETER_DOUBLE}
            if len(request.parameters)!=3 or set(values)!={'x','y','yaw'}:raise ValueError('Provide exactly three DOUBLE parameters: x, y, yaw (radians)')
            self.objects.set_enabled(key,True,reposition=True,pose=(values['x'],values['y'],values['yaw']))
            response.result.successful=True;response.result.reason=f'{key}: placed at specified position'
        except ValueError as exc:response.result.successful=False;response.result.reason=str(exc)
        return response

    def reposition_object(self, key, request, response):
        try:
            if not self.obstacles_enabled: raise ValueError('Enable the table first')
            self.objects.set_enabled(key, True, reposition=True)
            response.success=True;response.message=f'{key}: repositioned'
        except ValueError as exc:response.success=False;response.message=str(exc)
        return response
    def snapshot(self):
        msg=String()
        msg.data=json.dumps({'time':self.sim.data.time,'qpos':self.sim.data.qpos.tolist(),
                             'obstacles':self.obstacles_enabled,'objects':self.objects.snapshot()})
        self.snapshot_pub.publish(msg)
    def set_obstacles(self, request, response):
        if not request.data and any(self.objects.active.values()):
            response.success=False;response.message='Remove the grasp objects before removing their table'
            return response
        if request.data == self.obstacles_enabled:
            response.success = True
            response.message = 'on' if request.data else 'off'
            return response
        m, d = self.sim.model, self.sim.data
        ids = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, obj['id']) for obj in OBJECTS]
        if any(g < 0 for g in ids):
            response.success = False
            response.message = 'Obstacle geometry missing; rebuild the image'
            return response
        def refresh_contact_masks():
            for bid in set(int(m.geom_bodyid[g]) for g in ids):
                mask = affinity = 0
                for g in range(m.ngeom):
                    if m.geom_bodyid[g] == bid:
                        mask |= int(m.geom_contype[g])
                        affinity |= int(m.geom_conaffinity[g])
                m.body_contype[bid] = mask
                m.body_conaffinity[bid] = affinity
        # Before enabling, reject obstacles intersecting the current robot pose.
        for g, obj in zip(ids, OBJECTS):
            m.geom_contype[g] = m.geom_conaffinity[g] = int(request.data)
        refresh_contact_masks()
        mujoco.mj_forward(m, d)
        intersecting = request.data and any(
            (int(c.geom1) in ids) != (int(c.geom2) in ids)
            and c.dist < -0.001 for c in d.contact)
        if intersecting:
            for g in ids: m.geom_contype[g] = m.geom_conaffinity[g] = 0
            refresh_contact_masks()
            mujoco.mj_forward(m, d)
            response.success = False
            response.message = 'Obstacle overlaps robot; move robot away before enabling'
            return response
        for g, obj in zip(ids, OBJECTS):
            m.geom_rgba[g] = obj['rgba'] if request.data else [0,0,0,0]
        self.obstacles_enabled = request.data
        response.success = True
        response.message = 'on' if request.data else 'off'
        return response
    def command(self, msg):
        try:
            if any(abs(v) > 0 for v in msg.velocity) or any(abs(v) > 0 for v in msg.effort):
                raise ValueError('Only name and position are accepted')
            self.sim.command(msg.name, msg.position)
        except ValueError as exc:
            self.get_logger().warning(f'Rejected command: {exc}', throttle_duration_sec=5.0)
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
            next_frame = time.monotonic()
            perf_wall = time.monotonic()
            perf_sim = node.sim.data.time
            tick = 0
            deadline = time.monotonic()
            while rclpy.ok() and (viewer is None or viewer.is_running()):
                rclpy.spin_once(node, timeout_sec=0)
                node.sim.step()
                tick += 1
                if tick % 5 == 0:
                    node.publish_state()
                if tick % 500 == 0:
                    now = time.monotonic()
                    node.performance['real_time_factor'] = (node.sim.data.time-perf_sim)/max(now-perf_wall,1e-6)
                    perf_wall,perf_sim = now,node.sim.data.time
                if tick % 100 == 0:
                    node.snapshot()
                if viewer and time.monotonic() >= next_frame:
                    viewer.sync()
                    next_frame = time.monotonic() + 1.0 / float(os.environ.get('OPENARM_VIEWER_FPS','60'))
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
