"""Optional ideal MID-360S point cloud, isolated from simulation control."""
import json,os,time
import numpy as np
import mujoco,rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy
from sensor_msgs.msg import PointCloud2,PointField
from std_msgs.msg import String
from std_srvs.srv import SetBool,Trigger
from rcl_interfaces.msg import SetParametersResult
from environment_assets import ITEMS
from scene_objects import OBJECTS
from ycb_assets import set_visibility
from lidar_mount import config
from lidar_scan import directions,scan
class Lidar(Node):
    def __init__(self):
        super().__init__('openarm_mid360s_sim');self.cfg=config()
        self.declare_parameter('rays_per_frame',self.cfg['rays_per_frame']);self.declare_parameter('fps',self.cfg['fps'])
        self.count=int(self.get_parameter('rays_per_frame').value);self.fps=float(self.get_parameter('fps').value)
        if not 32<=self.count<=40000 or not 0<self.fps<=20:raise ValueError('rays_per_frame:32..40000; fps:(0,20]')
        self.enabled=False;self.latest=None;self.model=None;self.error='';self.last_stamp=None;self.frame=0;self.points=0;self.scan_ms=0.
        self.create_subscription(String,'/openarm/sim_state',self.state,1)
        self.pub=self.create_publisher(PointCloud2,'/lidar/points',QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE))
        self.create_service(SetBool,'/openarm/lidar/set_enabled',self.toggle)
        self.create_service(Trigger,'/openarm/lidar/status',self.status)
        self.create_timer(1/self.fps,self.render)
        self.add_on_set_parameters_callback(self.validate_parameters)
        self.add_post_set_parameters_callback(self.apply_parameters)
        self.last_wall_time=None;self.cloud_hz=0.
    def validate_parameters(self,params):
        for p in params:
            if p.name=='rays_per_frame' and (type(p.value) is not int or not 32<=p.value<=40000):
                return SetParametersResult(successful=False,reason='rays_per_frame must be an integer in 32..40000')
            if p.name=='fps' and p.value!=self.fps:
                return SetParametersResult(successful=False,reason='fps is a startup setting; change rays_per_frame for live density')
        return SetParametersResult(successful=True)
    def apply_parameters(self,params):
        for p in params:
            if p.name=='rays_per_frame':self.count=p.value
    def state(self,msg):
        try:self.latest=json.loads(msg.data)
        except (ValueError,TypeError) as exc:self.error=str(exc)
    def toggle(self,req,res):
        self.enabled=req.data;self.error='';self.last_stamp=None;self.last_wall_time=None;self.cloud_hz=0.
        if not self.enabled:
            self.publish(np.empty((0,3),dtype='<f4'),self.latest['time'] if self.latest else 0.)
            self.data=None;self.model=None
        res.success=True;res.message='LiDAR on' if self.enabled else 'LiDAR off';return res
    def status(self,req,res):
        res.success=True;res.message=json.dumps({'enabled':self.enabled,'error':self.error,'points':self.points,'scan_ms':self.scan_ms,'rays_per_frame':self.count,'fps_limit':self.fps,'nominal_rays_per_second':self.count*self.fps,'cloud_hz':self.cloud_hz,'last_sim_time':self.last_stamp,'model':'MID-360S','scan_pattern':'ideal approximation','mount_calibrated':False});return res
    def initialize(self):
        from sensor_model import load_sensor_model
        self.model,self.active=load_sensor_model(self.latest,textures=False);self.data=mujoco.MjData(self.model)
        self.bid=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,'mid360s_link')
        self.exclude=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,'mid360s_mount')
        if min(self.bid,self.exclude)<0:raise ValueError('LiDAR mount missing: rebuild image')
        self.model.geom_group[self.model.geom_group==3]=5
    def publish(self,points,stamp):
        msg=PointCloud2();msg.header.frame_id='mid360s_link'
        msg.header.stamp.sec,msg.header.stamp.nanosec=divmod(round(stamp*1e9),1000000000)
        msg.height=1;msg.width=len(points);msg.is_bigendian=False;msg.is_dense=True
        msg.fields=[PointField(name=n,offset=4*i,datatype=PointField.FLOAT32,count=1) for i,n in enumerate(('x','y','z'))]
        msg.point_step=12;msg.row_step=12*len(points);msg.data=points.tobytes();self.pub.publish(msg)
    def render(self):
        if not self.enabled or self.latest is None or self.latest['time']==self.last_stamp:return
        snapshot=self.latest
        try:
            from sensor_model import active_objects
            if self.model is None or self.active!=active_objects(snapshot):
                self.data=None;self.model=None
                self.initialize()
            start=time.perf_counter();m,d=self.model,self.data
            d.qpos[:]=snapshot['qpos'];d.time=snapshot['time']
            if m.nmocap:d.mocap_pos[:]=snapshot['mocap_pos'];d.mocap_quat[:]=snapshot['mocap_quat']
            for obj in OBJECTS:
                gid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,obj['id'])
                m.geom_group[gid]=0 if snapshot['obstacles'] else 5
                m.geom_rgba[gid]=obj['rgba'] if snapshot['obstacles'] else [0,0,0,0]
            for key,obj in ITEMS.items():
                enabled=snapshot['objects'][key]['enabled']
                for i,g in enumerate(obj['geoms']):
                    gid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,f'{obj["id"]}_{i}')
                    if gid<0:continue
                    set_visibility(m,gid,g,enabled)
                    m.geom_group[gid]=5 if not enabled or g.get('collision',False) else 2
            mujoco.mj_forward(m,d)
            rays=directions(self.count,self.frame,self.cfg['vertical_min_deg'],self.cfg['vertical_max_deg'])
            pts,_=scan(mujoco,m,d,d.xpos[self.bid],d.xmat[self.bid].reshape(3,3),rays,self.exclude,self.cfg['min_range_m'],self.cfg['max_range_m'])
            now=time.perf_counter()
            self.cloud_hz=1/(now-self.last_wall_time) if self.last_wall_time is not None else 0.
            self.last_wall_time=now
            self.publish(pts,snapshot['time']);self.last_stamp=snapshot['time'];self.frame+=1;self.points=len(pts);self.scan_ms=(time.perf_counter()-start)*1000
        except Exception as exc:
            self.enabled=False;self.error=str(exc);self.get_logger().error('LiDAR disabled: '+self.error)
def main():
    rclpy.init();node=Lidar()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
