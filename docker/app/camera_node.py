"""Ideal RGB-D sensor with D435-like topics. Not a librealsense/device emulator."""
import os,json,math,time
os.environ['MUJOCO_GL']='osmesa' if os.environ.get('LIBGL_ALWAYS_SOFTWARE','1')=='1' else 'egl'
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
# Compatible with RViz defaults and BEST_EFFORT sensor readers.
IMAGE_QOS = QoSProfile(depth=2, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
from sensor_msgs.msg import Image,CameraInfo
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
        for stream in ('color','depth','aligned_depth_to_color'):
            name='image_raw' if stream=='color' or stream=='aligned_depth_to_color' else 'image_rect_raw'
            self.pub[stream]=(self.create_publisher(Image,f'/camera/camera/{stream}/{name}',IMAGE_QOS),self.create_publisher(CameraInfo,f'/camera/camera/{stream}/camera_info',IMAGE_QOS))
        self.tf=StaticTransformBroadcaster(self);self.transforms()
        self.create_timer(1/self.cfg['fps'],self.render)
    def state(self,msg):self.latest=json.loads(msg.data)
    def status(self,req,res):
        res.success=True;res.message=json.dumps({'enabled':self.enabled,'error':self.error,'mount_calibrated':self.cfg['calibration_verified']});return res
    def toggle(self,req,res):
        self.enabled=req.data;self.error='';res.success=True;res.message='camera on' if req.data else 'camera off';return res
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
        self.tf.sendTransform(out)
    def initialize(self):
        import mujoco
        self.mj=mujoco;self.model=mujoco.MjModel.from_xml_path(os.environ['OPENARM_SCENE']);self.data=mujoco.MjData(self.model)
        self.model.vis.global_.offwidth=max(self.cfg[k]['width'] for k in ('color','depth'))
        self.model.vis.global_.offheight=max(self.cfg[k]['height'] for k in ('color','depth'))
        for stream in ('color','depth'):
            c=self.cfg[stream];self.renderers[stream]=mujoco.Renderer(self.model,height=c['height'],width=c['width'])
        self.get_logger().info('RGB-D rendering enabled; ideal optics, official bracket with project-defined M6 height')
    def publish(self,stream,pixels,snapshot):
        c=self.cfg['depth' if stream=='depth' else 'color'];w,h=c['width'],c['height']
        frame='camera_depth_optical_frame' if stream=='depth' else 'camera_color_optical_frame'
        msg=Image();ns=round(snapshot['time']*1e9);msg.header.stamp.sec,msg.header.stamp.nanosec=divmod(ns,1000000000);msg.header.frame_id=frame
        msg.height=h;msg.width=w;msg.is_bigendian=0
        if stream=='color':msg.encoding='rgb8';msg.step=w*3;msg.data=pixels.astype('uint8').tobytes()
        else:
            valid=np.isfinite(pixels)&(pixels>=self.cfg['min_depth_m'])&(pixels<=self.cfg['max_depth_m'])
            pixels=np.where(valid,pixels*1000,0);msg.encoding='16UC1';msg.step=w*2;msg.data=np.rint(pixels).astype('<u2').tobytes()
        info=CameraInfo();info.header=msg.header;info.width=w;info.height=h;info.distortion_model='plumb_bob';info.d=[0.0]*5
        f=h/(2*math.tan(math.radians(c['vertical_fov_deg'])/2));cx=w/2;cy=h/2
        info.k=[f,0.,cx,0.,f,cy,0.,0.,1.];info.r=[1.,0.,0.,0.,1.,0.,0.,0.,1.];info.p=[f,0.,cx,0.,0.,f,cy,0.,0.,0.,1.,0.]
        self.pub[stream][0].publish(msg);self.pub[stream][1].publish(info)
    def render(self):
        if not self.enabled or not self.latest or self.latest['time']==self.last_stamp:return
        snapshot=self.latest
        try:
            if self.model is None:self.initialize()
            m,d=self.model,self.data;d.qpos[:]=snapshot['qpos'];d.time=snapshot['time']
            for obj in OBJECTS:
                g=self.mj.mj_name2id(m,self.mj.mjtObj.mjOBJ_GEOM,obj['id']);m.geom_rgba[g]=obj['rgba'] if snapshot['obstacles'] else [0,0,0,0]
            for key,obj in ITEMS.items():
                for i,geom in enumerate(obj['geoms']):
                    g=self.mj.mj_name2id(m,self.mj.mjtObj.mjOBJ_GEOM,f'{obj["id"]}_{i}');set_visibility(m,g,geom,snapshot['objects'][key]['enabled'])
            self.mj.mj_forward(m,d)
            color=self.renderers['color'];color.disable_depth_rendering();color.update_scene(d,camera='d435_color');self.publish('color',color.render().copy(),snapshot)
            color.enable_depth_rendering();self.publish('aligned_depth_to_color',color.render().copy(),snapshot)
            depth=self.renderers['depth'];depth.enable_depth_rendering();depth.update_scene(d,camera='d435_depth');self.publish('depth',depth.render().copy(),snapshot)
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
