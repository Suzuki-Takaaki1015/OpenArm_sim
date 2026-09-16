"""Official OpenArm v1.1 bracket geometry plus an explicit project installation datum.
CAD coordinates are mm; runtime coordinates are metres. See CAMERA_MOUNT.md.
"""
import json,math,os
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


def exposed_v2_pedestal(source, destination):
    """Remove the connected chest shell from the pinned binary STL, keeping the pedestal.

    Work in source millimetres. Select by bounds, not triangle order; fail if the
    upstream topology changes. The original vendor asset remains untouched.
    """
    raw=Path(source).read_bytes()
    dtype=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    count=int.from_bytes(raw[80:84],'little')
    if len(raw)!=84+50*count:raise ValueError('Expected pinned binary pedestal STL')
    triangles=np.frombuffer(raw,dtype=dtype,offset=84)
    vertices,inverse=np.unique(triangles['vertices'].reshape(-1,3),axis=0,return_inverse=True)
    faces=inverse.reshape(-1,3);parents=list(range(len(vertices)))
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for a,b,c in faces:
        root=find(a);parents[find(b)]=root;parents[find(c)]=root
    labels=np.array([find(i) for i in faces[:,0]])
    shells=[];columns=[]
    for label in np.unique(labels):
        points=triangles['vertices'][labels==label].reshape(-1,3)
        low,high=points.min(0),points.max(0)
        if np.allclose(low,[-84.7501,-80,613],atol=.02) and np.allclose(high,[65.2499,80,773],atol=.02):
            shells.append(label)
        if np.allclose(low,[-30,-30,8],atol=.02) and np.allclose(high,[30,30,758],atol=.02):
            columns.append(label)
    if len(shells)!=1:raise ValueError('Pinned v2 chest shell cannot be identified safely')
    if len(columns)!=1:raise ValueError('Pinned v2 column cannot be identified safely')
    def with_normals(selected):
        # Pinned v2 STL stores zero normals; OGRE renders it black whereas
        # MuJoCo regenerates normals. Preserve every vertex and face winding.
        selected=selected.copy()
        vertices=selected['vertices'].astype(float)
        normals=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
        lengths=np.linalg.norm(normals,axis=1)
        selected['normal']=normals/np.where(lengths>0,lengths,1)[:,None]
        return selected
    column=with_normals(triangles[labels==columns[0]])
    column_path=Path(destination).with_name('camera_exposed_column.stl')
    column_path.write_bytes(raw[:80]+len(column).to_bytes(4,'little')+column.tobytes())
    reference=triangles[labels!=shells[0]]
    Path(destination).with_name('camera_exposed_support_reference.stl').write_bytes(
        raw[:80]+len(reference).to_bytes(4,'little')+reference.tobytes())
    kept=with_normals(triangles[(labels!=shells[0]) & (labels!=columns[0])])
    Path(destination).write_bytes(raw[:80]+len(kept).to_bytes(4,'little')+kept.tobytes())

def prepare_robot(path):
    cfg=config();d=definition(cfg);tree=E.parse(path);root=tree.getroot();assets=root.find('asset')
    body=root.find("worldbody/body[@name='openarm_body_link0']")
    if body is None:raise ValueError('Expected pinned OpenArm v1 body')
    # Official bracket installation requires removal of both chest covers (issue 307).
    for g in list(body.findall('geom')):
        if g.get('mesh')=='body_link0_5.obj' or (g.get('name') or '').startswith('camera_mount_'):body.remove(g)
    for a in list(assets.findall('mesh')):
        if (a.get('name') or '').startswith('camera_mount_'):assets.remove(a)
    if os.environ.get('OPENARM_VERSION','1')=='2':
        visual=assets.find("mesh[@name='body_link0']")
        if visual is None:raise ValueError('Expected pinned v2 pedestal visual')
        meshdir=Path(root.find('compiler').get('meshdir'))
        source=meshdir/'visual/body/body_link0.stl'
        output=Path(path).with_name('camera_exposed_pedestal.stl')
        exposed_v2_pedestal(source,output)
        visual.set('file',str(output))
        # Split only the existing visual triangles; retain collision and inertia.
        E.SubElement(assets,'mesh',name='camera_mount_column_visual',
                     file=str(output.with_name('camera_exposed_column.stl')),scale='0.001 0.001 0.001')
        E.SubElement(body,'geom',name='camera_mount_column_visual',mesh='camera_mount_column_visual',
                     type='mesh',**{'class':'visual','material':'metal_silver','rgba':'.796 .796 .796 1'})
        collision=assets.find("mesh[@name='body_link0_symp']")
        if collision is None:raise ValueError('Expected pinned v2 pedestal collision')
        collision.set('file',str(ASSETS/'pedestal_collision.obj'))
        collision.set('scale','1 1 1')
    else:
        for g in body.findall('geom'):
            if g.get('mesh')=='body_link0_3.obj' and g.get('class')=='visual':
                g.set('material','metal_silver')
    old=assets.find("mesh[@name='body_collision']")
    if old is not None:
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
    if os.environ.get('OPENARM_VERSION','1')=='2':
        # MuJoCo auto inertia depends on each mesh's convex hull. Splitting the
        # visual must not change the original combined support's mass/inertia.
        reference=E.fromstring(E.tostring(root))
        rb=reference.find("worldbody/body[@name='openarm_body_link0']")
        for item in list(rb):
            if item.tag=='inertial' or item.get('name')=='camera_mount_column_visual':rb.remove(item)
        reference.find("asset/mesh[@name='body_link0']").set('file',
            str(Path(path).with_name('camera_exposed_support_reference.stl')))
        original=mujoco.MjModel.from_xml_string(E.tostring(reference,encoding='unicode'))
        bid=mujoco.mj_name2id(original,mujoco.mjtObj.mjOBJ_BODY,'openarm_body_link0')
        for item in list(body.findall('inertial')):body.remove(item)
        E.SubElement(body,'inertial',mass=vec([original.body_mass[bid]]),
            pos=vec(original.body_ipos[bid]),quat=vec(original.body_iquat[bid]),
            diaginertia=vec(original.body_inertia[bid]))
    tree.write(path,encoding='unicode')
