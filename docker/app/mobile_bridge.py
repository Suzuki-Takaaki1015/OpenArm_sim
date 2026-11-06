"""ROS endpoint for the three physical omniwheel drives and an ideal UTM-30LX."""
import math,time
import numpy as np
import mujoco
from geometry_msgs.msg import Twist,TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan,JointState
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster,StaticTransformBroadcaster
from mobile_speeds import MAX_LINEAR, MAX_YAW, LINEAR_ACCEL, YAW_ACCEL

class Mobile:
    def __init__(self,node):
        self.node=node;self.sim=node.sim;m=self.sim.model
        self.ids=[];self.rows=[];self.names=[];self.qadr=[]
        for wheel in ('front_left','front_right','rear'):
            j=m.joint('axle_'+wheel);x,y,_=m.body('wheel_'+wheel).pos
            a,b=j.axis[1],-j.axis[0]
            self.rows.append([a/.06,b/.06,(x*b-y*a)/.06])
            self.ids.append(m.actuator('motor_'+wheel).id);self.names.append(j.name);self.qadr.append(int(j.qposadr[0]))
        self.matrix=np.asarray(self.rows);self.target=np.zeros(3);self.v=np.zeros(3)
        self.last_sim=-100.;self.last_wall=0.;self.next_scan=0.
        self.base=m.body('base_link').id;self.site=m.site('utm_scan_origin').id
        self.tf=TransformBroadcaster(node);self.fixed=StaticTransformBroadcaster(node)
        tr=TransformStamped();tr.header.frame_id='odom';tr.child_frame_id='world';tr.transform.rotation.w=1.;self.fixed.sendTransform(tr)
        self.odom=node.create_publisher(Odometry,'/odom',5)
        self.joints=node.create_publisher(JointState,'/joint_states',5)
        self.laser=node.create_publisher(LaserScan,'/scan',qos_profile_sensor_data)
        self.manual_until=0.
        self.sub=node.create_subscription(Twist,'/cmd_vel',self.automatic_command,1)
        self.manual_sub=node.create_subscription(Twist,'/happy/manual_cmd_vel',self.manual_command,1)
        robot_bodies={self.base}
        for body,parent in enumerate(m.body_parentid):
            if parent in robot_bodies:robot_bodies.add(body)
        self.self_geom=np.isin(m.geom_bodyid,list(robot_bodies))
        self.angles=np.deg2rad(np.linspace(-135.,135.,1081))
        self.rays=np.stack((np.cos(self.angles),np.sin(self.angles),np.zeros(1081)),axis=1)
    def automatic_command(self,msg):
        if time.monotonic() >= self.manual_until:
            self.command(msg)

    def manual_command(self,msg):
        # While the operator holds control, discard competing autonomous inputs.
        self.manual_until=time.monotonic()+.5
        self.command(msg)

    def command(self,msg):
        v=np.array([msg.linear.x,msg.linear.y,msg.angular.z])
        if not np.isfinite(v).all():v[:]=0
        v[:2] *= min(1., MAX_LINEAR / max(1e-12, np.linalg.norm(v[:2])))
        v[2] = np.clip(v[2], -MAX_YAW, MAX_YAW)
        self.target=v;self.last_sim=self.sim.data.time;self.last_wall=time.monotonic()
    def step(self):
        d=self.sim.data;dt=self.sim.model.opt.timestep
        goal=self.target if d.time-self.last_sim<.5 and time.monotonic()-self.last_wall<.5 else np.zeros(3)
        dv = goal - self.v
        dv[:2] *= min(1., LINEAR_ACCEL * dt / max(np.linalg.norm(dv[:2]), 1e-12))
        dv[2] = np.clip(dv[2], -YAW_ACCEL * dt, YAW_ACCEL * dt)
        self.v+=dv;d.ctrl[self.ids]=np.clip(self.matrix@self.v,-14,14)
    def publish(self,stamp):
        m,d=self.sim.model,self.sim.data
        o=Odometry();o.header.stamp=stamp;o.header.frame_id='odom';o.child_frame_id='base_link'
        p=o.pose.pose;p.position.x,p.position.y,p.position.z=map(float,d.xpos[self.base])
        p.orientation.w,p.orientation.x,p.orientation.y,p.orientation.z=map(float,d.xquat[self.base])
        v=np.zeros(6);mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_XBODY,self.base,v,1)
        o.twist.twist.angular.x,o.twist.twist.angular.y,o.twist.twist.angular.z=map(float,v[:3])
        o.twist.twist.linear.x,o.twist.twist.linear.y,o.twist.twist.linear.z=map(float,v[3:]);self.odom.publish(o)
        tr=TransformStamped();tr.header=o.header;tr.child_frame_id=o.child_frame_id;tr.transform.rotation=p.orientation
        tr.transform.translation.x,tr.transform.translation.y,tr.transform.translation.z=map(float,d.xpos[self.base]);self.tf.sendTransform(tr)
        j=JointState();j.header.stamp=stamp;j.name=self.names;j.position=d.qpos[self.qadr].tolist();self.joints.publish(j)
    def scan(self,stamp):
        m,d=self.sim.model,self.sim.data
        if d.time+1e-9<self.next_scan:return
        self.next_scan=max(self.next_scan+.025,d.time)
        if not self.laser.get_subscription_count():return
        directions=np.ascontiguousarray(self.rays@d.site_xmat[self.site].reshape(3,3).T)
        ids=np.full(1081,-1,np.int32);dist=np.full(1081,-1.)
        mujoco.mj_multiRay(m,d,d.site_xpos[self.site],directions.ravel(),np.array([1,1,1,0,0,0],np.uint8),1,self.base,ids,dist,None,1081,30.)
        msg=LaserScan();msg.header.stamp=stamp;msg.header.frame_id='laser';msg.angle_min=float(self.angles[0]);msg.angle_max=float(self.angles[-1])
        msg.angle_increment=math.radians(.25);msg.scan_time=.025;msg.time_increment=0.;msg.range_min=.1;msg.range_max=30.
        ranges=np.where((ids>=0)&(dist>=.1)&(dist<=30.),dist,np.inf)
        ranges[(ids>=0)&self.self_geom[np.maximum(ids,0)]]=np.nan
        msg.ranges=ranges.astype(np.float32).tolist()
        self.laser.publish(msg)
