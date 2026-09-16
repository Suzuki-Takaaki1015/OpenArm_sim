"""Physics-thread scene transactions; validate on a private model before mutation."""
import copy
import os
import time
from types import SimpleNamespace

import mujoco
import numpy as np
from action_msgs.msg import GoalStatusArray
from control_msgs.msg import JointTrajectoryControllerState
from trajectory_msgs.msg import JointTrajectory
from rclpy.qos import QoSProfile, DurabilityPolicy
from dynamic_objects import DynamicObjects
from environment_assets import ITEMS
from scene_objects import OBJECTS
from scene_presets import validate


class Presets:
    def __init__(self, bridge):
        self.bridge = bridge
        self.controllers = {}
        self.goals = {}
        self.trajectory_until = {}
        for side in ('left', 'right'):
            for part in ('arm', 'gripper'):
                name = side + '_' + part + '_controller'
                bridge.create_subscription(JointTrajectory, '/' + name + '/joint_trajectory',
                    lambda msg, name=name: self.trajectory(name, msg), 10)
                bridge.create_subscription(JointTrajectoryControllerState, '/' + name + '/controller_state',
                    lambda msg, name=name: self.state(name, msg), 1)
                bridge.create_subscription(GoalStatusArray, '/' + name + '/follow_joint_trajectory/_action/status',
                    lambda msg, name=name: self.goals.update({name: any(s.status in (1, 2, 3) for s in msg.status_list)}),
                    QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

    def trajectory(self, name, msg):
        if not msg.points:
            return  # An ignored/invalid message must not clear an existing guard.
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        duration = msg.points[-1].time_from_start
        self.trajectory_until[name] = max(self.trajectory_until.get(name, 0), max(stamp, self.bridge.sim.data.time) + duration.sec + duration.nanosec * 1e-9)

    def state(self, name, msg):
        reference = msg.reference
        moving = any(abs(x) > .001 for x in reference.velocities)
        self.controllers[name] = (time.monotonic(), moving)

    def idle(self):
        sim = self.bridge.sim
        if len(self.controllers) != 4 or any(time.monotonic()-t > 2 or moving for t, moving in self.controllers.values()):
            raise ValueError('コントローラ状態が未確認・古い、または軌道実行中です。腕を停止して再試行してください')
        if any(t > sim.data.time for t in self.trajectory_until.values()) or any(self.goals.values()) or np.max(np.abs(sim.data.qvel[sim.dadr])) > .02 or np.max(np.abs(sim.target-sim.reference)) > .001:
            raise ValueError('軌道実行中または腕が動いています。停止後に復元してください')

    def capture(self):
        b = self.bridge
        return dict(schema='openarm.scene', version=1, robot_model=os.environ.get('OPENARM_VERSION', '1'),
            tables={t['id']: dict(enabled=b.obstacles_enabled, pose=t['position']+[1, 0, 0, 0]) for t in OBJECTS},
            objects={k: dict(enabled=b.objects.active[k], pose=b.objects.pose(k).tolist(), support=b.objects.supports[k]) for k in ITEMS})

    def backup(self):
        m, d = self.bridge.sim.model, self.bridge.sim.data
        return ({n: getattr(m, n).copy() for n in ('geom_contype', 'geom_conaffinity', 'geom_rgba', 'geom_matid', 'body_contype', 'body_conaffinity', 'body_gravcomp')},
                {n: getattr(d, n).copy() for n in ('qpos', 'qvel', 'qacc_warmstart', 'mocap_pos', 'mocap_quat')},
                self.bridge.objects.active.copy(), self.bridge.objects.supports.copy(), self.bridge.obstacles_enabled)

    def restore(self, state):
        b = self.bridge
        for target, arrays in ((b.sim.model, state[0]), (b.sim.data, state[1])):
            for name, values in arrays.items():
                getattr(target, name)[:] = values
        b.objects.active, b.objects.supports, b.obstacles_enabled = state[2:]
        mujoco.mj_forward(b.sim.model, b.sim.data)

    @staticmethod
    def populate(objects, document):
        m, d = objects.sim.model, objects.sim.data
        for key in ITEMS:
            objects.masks(key, False)
        for table in OBJECTS:
            g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, table['id'])
            if g < 0:
                raise ValueError('Table geometry missing; rebuild image')
            enabled = document['tables'][table['id']]['enabled']
            m.geom_contype[g] = m.geom_conaffinity[g] = int(enabled)
            m.geom_rgba[g] = table['rgba'] if enabled else [0, 0, 0, 0]
        # Parents before dependants, independent of JSON key order.
        for key in sorted(ITEMS, key=lambda k: not ITEMS[k].get('furniture', False)):
            state = document['objects'][key]
            objects.write_pose(key, state['pose'])
            objects.masks(key, state['enabled'])
            objects.active[key] = state['enabled']
            objects.supports[key] = state['support']
        for bid in set(int(m.geom_bodyid[g]) for g in range(m.ngeom)):
            gs = np.where(m.geom_bodyid == bid)[0]
            m.body_contype[bid] = np.bitwise_or.reduce(m.geom_contype[gs], initial=0)
            m.body_conaffinity[bid] = np.bitwise_or.reduce(m.geom_conaffinity[gs], initial=0)
        mujoco.mj_forward(m, d)

    def apply(self, document):
        b = self.bridge
        document = validate(document, ITEMS, OBJECTS, os.environ.get('OPENARM_VERSION', '1'))
        self.idle()
        # Trial uses current robot joints but never changes live physics or publishes.
        trial = SimpleNamespace(model=copy.copy(b.sim.model), data=None)
        trial.data = mujoco.MjData(trial.model)
        mujoco.mj_copyData(trial.data, trial.model, b.sim.data)
        objects = DynamicObjects(trial)
        self.populate(objects, document)
        scene_geoms = {g for k in ITEMS if objects.active[k] for g in objects.geoms(k)}
        scene_geoms.update(mujoco.mj_name2id(trial.model, mujoco.mjtObj.mjOBJ_GEOM, t['id']) for t in OBJECTS)
        if any(c.dist < -.003 and (int(c.geom1) in scene_geoms or int(c.geom2) in scene_geoms) for c in trial.data.contact):
            raise ValueError('復元配置がロボット・物体と重なります。現在のシーンは変更していません')
        for key, spec in ITEMS.items():
            if objects.active[key] and spec.get('furniture') and objects.collision(key):
                raise ValueError(key + ': furniture collision; scene unchanged')
        before = self.backup()
        try:
            self.populate(b.objects, document)
            b.obstacles_enabled = all(t['enabled'] for t in document['tables'].values())
        except Exception:
            self.restore(before)
            raise
        return 'シーンを復元しました（物理状態からMoveItへ同期します）'
