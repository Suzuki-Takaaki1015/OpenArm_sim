"""Run inside a generated OpenArm image; tests real rendering and ROS publication."""
import os,time,json
import numpy as np
import rclpy
from sensor_msgs.msg import Image,CameraInfo
from camera_node import Camera
from environment_assets import ITEMS
rclpy.init()
node=Camera();received={}
subscriptions=[]
for side in ('left','right'):
    for kind,cls,suffix in [('rgb',Image,'image_raw'),('info',CameraInfo,'camera_info')]:
        key=side+'_'+kind
        subscriptions.append(node.create_subscription(cls,f'/camera/{side}_wrist/color/{suffix}',lambda msg,k=key: received.__setitem__(k,msg),2))
node.initialize();m=node.model;d=node.data;mj=node.mj
node.latest={'time':1.,'qpos':d.qpos.tolist(),'mocap_pos':d.mocap_pos.tolist(),'mocap_quat':d.mocap_quat.tolist(),'obstacles':True,'objects':{k:{'enabled':False} for k in ITEMS}}
node.enabled=True
for _ in range(30):
    rclpy.spin_once(node,timeout_sec=.1)
    if len(received)==4:break
assert not node.error,node.error
assert len(received)==4,received.keys()
for side in ('left','right'):
    image=received[side+'_rgb'];info=received[side+'_info']
    assert (image.width,image.height,image.encoding)==(320,200,'rgb8')
    assert image.header.frame_id==f'camera_{side}_wrist_optical_frame'
    assert info.header==image.header
    assert abs(info.k[0]-100/np.tan(np.deg2rad(33)))<1e-4
    pixels=np.frombuffer(image.data,dtype=np.uint8)
    assert pixels.std()>1,'Uniform image'
    cid=mj.mj_name2id(m,mj.mjtObj.mjOBJ_CAMERA,f'camera_wrist_{side}')
    before=d.cam_xpos[cid].copy()
    jid=mj.mj_name2id(m,mj.mjtObj.mjOBJ_JOINT,f'openarm_{side}_joint2')
    d.qpos[m.jnt_qposadr[jid]]+=.2;mj.mj_forward(m,d)
    assert np.linalg.norm(d.cam_xpos[cid]-before)>.001
    print('PASS',side,'RGB/CameraInfo and wrist motion',flush=True)
node.close();node.destroy_node();rclpy.shutdown()
