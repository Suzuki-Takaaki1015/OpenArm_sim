"""Small position servo for the pinned OpenArm v1 MJCF, independent of ROS."""
import os
import mujoco
import numpy as np


class Simulation:
    def __init__(self, path=None):
        self.model = mujoco.MjModel.from_xml_path(path or os.environ.get('OPENARM_SCENE', os.environ['OPENARM_MODEL']))
        self.model.opt.timestep = 0.002
        self.model.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        # Official OpenArm v2 uses this contact setup to prevent jaw creep.
        self.model.opt.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
        self.model.opt.impratio = 10
        for g in range(self.model.ngeom):
            body = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, self.model.geom_bodyid[g]) or ''
            if 'finger' in body and self.model.geom_contype[g]:
                self.model.geom_condim[g] = 4
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
        # SI units: arm servo Nm/rad; finger servo N/m. The simplified MJCF
        # has slide joints, not the physical motor/linkage transmission.
        self.kp = np.array([1500.0 if 'finger' in n else 80.0 for n in self.names])
        self.kd = np.array([10.0 if 'finger' in n else 8.0 for n in self.names])
        self.speed = np.array([0.02 if 'finger' in n else 1.0 for n in self.names])
        self.position_act = np.ones(m.nu, dtype=bool)
        self.motor_act = np.ones(m.nu, dtype=bool)
        for a, j in enumerate(self.act_joint):
            finger = 'finger' in self.names[j]
            if finger:
                # Conservative 15 N/jaw; not the upstream 333 N nor Nm.
                force = 15.0
            else:
                # Official DM8009P / DM4340 / DM4310 peak motor limits.
                number = int(self.names[j].rsplit('joint', 1)[1])
                force = 40.0 if number <= 2 else 27.0 if number <= 4 else 7.0
            m.actuator_gaintype[a] = mujoco.mjtGain.mjGAIN_FIXED
            m.actuator_biastype[a] = mujoco.mjtBias.mjBIAS_AFFINE
            m.actuator_gainprm[a, 0] = self.kp[j]
            m.actuator_biasprm[a, :3] = [0, -self.kp[j], -self.kd[j]]
            m.actuator_forcelimited[a] = 1
            m.actuator_forcerange[a] = [-force, force]
            m.actuator_ctrllimited[a] = 0
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
        for a, j in enumerate(self.act_joint):
            control = self.reference[j]
            if self.motor_act[a]:
                control += d.qfrc_bias[self.dadr[j]] / self.kp[j]
            if m.actuator_ctrllimited[a]:
                control = np.clip(control, *m.actuator_ctrlrange[a])
            d.ctrl[a] = control
        mujoco.mj_step(m, d)
        if not np.all(np.isfinite(d.qpos)) or not np.all(np.isfinite(d.qvel)):
            raise RuntimeError('Nonfinite simulation state')
