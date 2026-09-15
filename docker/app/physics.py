"""Small position servo for the pinned OpenArm v1 MJCF, independent of ROS."""
import os
import mujoco
import numpy as np


class Simulation:
    def __init__(self, path=None):
        self.model = mujoco.MjModel.from_xml_path(path or os.environ.get('OPENARM_SCENE', os.environ['OPENARM_MODEL']))
        self.model.opt.timestep = 0.002
        self.model.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        self.data = mujoco.MjData(self.model)
        m = self.model
        self.joint_ids = np.array([j for j in range(m.njnt) if m.jnt_type[j] in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE) and (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT,j) or '').startswith('openarm_')],dtype=int)
        self.names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j)
                      for j in self.joint_ids]
        self.index = {name: j for j, name in enumerate(self.names)}
        self.qadr = m.jnt_qposadr[self.joint_ids].copy()
        self.dadr = m.jnt_dofadr[self.joint_ids].copy()
        self.act_joint = np.array([list(self.joint_ids).index(int(j)) for j in m.actuator_trnid[:, 0]])
        if (np.any(m.actuator_trntype != mujoco.mjtTrn.mjTRN_JOINT)
                or not np.allclose(m.actuator_gear[:, 0], 1)):
            raise ValueError('Unsupported actuator transmission')
        self.position_act = m.actuator_biastype == mujoco.mjtBias.mjBIAS_AFFINE
        self.kp = np.array([250.0 if 'finger' in n else 80.0 for n in self.names])
        self.kd = np.array([5.0 if 'finger' in n else 8.0 for n in self.names])
        self.speed = np.array([0.02 if 'finger' in n else 0.5 for n in self.names])
        self.reset()

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.target = self.data.qpos[self.qadr].copy()
        self.reference = self.target.copy()
        mujoco.mj_forward(self.model, self.data)

    def command(self, names, positions):
        if not names or len(names) != len(positions) or len(set(names)) != len(names):
            raise ValueError('Provide nonempty, unique names with matching positions')
        next_target = self.target.copy()
        for name, value in zip(names, positions):
            if name not in self.index or not np.isfinite(value):
                raise ValueError(f'Unknown joint or nonfinite position: {name}')
            j = self.index[name]
            if self.model.jnt_limited[self.joint_ids[j]]:
                lo, hi = self.model.jnt_range[self.joint_ids[j]]
                if not lo - 1e-5 <= value <= hi + 1e-5:
                    raise ValueError(f'{name}: {value} outside [{lo}, {hi}]')
                value = float(np.clip(value, lo, hi))
            next_target[j] = value
        self.target = next_target

    def step(self):
        m, d = self.model, self.data
        limit = self.speed * m.opt.timestep
        self.reference += np.clip(self.target - self.reference, -limit, limit)
        # Feedforward bias compensation plus PD; MuJoCo still integrates dynamics.
        torque = (self.kp * (self.reference - d.qpos[self.qadr])
                  - self.kd * d.qvel[self.dadr] + d.qfrc_bias[self.dadr])
        for a, j in enumerate(self.act_joint):
            if self.position_act[a]:
                control = self.reference[j]
            else:
                control = torque[j]
                force_range = m.actuator_forcerange[a] if m.actuator_forcelimited[a] else (-20, 20)
                control = np.clip(control, *force_range)
            if m.actuator_ctrllimited[a]:
                control = np.clip(control, *m.actuator_ctrlrange[a])
            d.ctrl[a] = control
        mujoco.mj_step(m, d)
        if not np.all(np.isfinite(d.qpos)) or not np.all(np.isfinite(d.qvel)):
            raise RuntimeError('Nonfinite simulation state')
