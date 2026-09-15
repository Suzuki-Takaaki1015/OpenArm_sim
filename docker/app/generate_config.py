"""Generate matching MoveIt/URDF models from the pinned MJCF, not another revision."""
import math
import os
from pathlib import Path
import xml.etree.ElementTree as E
import mujoco
import numpy as np
import yaml

OUT = Path(os.environ.get('OPENARM_CONFIG', '/opt/openarm/config'))
SRC = Path(os.environ['OPENARM_MODEL'])
OUT.mkdir(parents=True, exist_ok=True)
m = mujoco.MjModel.from_xml_path(str(SRC))
x = E.parse(SRC).getroot()
robot = E.Element('robot', name='openarm')
E.SubElement(robot, 'link', name='world')
semantic = E.Element('robot', name='openarm')
meshes = {e.get('name'): e for e in x.findall('asset/mesh')}
materials = {e.get('name'): e for e in x.findall('asset/material')}
joint_limits = {}

def vec(v): return ' '.join(f'{n:.12g}' for n in v)
def rpy(q):
    w,x,y,z = map(float,q)
    return [math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)), math.asin(np.clip(2*(w*y-z*x),-1,1)), math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))]
def origin(e, xyz, quat): E.SubElement(e, 'origin', xyz=vec(xyz), rpy=vec(rpy(quat)))
def floats(s): return list(map(float,s.split()))

hardware = E.SubElement(robot, 'ros2_control', name='MujocoTopicSystem', type='system')
h = E.SubElement(hardware, 'hardware')
E.SubElement(h,'plugin').text='joint_state_topic_hardware_interface/JointStateTopicSystem'
for name,value in {'joint_commands_topic':'/mujoco/joint_commands','joint_states_topic':'/mujoco/joint_states','trigger_joint_command_threshold':'-1'}.items():
    E.SubElement(h,'param',name=name).text=value

def body(b,parent):
    name=b.get('name'); bid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,name)
    link=E.SubElement(robot,'link',name=name)
    js=b.findall('joint')
    assert len(js)<=1, 'Multiple joints per body require a different URDF conversion'
    if js:
        jname=js[0].get('name'); j=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,jname)
        assert np.allclose(m.jnt_pos[j],0), 'Nonzero joint anchor not implemented'
        finger='finger' in jname
        effort=20 if finger else (40 if jname.endswith(('joint1','joint2')) else 27 if jname.endswith(('joint3','joint4')) else 7)
        velocity=0.02 if finger else 0.5
        joint=E.SubElement(robot,'joint',name=jname,type='prismatic' if finger else 'revolute')
        E.SubElement(joint,'axis',xyz=vec(m.jnt_axis[j]))
        E.SubElement(joint,'limit',lower=str(m.jnt_range[j,0]),upper=str(m.jnt_range[j,1]),effort=str(effort),velocity=str(velocity))
        ctl=E.SubElement(hardware,'joint',name=jname)
        # Each finger is controlled explicitly. Gripper groups command both fingers.
        E.SubElement(ctl,'command_interface',name='position')
        for state in ('position','velocity','effort'):
            st=E.SubElement(ctl,'state_interface',name=state)
            if state=='position': E.SubElement(st,'param',name='initial_value').text='0.0'
        joint_limits[jname]={'has_velocity_limits':True,'max_velocity':velocity,'has_acceleration_limits':True,'max_acceleration':0.05 if finger else 0.8}
    else: joint=E.SubElement(robot,'joint',name=name+'_fixed',type='fixed')
    E.SubElement(joint,'parent',link=parent);E.SubElement(joint,'child',link=name)
    origin(joint,m.body_pos[bid],m.body_quat[bid])
    E.SubElement(semantic,'disable_collisions',link1=parent,link2=name,reason='Adjacent')
    for geom in b.findall('geom'):
        if geom.get('type')!='mesh': raise ValueError('Unexpected geometry')
        purpose='collision' if geom.get('class')=='collision' else 'visual'
        item=E.SubElement(link,purpose)
        origin(item,floats(geom.get('pos','0 0 0')),floats(geom.get('quat','1 0 0 0')))
        mesh=meshes[geom.get('mesh')]
        geometry=E.SubElement(item,'geometry')
        E.SubElement(geometry,'mesh',filename='file://'+str(SRC.parent/'meshes'/mesh.get('file')),scale=mesh.get('scale','1 1 1'))
        if purpose=='visual':
            material=E.SubElement(item,'material',name=geom.get('material','default'))
            rgba=materials.get(geom.get('material'))
            E.SubElement(material,'color',rgba=rgba.get('rgba','0.6 0.6 0.6 1') if rgba is not None else '0.6 0.6 0.6 1')
    for child in b.findall('body'):body(child,name)

for b in x.findall('worldbody/body'):body(b,'world')
for exclude in x.findall('contact/exclude'):
    E.SubElement(semantic,'disable_collisions',link1=exclude.get('body1'),link2=exclude.get('body2'),reason='MJCF exclusion')

# Closed finger contact and gripper mount pairs follow the official v1 MoveIt SRDF.
for side in ('left','right'):
    fingers=[f'openarm_{side}_left_finger',f'openarm_{side}_right_finger']
    E.SubElement(semantic,'disable_collisions',link1=fingers[0],link2=fingers[1],reason='Gripper contact')
    for finger in fingers:
        E.SubElement(semantic,'disable_collisions',link1=f'openarm_{side}_link7',link2=finger,reason='Gripper mount')

controllers={'controller_manager':{'ros__parameters':{'update_rate':100,'use_sim_time':True,'joint_state_broadcaster':{'type':'joint_state_broadcaster/JointStateBroadcaster'}}}}
moveit_controllers={'controller_names':[]}
kinematics={}
ompl={'planning_plugins':['ompl_interface/OMPLPlanner'],'request_adapters':['default_planning_request_adapters/ResolveConstraintFrames','default_planning_request_adapters/ValidateWorkspaceBounds','default_planning_request_adapters/CheckStartStateBounds','default_planning_request_adapters/CheckStartStateCollision'],'response_adapters':['default_planning_response_adapters/AddTimeOptimalParameterization','default_planning_response_adapters/ValidateSolution','default_planning_response_adapters/DisplayMotionPath'],'planner_configs':{'RRTConnectkConfigDefault':{'type':'geometric::RRTConnect','range':0.0}}}
for side in ('left','right'):
    for suffix in ('arm','gripper'):
        group=f'{side}_{suffix}'
        names=[f'openarm_{side}_joint{i}' for i in range(1,8)] if suffix=='arm' else [f'openarm_{side}_finger_joint{i}' for i in (1,2)]
        g=E.SubElement(semantic,'group',name=group)
        if suffix=='arm':
            E.SubElement(g,'chain',base_link=f'openarm_{side}_link0',tip_link=f'openarm_{side}_hand')
            kinematics[group]={'kinematics_solver':'kdl_kinematics_plugin/KDLKinematicsPlugin','kinematics_solver_search_resolution':0.005,'kinematics_solver_timeout':0.1}
            E.SubElement(semantic,'end_effector',name=side+'_hand',parent_link=f'openarm_{side}_hand',group=f'{side}_gripper',parent_group=group)
        else:
            for name in names:E.SubElement(g,'joint',name=name)
        state=E.SubElement(semantic,'group_state',name='home',group=group)
        for name in names:E.SubElement(state,'joint',name=name,value='0')
        if suffix=='gripper':
            state=E.SubElement(semantic,'group_state',name='open',group=group)
            for name in names:E.SubElement(state,'joint',name=name,value='0.03')
        ctl=group+'_controller'
        controllers['controller_manager']['ros__parameters'][ctl]={'type':'joint_trajectory_controller/JointTrajectoryController'}
        tolerance=0.005 if suffix=='gripper' else 0.04
        controllers[ctl]={'ros__parameters':{'joints':names,'command_interfaces':['position'],'state_interfaces':['position','velocity'],'allow_partial_joints_goal':False,'constraints':{'goal_time':5.0,'stopped_velocity_tolerance':0.1,**{n:{'trajectory':0.2 if suffix=='arm' else 0.02,'goal':tolerance} for n in names}}}}
        moveit_controllers['controller_names'].append(ctl)
        moveit_controllers[ctl]={'type':'FollowJointTrajectory','action_ns':'follow_joint_trajectory','default':True,'joints':names}
        ompl[group]={'planner_configs':['RRTConnectkConfigDefault'],'longest_valid_segment_fraction':0.01}

E.indent(robot);E.indent(semantic)
(OUT/'openarm.urdf').write_text(E.tostring(robot,encoding='unicode'))
(OUT/'openarm.srdf').write_text(E.tostring(semantic,encoding='unicode'))
for filename, obj in [('controllers.yaml',controllers),('moveit_controllers.yaml',moveit_controllers),('kinematics.yaml',kinematics),('ompl.yaml',ompl),('joint_limits.yaml',{'joint_limits':joint_limits})]:
    (OUT/filename).write_text(yaml.safe_dump(obj,sort_keys=False))
print('Generated model/config:',OUT)

# Derived viewer scene: lighting and a decorative, non-colliding ground plane.
scene=E.parse(SRC.parent/'scene.xml')
scene.find('visual/quality').set('shadowsize','1024')
scene.find('visual/headlight').set('ambient','0.5 0.5 0.5')
scene.find('visual/headlight').set('diffuse','0.8 0.8 0.8')
scene.find('worldbody/geom').set('contype','0')
scene.find('worldbody/geom').set('conaffinity','0')
scene.write(SRC.parent/'simulation_scene.xml',encoding='unicode')
# Keep Openbox's standard mouse/keyboard bindings and arrange the two applications.
ns={'o':'http://openbox.org/3.4/rc'}
E.register_namespace('',ns['o'])
ob=E.parse('/etc/xdg/openbox/rc.xml')
apps=ob.find('o:applications',ns)
for cls,x,width in [('rviz2',0,1200),('MuJoCo',1200,720)]:
    rule=E.SubElement(apps,'{'+ns['o']+'}application',{'class':cls})
    pos=E.SubElement(rule,'{'+ns['o']+'}position',force='yes')
    E.SubElement(pos,'{'+ns['o']+'}x').text=str(x)
    E.SubElement(pos,'{'+ns['o']+'}y').text='0'
    size=E.SubElement(rule,'{'+ns['o']+'}size')
    E.SubElement(size,'{'+ns['o']+'}width').text=str(width)
    E.SubElement(size,'{'+ns['o']+'}height').text='1040'
    E.SubElement(rule,'{'+ns['o']+'}maximized').text='no'
ob.write(OUT/'openbox.xml',encoding='unicode')

# Optional fixed development obstacles; initially hidden with contact disabled.
from scene_objects import OBJECTS
scene = E.parse(SRC.parent/'simulation_scene.xml')
for obj in OBJECTS:
    E.SubElement(scene.find('worldbody'), 'geom', name=obj['id'], type='box',
                 pos=vec(obj['position']), size=vec([v/2 for v in obj['size']]),
                 rgba='0 0 0 0', contype='0', conaffinity='0', friction='1 0.005 0.0001')
scene.write(SRC.parent/'simulation_scene.xml', encoding='unicode')

from environment_assets import add_assets
add_assets(SRC.parent/"simulation_scene.xml")
