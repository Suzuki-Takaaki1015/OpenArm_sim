"""Ideal RGB-D sensor with D435-like topics. Not a librealsense/device emulator."""
import os,json,math,time
os.environ['MUJOCO_GL']='osmesa' if os.environ.get('LIBGL_ALWAYS_SOFTWARE','1')=='1' else 'egl'
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
# Compatible with RViz defaults and BEST_EFFORT sensor readers.
IMAGE_QOS = QoSProfile(depth=2, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
from sensor_msgs.msg import Image,CameraInfo,PointCloud2
from rgbd_cloud import point_cloud
from std_msgs.msg import String
from std_srvs.srv import SetBool,Trigger
from geometry_msgs.msg import TransformStamped
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
from environment_assets import ITEMS,camera_config
from scene_objects import OBJECTS
from ycb_assets import set_visibility

class Camera(Node):
    def __init__(self):
        super().__init__('openarm_d435_sim')
        self.cfg=camera_config();self.enabled=False;self.latest=None;self.last_stamp=-1;self.model=None;self.renderers={};self.error=''
        self.create_subscription(String,'/openarm/sim_state',self.state,2)
        self.create_service(SetBool,'/openarm/camera/set_enabled',self.toggle)
        self.create_service(Trigger,'/openarm/camera/status',self.status)
        self.pub={}
        self.wrists={}
        if os.environ.get('OPENARM_VERSION')=='2':
            for side in ('left','right'):
                stream=f'wrist_{side}'
                self.pub[stream]=(self.create_publisher(Image,f'/camera/{side}_wrist/color/image_raw',IMAGE_QOS),self.create_publisher(CameraInfo,f'/camera/{side}_wrist/color/camera_info',IMAGE_QOS))
        for stream in ('color','depth','aligned_depth_to_color'):
            name='image_raw' if stream=='color' or stream=='aligned_depth_to_color' else 'image_rect_raw'
            self.pub[stream]=(self.create_publisher(Image,f'/camera/camera/{stream}/{name}',IMAGE_QOS),self.create_publisher(CameraInfo,f'/camera/camera/{stream}/camera_info',IMAGE_QOS))
        self.mobile=os.getenv('HAPPY_MOBILE')=='1'
        self.camera_pubs={}
        self.clouds={}
        self.d455={'color':{'width':320,'height':200,'vertical_fov_deg':65.},
                   'depth':{'width':424,'height':240,'vertical_fov_deg':58.}}
        if self.mobile:
            for camera in ('d435i','d455'):
                for stream in ('color','depth','aligned_depth_to_color'):
                    prefix=f'/camera/{camera}/{stream}'
                    leaf='image_rect_raw' if stream=='depth' else 'image_raw'
                    self.camera_pubs[camera,stream]=(self.create_publisher(Image,prefix+'/'+leaf,IMAGE_QOS),
                                                     self.create_publisher(CameraInfo,prefix+'/camera_info',IMAGE_QOS))
                self.clouds[camera]=self.create_publisher(PointCloud2,f'/camera/{camera}/depth/color/points',IMAGE_QOS)
        self.tf=StaticTransformBroadcaster(self);self.transforms()
        self.create_timer(1/self.cfg['fps'],self.render)
    def state(self,msg):self.latest=json.loads(msg.data)
    def status(self,req,res):
        res.success=True;res.message=json.dumps({'enabled':self.enabled,'error':self.error,'mount_calibrated':self.cfg['calibration_verified'],'wrist_cameras':list(self.wrists),'rgbd_cameras':list(self.clouds) if self.mobile else ['d435']});return res
    def toggle(self,req,res):
        self.enabled=req.data;self.error=''
        if not self.enabled:
            self.close();self.renderers={};self.renderer=None;self.data=None;self.model=None
        self.last_stamp=-1
        res.success=True;res.message='camera on' if req.data else 'camera off';return res
    def transforms(self):
        out=[];cfg=self.cfg
        t=TransformStamped();t.header.frame_id=cfg['parent_frame'];t.child_frame_id='camera_link'
        t.transform.translation.x,t.transform.translation.y,t.transform.translation.z=cfg['position_m']
        r,p,y=[v/2 for v in cfg['rpy_rad']];cr,sr=math.cos(r),math.sin(r);cp,sp=math.cos(p),math.sin(p);cy,sy=math.cos(y),math.sin(y)
        t.transform.rotation.x=sr*cp*cy-cr*sp*sy;t.transform.rotation.y=cr*sp*cy+sr*cp*sy;t.transform.rotation.z=cr*cp*sy-sr*sp*cy;t.transform.rotation.w=cr*cp*cy+sr*sp*sy;out.append(t)
        for name in ('color','depth'):
            t=TransformStamped();t.header.frame_id='camera_link';t.child_frame_id=f'camera_{name}_optical_frame'
            if name=='color':t.transform.translation.x,t.transform.translation.y,t.transform.translation.z=cfg['color_offset_m']
            t.transform.rotation.x=-.5;t.transform.rotation.y=.5;t.transform.rotation.z=-.5;t.transform.rotation.w=.5;out.append(t)
        self.base_transforms=out;self.tf.sendTransform(out)
    def initialize(self):
        import mujoco
        from sensor_model import load_sensor_model
        self.mj=mujoco;self.model,self.active=load_sensor_model(self.latest);self.data=mujoco.MjData(self.model)
        self.model.vis.global_.offwidth=max(self.cfg[k]['width'] for k in ('color','depth'))
        self.model.vis.global_.offheight=max(self.cfg[k]['height'] for k in ('color','depth'))
        from shared_renderer import SharedRenderer
        self.renderer=SharedRenderer(self.model,height=self.model.vis.global_.offheight,width=self.model.vis.global_.offwidth)
        self.renderers['shared']=self.renderer
        if os.environ.get('OPENARM_VERSION')=='2':
            transforms=[]
            for side in ('left','right'):
                name=f'camera_wrist_{side}'
                cid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_CAMERA,name)
                if cid<0: raise RuntimeError('Official wrist camera missing: '+name)
                stream=f'wrist_{side}'
                # Keep official aspect ratio and field of view; reduce resolution for VM use.
                self.wrists[stream]={'width':320,'height':200,'vertical_fov_deg':float(self.model.cam_fovy[cid]),'camera':name}

                transform=TransformStamped()
                transform.header.frame_id=mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_BODY,int(self.model.cam_bodyid[cid]))
                transform.child_frame_id=f'camera_{side}_wrist_optical_frame'
                transform.transform.translation.x,transform.transform.translation.y,transform.transform.translation.z=map(float,self.model.cam_pos[cid])
                # MuJoCo camera: -Z forward/+Y up; ROS optical: +Z forward/+Y down.
                q=np.empty(4);mujoco.mju_mulQuat(q,self.model.cam_quat[cid],np.array([0.,1.,0.,0.]))
                transform.transform.rotation.w,transform.transform.rotation.x,transform.transform.rotation.y,transform.transform.rotation.z=map(float,q)
                transforms.append(transform)
            if self.mobile:
                for channel in ('color','depth'):
                    cid=self.model.camera('d455_'+channel).id
                    t=TransformStamped()
                    t.header.frame_id='base_link'
                    t.child_frame_id=f'd455_{channel}_optical_frame'
                    t.transform.translation.x,t.transform.translation.y,t.transform.translation.z=map(float,self.model.cam_pos[cid])
                    q=np.empty(4)
                    mujoco.mju_mulQuat(q,self.model.cam_quat[cid],np.array([0.,1.,0.,0.]))
                    t.transform.rotation.w,t.transform.rotation.x,t.transform.rotation.y,t.transform.rotation.z=map(float,q)
                    transforms.append(t)
            self.tf.sendTransform(self.base_transforms+transforms)
        self.get_logger().info('Chest RGB-D and available official wrist RGB cameras enabled')
    def publish(self,stream,pixels,snapshot,camera='d435i'):
        c=self.wrists[stream] if stream in self.wrists else self.cfg['depth' if stream=='depth' else 'color'];w,h=c['width'],c['height']
        frame=f'camera_{stream[6:]}_wrist_optical_frame' if stream in self.wrists else 'camera_depth_optical_frame' if stream=='depth' else 'camera_color_optical_frame'
        if camera=='d455':
            c=self.d455['depth' if stream=='depth' else 'color'];w,h=c['width'],c['height']
            frame='d455_depth_optical_frame' if stream=='depth' else 'd455_color_optical_frame'
        depth_mm=None
        msg=Image();ns=round(snapshot['time']*1e9);msg.header.stamp.sec,msg.header.stamp.nanosec=divmod(ns,1000000000);msg.header.frame_id=frame
        msg.height=h;msg.width=w;msg.is_bigendian=0
        if stream=='color' or stream in self.wrists:msg.encoding='rgb8';msg.step=w*3;msg.data=pixels.astype('uint8').tobytes()
        else:
            near,far=(.18,6.) if camera=='d455' else (self.cfg['min_depth_m'],self.cfg['max_depth_m'])
            valid=np.isfinite(pixels)&(pixels>=near)&(pixels<=far)
            pixels=np.where(valid,pixels*1000,0);msg.encoding='16UC1';msg.step=w*2;depth_mm=np.rint(pixels).astype('<u2');msg.data=depth_mm.tobytes()
        info=CameraInfo();info.header=msg.header;info.width=w;info.height=h;info.distortion_model='plumb_bob';info.d=[0.0]*5
        f=h/(2*math.tan(math.radians(c['vertical_fov_deg'])/2));cx=w/2;cy=h/2
        info.k=[f,0.,cx,0.,f,cy,0.,0.,1.];info.r=[1.,0.,0.,0.,1.,0.,0.,0.,1.];info.p=[f,0.,cx,0.,0.,f,cy,0.,0.,0.,1.,0.]
        destinations=[]
        if camera=='d435i':destinations.append(self.pub[stream])
        if (camera,stream) in self.camera_pubs:destinations.append(self.camera_pubs[camera,stream])
        for images,infos in destinations:
            images.publish(msg);infos.publish(info)
        return info,depth_mm

    def render_rgbd(self,camera,snapshot):
        cfg=self.d455 if camera=='d455' else self.cfg
        model_name='d455' if camera=='d455' else 'd435'
        color=self.renderer.resize_viewport(cfg['color']['width'],cfg['color']['height'])
        color.disable_depth_rendering()
        color.update_scene(self.data,camera=model_name+'_color')
        rgb=color.render().copy()
        self.publish('color',rgb,snapshot,camera)
        color.enable_depth_rendering()
        info,mm=self.publish('aligned_depth_to_color',color.render(),snapshot,camera)
        cloud=self.clouds.get(camera)
        if cloud is not None and cloud.get_subscription_count():
            cloud.publish(point_cloud(info,rgb,mm))
        depth=self.renderer.resize_viewport(cfg['depth']['width'],cfg['depth']['height'])
        depth.enable_depth_rendering()
        depth.update_scene(self.data,camera=model_name+'_depth')
        self.publish('depth',depth.render(),snapshot,camera)
    def render(self):
        if not self.enabled or not self.latest or self.latest['time']==self.last_stamp:return
        snapshot=self.latest
        try:
            from sensor_model import active_objects
            if self.model is None or self.active!=active_objects(snapshot):
                self.close();self.renderers={};self.renderer=None;self.data=None;self.model=None
                self.initialize()
            m,d=self.model,self.data;d.qpos[:]=snapshot['qpos'];d.time=snapshot['time']
            if m.nmocap:
                d.mocap_pos[:]=snapshot['mocap_pos'];d.mocap_quat[:]=snapshot['mocap_quat']
            for obj in OBJECTS:
                g=self.mj.mj_name2id(m,self.mj.mjtObj.mjOBJ_GEOM,obj['id']);m.geom_rgba[g]=obj['rgba'] if snapshot['obstacles'] else [0,0,0,0]
            for key,obj in ITEMS.items():
                for i,geom in enumerate(obj['geoms']):
                    g=self.mj.mj_name2id(m,self.mj.mjtObj.mjOBJ_GEOM,f'{obj["id"]}_{i}')
                    if g>=0:set_visibility(m,g,geom,snapshot['objects'][key]['enabled'])
            self.mj.mj_forward(m,d)
            self.render_rgbd('d435i',snapshot)
            if self.mobile:self.render_rgbd('d455',snapshot)
            for stream,c in self.wrists.items():
                renderer=self.renderer.resize_viewport(c['width'],c['height']);renderer.disable_depth_rendering();renderer.update_scene(d,camera=c['camera']);self.publish(stream,renderer.render().copy(),snapshot)
            self.last_stamp=snapshot['time']
        except Exception as exc:
            self.error=str(exc);self.enabled=False;self.get_logger().error('Camera disabled: '+self.error)
    def close(self):
        for renderer in self.renderers.values():renderer.close()

def main():
    rclpy.init();node=Camera()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.close();node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
