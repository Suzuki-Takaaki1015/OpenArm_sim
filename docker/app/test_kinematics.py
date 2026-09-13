"""Compare URDF forward kinematics against MuJoCo at deterministic joint samples."""
import os
from pathlib import Path
import xml.etree.ElementTree as E
import numpy as np
import mujoco
def axis_rotation(v):
    angle=np.linalg.norm(v)
    if angle<1e-15:return np.eye(3)
    a=v/angle
    cross=np.array([[0,-a[2],a[1]],[a[2],0,-a[0]],[-a[1],a[0],0]])
    return np.eye(3)+np.sin(angle)*cross+(1-np.cos(angle))*(cross@cross)
def euler_rotation(v):
    return axis_rotation(np.array([0,0,v[2]]))@axis_rotation(np.array([0,v[1],0]))@axis_rotation(np.array([v[0],0,0]))
m=mujoco.MjModel.from_xml_path(os.environ['OPENARM_MODEL']);d=mujoco.MjData(m)
root=E.parse(Path(os.environ.get('OPENARM_CONFIG','/opt/openarm/config'))/'openarm.urdf').getroot()
joints=root.findall('joint');rng=np.random.default_rng(7);error=0.
for _ in range(12):
    for j in range(m.njnt):d.qpos[m.jnt_qposadr[j]]=rng.uniform(*m.jnt_range[j])
    mujoco.mj_forward(m,d);poses={'world':np.eye(4)}
    for joint in joints:
        parent=joint.find('parent').get('link');child=joint.find('child').get('link');origin=joint.find('origin')
        transform=np.eye(4);transform[:3,3]=np.fromstring(origin.get('xyz'),sep=' ')
        transform[:3,:3]=euler_rotation(np.fromstring(origin.get('rpy'),sep=' '))
        movement=np.eye(4)
        if joint.get('type')!='fixed':
            j=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,joint.get('name'));q=d.qpos[m.jnt_qposadr[j]]
            axis=np.fromstring(joint.find('axis').get('xyz'),sep=' ')
            if joint.get('type')=='prismatic':movement[:3,3]=axis*q
            else:movement[:3,:3]=axis_rotation(axis*q)
        poses[child]=poses[parent]@transform@movement
        b=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,child)
        error=max(error,float(np.max(abs(poses[child][:3,3]-d.xpos[b]))),float(np.max(abs(poses[child][:3,:3]-d.xmat[b].reshape(3,3)))))
assert error<1e-8,error
print('PASS: URDF / MuJoCo transforms match at 12 random poses; max error',error)
