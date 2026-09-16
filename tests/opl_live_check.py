import os,time,json,math,tkinter as tk
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image,CameraInfo
from std_msgs.msg import String
from moveit_msgs.srv import GetPlanningScene
from moveit_msgs.msg import PlanningSceneComponents
from std_srvs.srv import Trigger
from scene_cli import call
from scene_panel import ScenePanel
from opl_assets import CATALOG,FURNITURE
from environment_assets import ITEMS
from PIL import Image as PILImage
root=tk.Tk();panel=ScenePanel(root)
rclpy.init();node=Node('verify_opl_gui')
latest={};messages={}
def state(msg):latest.update(json.loads(msg.data))
node.create_subscription(String,'/openarm/sim_state',state,2)
topics=[('color',Image,'/camera/camera/color/image_raw'),
        ('depth',Image,'/camera/camera/depth/image_rect_raw'),
        ('aligned',Image,'/camera/camera/aligned_depth_to_color/image_raw'),
        ('color_info',CameraInfo,'/camera/camera/color/camera_info'),
        ('depth_info',CameraInfo,'/camera/camera/depth/camera_info'),
        ('aligned_info',CameraInfo,'/camera/camera/aligned_depth_to_color/camera_info')]
for key,cls,topic in topics:
    messages[key]=[]
    node.create_subscription(cls,topic,lambda msg,k=key:messages[k].append(msg),3)
def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        root.update();rclpy.spin_once(node,timeout_sec=.01);time.sleep(.005)
def wait_idle():
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        pump(.1)
        if not panel.busy:
            pump(.4)
            if not panel.busy:return
    raise AssertionError(('GUI timeout',panel.state.get(),panel.detail.get()))
def scene():
    req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
    return {o.id:o for o in call(node,GetPlanningScene,'/get_planning_scene',req).scene.world.collision_objects}
def select(key):
    lib.query.set('');lib.tree.selection_set(key);root.update();lib.describe()
def action(key,mode,x=None,y=0,yaw=0,support='worktable',success=True):
    select(key);lib.support.set(support)
    if x is not None:
        for k,v in [('x',x),('y',y),('yaw',yaw)]:lib.values[k].set(str(v))
    lib.run(mode);wait_idle()
    print(key,mode,panel.state.get(),panel.detail.get(),flush=True)
    # Preserve operation outcome before the scheduled status refresh overwrites detail.
    pump(.5)
    if success:
        assert latest['objects'][key]['enabled']==(mode!='off'),(key,mode,panel.state.get(),panel.detail.get())
    return latest['objects'][key]
def geometry(key):
    pump(.8);co=scene()[ITEMS[key]['id']];obj=ITEMS[key]
    desc=[g for g in obj['geoms'] if g.get('collision',True)]
    assert len(co.primitives)+len(co.meshes)==len(desc),(key,len(co.primitives),len(co.meshes),len(desc))
    if not obj.get('ycb'):
        for primitive,pose,g in zip(co.primitives,co.primitive_poses,desc):
            dims=[2*v for v in g['size']] if g['type']=='box' else [2*g['size'][-1],g['size'][0]]
            assert np.allclose(primitive.dimensions,dims)
            assert np.allclose([pose.position.x,pose.position.y,pose.position.z],g['pos'])
    state=latest['objects'][key];assert np.allclose([co.pose.position.x,co.pose.position.y,co.pose.position.z],state['position'],atol=.015)
    q=np.array([co.pose.orientation.w,co.pose.orientation.x,co.pose.orientation.y,co.pose.orientation.z]); p=np.array(state['quaternion_wxyz'])
    assert min(np.linalg.norm(q-p),np.linalg.norm(q+p))<.02,(q,p)
    return co

try:
    pump(.7);wait_idle();panel.open_opl();wait_idle();lib=panel.opl_panel
    assert len(lib.tree.get_children())==59 # 34 rows +11 extra clothes +14 furniture
    lib.query.set('Lemonade');assert len(lib.tree.get_children())==1
    panel.request('camera-on');wait_idle();pump(4)
    assert min(len(v) for v in messages.values())>=3
    baseline=np.array(PILImage.frombytes('RGB',(320,180),bytes(messages['color'][-1].data)))
    # Actual GUI placement at a location visible to the real camera stream.
    action('opl_coffee_table','place',x=1.05);geometry('opl_coffee_table')
    pump(3)
    actual=np.array(PILImage.frombytes('RGB',(320,180),bytes(messages['color'][-1].data)))
    assert np.mean(abs(actual.astype(float)-baseline.astype(float)))>1,'Camera did not reflect mocap furniture'
    PILImage.fromarray(actual).save('/tmp/opl-live-v'+os.environ['OPENARM_VERSION']+'-camera.png')
    before=latest['objects']['opl_coffee_table']['position'][:]
    action('opl_lemonade','place',x=1.05,support='opl_coffee_table:top');geometry('opl_lemonade')
    action('opl_coffee_table','off',success=False)
    assert latest['objects']['opl_coffee_table']['enabled']
    action('opl_coffee_table','place',x=2,success=False)
    assert np.allclose(latest['objects']['opl_coffee_table']['position'],before)
    action('opl_lemonade','reposition',support='opl_coffee_table:top');geometry('opl_lemonade')
    old=latest['objects']['opl_lemonade']['position'][:]
    action('opl_lemonade','place',x=5,support='opl_coffee_table:top',success=False)
    assert np.allclose(latest['objects']['opl_lemonade']['position'],old,atol=.003)
    action('opl_lemonade','off');assert ITEMS['opl_lemonade']['id'] not in scene()
    action('opl_coffee_table','place',x=1.2,yaw=35);co=geometry('opl_coffee_table')
    assert abs(co.pose.position.x-1.2)<.001
    action('opl_coffee_table','off');assert ITEMS['opl_coffee_table']['id'] not in scene()
    # Compound open shelves: exact same primitive dimensions and local poses in MoveIt.
    action('opl_cabinet','place',x=2,yaw=25);geometry('opl_cabinet')
    action('opl_cup_rice','place',x=2,support='opl_cabinet:shelf1');geometry('opl_cup_rice')
    action('opl_cup_rice','off')
    action('opl_cabinet','off')
    for key,_,_ in topics:
        ms=messages[key]
        assert len({(m.header.stamp.sec,m.header.stamp.nanosec) for m in ms})>=3
        assert all(m.header.frame_id for m in ms)
    for key in ('depth','aligned'):
        m=messages[key][-1]
        assert m.encoding=='16UC1' and len(m.data)==m.height*m.width*2
        assert np.count_nonzero(np.frombuffer(m.data,dtype='<u2'))>0
    camera=json.loads(call(node,Trigger,'/openarm/camera/status',Trigger.Request()).message)
    assert camera['enabled'] and not camera['error']
    # Toggle OFF and ON: no stale replay accepted after re-enable.
    panel.request('camera-off');wait_idle();pump(.5)
    counts={k:len(v) for k,v in messages.items()};pump(1.5)
    assert counts=={k:len(v) for k,v in messages.items()}
    panel.request('camera-on');wait_idle();pump(2)
    assert all(len(messages[k])>v for k,v in counts.items())
    print('PASS GUI v'+os.environ['OPENARM_VERSION']+': catalog59/search/place/random/MOVE/hide/occupied and bounds guards; MoveIt exact primitive geometry and pose; live mocap RGB change; six fresh camera streams; OFF/ON',flush=True)
finally:
    node.destroy_node();rclpy.shutdown();root.destroy()
