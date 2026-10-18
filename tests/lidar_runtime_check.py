"""Run inside a disposable running simulator; checks point cloud and camera end to end."""
import json,time,math,os
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2,Image
from std_srvs.srv import SetBool,Trigger
from tf2_ros import Buffer,TransformListener
from rclpy.time import Time
rclpy.init();n=Node('mid360s_acceptance');clouds=[];images=[]
buffer=Buffer();listener=TransformListener(buffer,n)
n.create_subscription(PointCloud2,'/lidar/points',lambda m:clouds.append(m),10)
n.create_subscription(Image,'/camera/camera/color/image_raw',lambda m:images.append(m),2)
wrists={}
if os.environ.get('OPENARM_VERSION')=='2':
    for side in ('left','right'):
        n.create_subscription(Image,f'/camera/{side}_wrist/color/image_raw',lambda m,side=side:wrists.update({side:m}),2)
def spin(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.05)
def call(kind,name,data=None):
    c=n.create_client(kind,name)
    assert c.wait_for_service(timeout_sec=90),name
    req=kind.Request()
    if data is not None:req.data=data
    f=c.call_async(req);rclpy.spin_until_future_complete(n,f,timeout_sec=90)
    assert f.done() and f.result().success,(name,f.result())
    n.destroy_client(c);return f.result()
try:
    status=json.loads(call(Trigger,'/openarm/lidar/status').message)
    assert not status['enabled']
    call(SetBool,'/openarm/set_obstacles',True)
    call(SetBool,'/openarm/lidar/set_enabled',True)
    deadline=time.monotonic()+60
    while not clouds and time.monotonic()<deadline:spin(.2)
    assert clouds,'No LiDAR messages'
    spin(2)
    state=json.loads(call(Trigger,'/openarm/lidar/status').message)
    assert state['enabled'] and not state['error'],state
    assert any(m.width>0 for m in clouds)
    t=buffer.lookup_transform('world','mid360s_link',Time())
    # Factory mounting datum from lidar_config; world == fixed base in this stack.
    assert abs(t.transform.translation.x-(.065+.047*math.sin(math.radians(55))))<1e-6
    assert abs(t.transform.translation.z-(.42+.047*math.cos(math.radians(55))))<1e-6
    q=t.transform.rotation
    R=np.array([[1-2*(q.y*q.y+q.z*q.z),2*(q.x*q.y-q.z*q.w),2*(q.x*q.z+q.y*q.w)],
                [2*(q.x*q.y+q.z*q.w),1-2*(q.x*q.x+q.z*q.z),2*(q.y*q.z-q.x*q.w)],
                [2*(q.x*q.z-q.y*q.w),2*(q.y*q.z+q.x*q.w),1-2*(q.x*q.x+q.y*q.y)]])
    origin=np.array([t.transform.translation.x,t.transform.translation.y,t.transform.translation.z])
    def table_hits(messages):
        total=0
        for m in messages:
            assert m.header.frame_id=='mid360s_link' and m.row_step==m.width*12
            p=np.frombuffer(bytes(m.data),dtype='<f4').reshape(-1,3)
            assert np.isfinite(p).all()
            if not len(p):continue
            assert np.linalg.norm(p,axis=1).min()>=.0999
            world=p@R.T+origin
            total+=np.count_nonzero((abs(world[:,2]-.16)<.001)&(world[:,0]>.25)&(world[:,0]<.75)&(abs(world[:,1])<.35))
        return total
    hits=table_hits(clouds);assert hits>5,hits
    call(SetBool,'/openarm/set_obstacles',False);spin(1);clouds.clear();spin(3)
    assert table_hits(clouds)==0,'Hidden table still returns points'
    call(SetBool,'/openarm/camera/set_enabled',True)
    deadline=time.monotonic()+60
    while not images and time.monotonic()<deadline:spin(.2)
    assert images and images[-1].width>0,'Camera regression'
    if os.environ.get('OPENARM_VERSION')=='2':
        deadline=time.monotonic()+60
        while len(wrists)<2 and time.monotonic()<deadline:spin(.2)
        assert len(wrists)==2,'Wrist cameras missing'
    call(SetBool,'/openarm/set_obstacles',True)
    call(SetBool,'/openarm/objects/box/set_enabled',True)
    images.clear();clouds.clear();deadline=time.monotonic()+90
    while (not images or not clouds) and time.monotonic()<deadline:spin(.2)
    assert images and clouds,'Sensor reload after object toggle failed'
    for sensor in ('camera','lidar'):
        status=json.loads(call(Trigger,f'/openarm/{sensor}/status').message)
        assert status['enabled'] and not status['error'],status
    call(SetBool,'/openarm/objects/box/set_enabled',False)
    call(SetBool,'/openarm/lidar/set_enabled',False);spin(.8);clouds.clear();spin(1)
    assert not clouds,'LiDAR continues publishing after stop'
    call(SetBool,'/openarm/lidar/set_enabled',True)
    deadline=time.monotonic()+60
    while not clouds and time.monotonic()<deadline:spin(.2)
    assert clouds,'LiDAR failed to resume'
    call(SetBool,'/openarm/lidar/set_enabled',False)
    call(SetBool,'/openarm/camera/set_enabled',False)
    print('PASS MID-360S: TF, XYZ cloud, table geometry, hidden table, toggle/resume, chest camera',state,flush=True)
finally:n.destroy_node();rclpy.shutdown()
