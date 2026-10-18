"""Geometry/state-layout regression for the sensor-only asset selection."""
import os,sys
sys.path.insert(0,'/opt/openarm/app')
import mujoco,numpy as np
from sensor_model import load_sensor_model,ITEMS
from lidar_scan import scan,directions
from ycb_assets import set_visibility
full=mujoco.MjModel.from_xml_path(os.environ['OPENARM_SCENE'])
for enabled in (set(),{'box'}, {'box','bottle'}):
 snapshot={'objects':{k:{'enabled':k in enabled} for k in ITEMS}}
 slim,active=load_sensor_model(snapshot,textures=False)
 assert slim.nq==full.nq and slim.nmocap==full.nmocap
 assert list(slim.jnt_qposadr)==list(full.jnt_qposadr)
 assert [mujoco.mj_id2name(slim,mujoco.mjtObj.mjOBJ_JOINT,i) for i in range(slim.njnt)]==[mujoco.mj_id2name(full,mujoco.mjtObj.mjOBJ_JOINT,i) for i in range(full.njnt)]
 outputs=[]
 for m in (full,slim):
  d=mujoco.MjData(m);m.geom_group[m.geom_group==3]=5
  for key,obj in ITEMS.items():
   for i,g in enumerate(obj['geoms']):
    gid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,f'{obj["id"]}_{i}')
    if gid<0:continue
    set_visibility(m,gid,g,key in enabled)
    m.geom_group[gid]=5 if key not in enabled or g.get('collision',False) else 2
  for key,x in [('box',.4),('bottle',.55)]:
   jid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,ITEMS[key]['id']+'_free')
   adr=m.jnt_qposadr[jid];d.qpos[adr:adr+3]=[x,0,.25]
  mujoco.mj_forward(m,d)
  bid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'mid360s_link')
  exclude=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'mid360s_mount')
  outputs.append(scan(mujoco,m,d,d.xpos[bid],d.xmat[bid].reshape(3,3),directions(800,0),exclude,.1,40)[0])
 np.testing.assert_allclose(outputs[0],outputs[1],rtol=1e-5,atol=1e-6)
 print('PASS sensor layout/rays',sorted(enabled),'bytes',slim.nbuffer,flush=True)
 del slim
