"""Compose both LiDAR variants from the generated v2 arm and the CAD chassis."""
from pathlib import Path
import copy,shutil,math
import xml.etree.ElementTree as E
import numpy as np
from mobile_camera_datum import mobile_d435
from mujoco import mju_mat2Quat
from model_transforms import quaternion_to_rpy
ASSETS=Path('/opt/happy/assets')
ROOT=Path('/opt/openarm/models'); CFG=Path('/opt/openarm/config')
OUT=ROOT/'mobile';OUT.mkdir(exist_ok=True);shutil.copytree(CFG/'v2',CFG/'mobile',dirs_exist_ok=True)
offset=np.array([.031037977,.002423205,.050204697])
laser=[.155395,.002407,.023]  # provisional scan plane in CAD housing; x points forward
def vec(x):return ' '.join(str(float(v)) for v in x)
def origin(e,pos,q=None):
    E.SubElement(e,'origin',xyz=vec(pos),rpy=vec(quaternion_to_rpy(q) if q is not None else [0]*3))
def arr(e,k,default):return np.array(list(map(float,e.get(k,default).split())))
def quat(rotation):
    q = np.zeros(4)
    mju_mat2Quat(q, rotation.ravel())
    return q


for suffix in ('','_no_lidar'):
    name='simulation_robot'+suffix+'.xml';scene='simulation_scene'+suffix+'.xml'
    model=E.parse(ROOT/'v2'/name);r=model.getroot();wb=r.find('worldbody');arm=wb.find("body[@name='openarm_body_link0']")
    ch=E.parse(ASSETS/'chassis.xml');base=ch.find('worldbody/body');base.set('name','base_link')
    # The CAD mount uses 60 mm between arm origins; the pedestal fixture uses 62 mm.
    for side,y in [('left',.030),('right',-.030)]:
        arm.find(f"body[@name='openarm_{side}_base_link']").set('pos',vec([0,y,.698]))
    omit={'openarm_body_link0_visual','openarm_body_link0_collision','camera_mount_column_visual','camera_mount_column'}
    for g in list(arm.findall('geom')):
        if g.get('name') in omit:arm.remove(g)
    camera = mobile_d435()
    mesh_q = quat(camera['mesh_rotation'])
    saddle_q = quat(camera['rotation'])
    for geom in arm.findall('geom'):
        geom_name = geom.get('name','')
        if geom_name.startswith('camera_mount_bracket'):
            geom.attrib.pop('mesh')
            geom.set('type','box')
            geom.set('pos',vec(camera['saddle_center']))
            geom.set('size',vec(camera['saddle_half']))
            geom.set('quat',vec(saddle_q))
        elif geom_name.startswith('camera_mount_d435'):
            geom.set('pos',vec(camera['front']))
            geom.set('quat',vec(mesh_q))
    arm.set('pos',vec(offset));wb.remove(arm);wb.append(base)
    assets={};colors={}
    for a in ch.find('asset'):
        key=a.get('name') or Path(a.get('file')).stem
        a.set('name','hm_'+key)
        if a.tag=='mesh':
            a.set('file',str(ASSETS/'meshes'/a.get('file')));assets[key]=a
        if a.tag=='material':colors[key]=a.get('rgba','0.5 0.5 0.5 1')
        r.find('asset').append(a)
    for d in ch.findall('default/default'):
        d.set('class','hm_'+d.get('class'));r.find('default').append(d)
    # URDF for RViz and MoveIt: base pose tracked via floating virtual joint.
    cfg=CFG/'mobile';ur='openarm'+suffix+'.urdf';sr='openarm'+suffix+'.srdf'
    u=E.parse(CFG/'v2'/ur);robot=u.getroot();s=E.parse(CFG/'v2'/sr);sem=s.getroot()
    robot.find("link[@name='world']").set('name','base_link')
    joint=robot.find("joint[@name='openarm_body_link0_fixed']");joint.find('parent').set('link','base_link')
    joint.find('origin').set('xyz',vec(offset))
    for side,y in [('left',.03),('right',-.03)]:
        robot.find(f"joint[@name='openarm_{side}_base_link_fixed']/origin").set('xyz',vec([0,y,.698]))
    for link in robot.findall('link'):
        for typ in ('visual','collision'):
            for item in list(link.findall(typ)):
                mesh=item.find('geometry/mesh')
                if mesh is not None and mesh.get('filename','').endswith('/chest_mount.obj'):
                    shape=item.find('geometry')
                    shape.remove(mesh)
                    E.SubElement(shape,'box',size=vec(2*camera['saddle_half']))
                    placement=item.find('origin')
                    placement.set('xyz',vec(camera['saddle_center']))
                    placement.set('rpy',vec(quaternion_to_rpy(saddle_q)))
                    continue
                if mesh is not None and Path(mesh.get('filename','')).name in ('d435.obj','d435_collision.obj'):
                    placement=item.find('origin')
                    placement.set('xyz',vec(camera['front']))
                    placement.set('rpy',vec(quaternion_to_rpy(mesh_q)))
                if mesh is not None and any(t in mesh.get('filename','') for t in ('camera_exposed_pedestal','pedestal_collision.obj','camera_exposed_column','column_collision','column.obj')):link.remove(item)
    for e in list(sem.findall('disable_collisions')):
        if 'world' in (e.get('link1'),e.get('link2')):sem.remove(e)
    E.SubElement(sem,'virtual_joint',name='mobile_pose',type='floating',parent_frame='world',child_link='base_link')
    def decorate(body,parent=None):
        n=body.get('name');link=robot.find("link[@name='base_link']") if parent is None else E.SubElement(robot,'link',name=n)
        if parent is not None:
            axle=body.find('joint');moving=axle is not None and axle.get('name','').startswith('axle_')
            j=E.SubElement(robot,'joint',name=axle.get('name') if moving else n+'_fixed',type='continuous' if moving else 'fixed')
            E.SubElement(j,'parent',link=parent);E.SubElement(j,'child',link=n);origin(j,arr(body,'pos','0 0 0'),arr(body,'quat','1 0 0 0'))
            if moving:E.SubElement(j,'axis',xyz=axle.get('axis'))
        for g in body.findall('geom'):
            if g.get('class'):g.set('class','hm_'+g.get('class'))
            if not g.get('mesh'):continue
            key=g.get('mesh');a=assets[key];vis=E.SubElement(link,'visual')
            origin(vis,arr(g,'pos','0 0 0'),arr(g,'quat','1 0 0 0'))
            E.SubElement(E.SubElement(vis,'geometry'),'mesh',filename='file://'+a.get('file'),scale=a.get('scale','1 1 1'))
            mat=g.get('material')
            if mat:E.SubElement(E.SubElement(vis,'material',name='hm_'+mat),'color',rgba=colors[mat]);g.set('material','hm_'+mat)
            g.set('mesh','hm_'+key)
        for b in body.findall('body'):decorate(b,n)
    decorate(base)
    for j in base.iter('joint'):
        if j.get('class'):j.set('class','hm_'+j.get('class'))
    for item in ch.find('actuator'):r.find('actuator').append(item)
    # Conservative lower chassis collision hull, shared by MuJoCo and MoveIt.
    E.SubElement(base,'geom',name='mobile_chassis_collision',type='cylinder',size='.19 .043',pos='0 0 .015',group='3',contype='4',conaffinity='1',rgba='0 0 0 0',mass='0')
    col=E.SubElement(robot.find("link[@name='base_link']"),'collision');origin(col,[0,0,.015]);E.SubElement(E.SubElement(col,'geometry'),'cylinder',radius='.19',length='.086')
    E.SubElement(base,'site',name='utm_scan_origin',pos=vec(laser),size='.001')
    E.SubElement(robot,'link',name='laser');j=E.SubElement(robot,'joint',name='utm_mount',type='fixed');E.SubElement(j,'parent',link='base_link');E.SubElement(j,'child',link='laser');origin(j,laser)
    # D455's CAD face is normal to vehicle +X. Measure its face and midlines
    # in base_link, then apply the nominal optical offsets from _d455.urdf.xacro.
    housing=base.find("geom[@mesh='hm_camera']")
    with Path(assets['camera'].get('file')).open() as mesh_file:
        vertices=np.array([list(map(float,line.split()[1:4])) for line in mesh_file if line.startswith('v ')])
    vertices+=arr(housing,'pos','0 0 0')
    low,high=vertices.min(0),vertices.max(0)
    depth_pos=(low+high)/2
    depth_pos[0]=high[0]-.00465
    depth_pos[1]+=.0475
    for channel,dy,fovy in [('depth',0.,58.),('color',-.059,65.)]:
        E.SubElement(base,'camera',name='d455_'+channel,pos=vec(depth_pos+[0.,dy,0.]),
                     xyaxes='0 -1 0 0 0 1',fovy=str(fovy))
    base.append(arm)
    # v2 meshdir is absolute; remaining relative filenames must resolve as in v2.
    st=E.parse(ROOT/'v2'/scene)
    scene_world=st.find('worldbody')
    for sensor in list(scene_world.findall('camera')):
        if sensor.get('name') in ('d435_color','d435_depth'):
            channel = sensor.get('name').split('_')[1]
            rotation = camera['rotation']
            sensor.set('pos',vec(camera[channel]))
            sensor.set('xyaxes',vec(np.concatenate((-rotation[:, 1], rotation[:, 2]))))
            scene_world.remove(sensor)
            arm.append(sensor)
    model.write(OUT/name)
    floor=st.find('worldbody/geom');floor.set('contype','1');floor.set('conaffinity','2');floor.set('friction','.9 .002 .0001')
    st.write(OUT/scene);u.write(cfg/ur);s.write(cfg/sr)


# The arm-only modes keep their own RViz configuration.
import yaml
app=Path('/opt/openarm/app')
view=yaml.safe_load((app/'openarm.rviz').read_text())
view['Visualization Manager']['Displays'].append({
    'Class':'rviz_default_plugins/LaserScan','Name':'UTM-30LX','Enabled':True,
    'Topic':{'Value':'/scan','Reliability Policy':'Best Effort','Depth':5},
    'Style':'Points','Size (Pixels)':3,'Color Transformer':'FlatColor',
    'Color':'60; 210; 255'})
(app/'mobile.rviz').write_text(yaml.safe_dump(view,sort_keys=False))
