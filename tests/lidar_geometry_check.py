"""Run with the container's MuJoCo/numpy; deterministic geometry regressions."""
import sys
sys.path.insert(0,'/opt/openarm/app')
import mujoco,numpy as np
from lidar_scan import directions,scan
r=directions(800,0);r1=directions(800,1)
assert np.allclose(np.linalg.norm(r,axis=1),1)
el=np.degrees(np.arcsin(r[:,2]));assert el.min()>=-7 and el.max()<=52
assert not np.allclose(r,r1)
m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="box" pos="2 0 0" size=".1 1 1"/><geom type="box" pos="1 0 0" size=".1 1 1" group="3"/></worldbody></mujoco>')
d=mujoco.MjData(m);mujoco.mj_forward(m,d)
p,ids=scan(mujoco,m,d,np.zeros(3),np.eye(3),np.array([[1.,0,0]]),-1,.1,40)
assert np.allclose(p,[[1.9,0,0]],atol=1e-6),(p,ids)
m.geom_group[0]=5
p,ids=scan(mujoco,m,d,np.zeros(3),np.eye(3),np.array([[1.,0,0]]),-1,.1,40)
assert len(p)==0,'Hidden geometry returned'
m.geom_group[0]=0
p,ids=scan(mujoco,m,d,np.zeros(3),np.eye(3),np.array([[1.,0,0]]),-1,2.,40)
assert len(p)==0,'Minimum range not enforced'
print('PASS angular coverage, nonrepeating samples, ray intersection, collision proxy exclusion, hidden geometry, minimum range')
