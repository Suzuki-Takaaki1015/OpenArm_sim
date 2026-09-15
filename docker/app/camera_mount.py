"""Official OpenArm v1.1 bracket geometry plus an explicit project installation datum.
CAD coordinates are mm; runtime coordinates are metres. See CAMERA_MOUNT.md.
"""
import json,math
from pathlib import Path
import xml.etree.ElementTree as E
import numpy as np
ASSETS=Path(__file__).with_name('camera_assets')
# STEP M6 axes: (40.334880912903, 0, 15/45); camera rear seat: X-Y=-9.000357133747.
M6_X=0.040334880912903074
REAR_SEAT_Y=0.00900035713374697
CAD_ROTATION=np.array([[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]])

def definition(cfg):
    h=cfg['mount_reference']['m6_axis_height_m']
    if not .650<=h<=.748:raise ValueError('M6 datum outside supported exposed chest-column installation range')
    mount=np.array([.030,-.030,h-M6_X])
    rear=mount+CAD_ROTATION@np.array([0.,REAR_SEAT_Y,.030])
    a=math.pi/4;c=math.cos(a);s=math.sin(a)
    R=np.array([[c,0.,s],[0.,1.,0.],[-s,0.,c]])
    # Official D435 URDF: front-to-depth reference 4.3 mm; depth lateral offset 17.5 mm.
    front=rear+R@np.array([.02505,0.,0.])
    depth=front+R@np.array([-.0043,.0175,0.])
    return dict(mount_position=mount,rear_center=rear,front_center=front,depth_position=depth,
                color_position=depth+R@np.array([0.,.015,0.]),R=R)

def config():
    cfg=json.loads(Path(__file__).with_name('camera_config.json').read_text())
    d=definition(cfg);cfg['position_m']=d['depth_position'].tolist();cfg['rpy_rad']=[0.,math.pi/4,0.]
    cfg['color_offset_m']=[0.,.015,0.]
    return cfg

def prepare_robot(path):
    cfg=config();d=definition(cfg);tree=E.parse(path);root=tree.getroot();assets=root.find('asset')
    body=root.find("worldbody/body[@name='openarm_body_link0']")
    if body is None:raise ValueError('Expected pinned OpenArm v1 body')
    # Official bracket installation requires removal of both chest covers (issue 307).
    for g in list(body.findall('geom')):
        if g.get('mesh')=='body_link0_5.obj' or (g.get('name') or '').startswith('camera_mount_'):body.remove(g)
    for a in list(assets.findall('mesh')):
        if (a.get('name') or '').startswith('camera_mount_'):assets.remove(a)
    old=assets.find("mesh[@name='body_collision']")
    old.set('file',str(ASSETS/'pedestal_collision.obj'));old.set('scale','1 1 1')
    vec=lambda values:' '.join(f'{float(v):.12g}' for v in values)
    def geom(name,file,pos,quat,purpose,color):
        asset='camera_mount_'+name
        E.SubElement(assets,'mesh',name=asset,file=str(ASSETS/file))
        attrs=dict(name=asset,mesh=asset,type='mesh',pos=vec(pos),quat=vec(quat))
        attrs['class']=purpose
        if purpose=='visual':attrs.update(material='metal_silver' if name=='d435' else 'matte_black',rgba=color)
        E.SubElement(body,'geom',**attrs)
    geom('column','column_collision.obj',[0,0,0],[1,0,0,0],'collision','')
    # Axis permutation CAD (X,Y,Z) -> base (Z,X,Y), quaternion wxyz=(.5,-.5,-.5,-.5).
    geom('bracket','chest_mount.obj',d['mount_position'],[.5,-.5,-.5,-.5],'visual','.15 .15 .17 1')
    geom('bracket_collision','chest_mount.obj',d['mount_position'],[.5,-.5,-.5,-.5],'collision','')
    # DAE mesh axes: X right, Y up, Z forward. Official mesh-to-camera rotation Rz(90) Rx(90).
    import mujoco
    mesh_R=d['R']@np.array([[0.,0.,1.],[1.,0.,0.],[0.,1.,0.]])
    q=np.zeros(4);mujoco.mju_mat2Quat(q,mesh_R.ravel())
    geom('d435','d435.obj',d['front_center'],q,'visual','.65 .65 .68 1')
    # Solid conservative housing for contacts and MoveIt, located entirely behind the front face.
    geom('d435_collision','d435_collision.obj',d['front_center'],q,'collision','')
    tree.write(path,encoding='unicode')
