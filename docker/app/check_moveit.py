"""Acceptance: real MoveIt plan+execute actions and measured MuJoCo feedback."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from sensor_msgs.msg import JointState
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, PositionConstraint, OrientationConstraint
from moveit_msgs.srv import GetPositionFK, GetStateValidity
from shape_msgs.msg import SolidPrimitive
from geometry_msgs.msg import Pose

class Check(Node):
    def __init__(self):
        super().__init__('openarm_moveit_acceptance')
        self.current=None; self.raw=None; self.samples=0
        self.create_subscription(JointState,'/joint_states',self.state,10)
        self.create_subscription(JointState,'/mujoco/joint_states',self.physics,10)
        self.move=ActionClient(self,MoveGroup,'/move_action')
        self.fk=self.create_client(GetPositionFK,'/compute_fk')
        self.valid=self.create_client(GetStateValidity,'/check_state_validity')
        self.results=[]
    def state(self,msg): self.current=msg
    def physics(self,msg): self.raw=msg; self.samples+=1
    def wait(self,future,timeout=120):
        deadline=time.monotonic()+timeout
        while not future.done() and time.monotonic()<deadline:rclpy.spin_once(self,timeout_sec=0.1)
        if not future.done():raise RuntimeError('ROS request timeout')
        result=future.result()
        if result is None:raise RuntimeError('Empty ROS result')
        return result
    def settle(self,seconds=1):
        end=time.monotonic()+seconds
        while time.monotonic()<end:rclpy.spin_once(self,timeout_sec=.05)
    def execute(self,group,constraint):
        goal=MoveGroup.Goal();r=goal.request
        r.group_name=group;r.pipeline_id='ompl';r.planner_id='RRTConnectkConfigDefault'
        r.num_planning_attempts=5;r.allowed_planning_time=10.0
        r.max_velocity_scaling_factor=0.2;r.max_acceleration_scaling_factor=0.2
        r.start_state.is_diff=True;r.goal_constraints=[constraint]
        goal.planning_options.plan_only=False;goal.planning_options.planning_scene_diff.is_diff=True
        goal.planning_options.planning_scene_diff.robot_state.is_diff=True
        sent=self.wait(self.move.send_goal_async(goal),30)
        if not sent.accepted:raise RuntimeError('MoveGroup rejected goal')
        result=self.wait(sent.get_result_async()).result
        if result.error_code.val!=1:raise RuntimeError(f'{group} plan/execute failed: {result.error_code.val}')
        if not result.planned_trajectory.joint_trajectory.points:raise RuntimeError('Empty planned trajectory')
        self.settle()
        final=result.planned_trajectory.joint_trajectory
        measured=dict(zip(self.raw.name,self.raw.position))
        error=max(abs(measured[n]-v) for n,v in zip(final.joint_names,final.points[-1].positions))
        tolerance=0.006 if 'gripper' in group else 0.04
        if error>tolerance:raise RuntimeError(f'{group}: physics tracking error {error}')
        self.results.append({'group':group,'points':len(final.points),'max_joint_error':error})
        print('PASS',self.results[-1],flush=True)
    def joints(self,group,targets):
        c=Constraints()
        for name,value in targets.items():c.joint_constraints.append(JointConstraint(joint_name=name,position=value,tolerance_above=.001,tolerance_below=.001,weight=1.0))
        self.execute(group,c)
    def pose(self):
        request=GetPositionFK.Request();request.header.frame_id='world'
        request.fk_link_names=['openarm_right_hand'];request.robot_state.joint_state=self.current
        positions=list(request.robot_state.joint_state.position)
        positions[request.robot_state.joint_state.name.index('openarm_right_joint4')]=0.35
        request.robot_state.joint_state.position=positions
        result=self.wait(self.fk.call_async(request))
        if result.error_code.val!=1:raise RuntimeError('FK failed')
        target=result.pose_stamped[0].pose
        c=Constraints()
        pc=PositionConstraint();pc.header.frame_id='world';pc.link_name='openarm_right_hand';pc.weight=1.0
        pc.constraint_region.primitives=[SolidPrimitive(type=SolidPrimitive.SPHERE,dimensions=[0.003])]
        region=Pose();region.position=target.position;region.orientation.w=1.0
        pc.constraint_region.primitive_poses=[region]
        oc=OrientationConstraint();oc.header.frame_id='world';oc.link_name='openarm_right_hand';oc.orientation=target.orientation
        oc.absolute_x_axis_tolerance=.03;oc.absolute_y_axis_tolerance=.03;oc.absolute_z_axis_tolerance=.03;oc.weight=1.0
        c.position_constraints=[pc];c.orientation_constraints=[oc]
        self.execute('right_arm',c)
        request.robot_state.joint_state=self.raw
        measured=self.wait(self.fk.call_async(request)).pose_stamped[0].pose
        error=math.sqrt(sum((getattr(target.position,k)-getattr(measured.position,k))**2 for k in ('x','y','z')))
        if error>.02:raise RuntimeError(f'Pose error {error} m')
        dot=abs(sum(getattr(target.orientation,k)*getattr(measured.orientation,k) for k in ('x','y','z','w')))
        angular_error=2*math.acos(min(1.0,dot))
        if angular_error>0.1:raise RuntimeError(f'Pose orientation error {angular_error} rad')
        self.results.append({'pose_position_error_m':error,'pose_orientation_error_rad':angular_error})
        print('PASS pose target',error,'m',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--existing',action='store_true');a=p.parse_args()
    child=None;log=None
    if not a.existing:
        log=open('/tmp/openarm-acceptance-stack.log','w')
        child=subprocess.Popen(['ros2','launch','/opt/openarm/app/simulation.launch.py','gui:=false'],stdout=log,stderr=subprocess.STDOUT)
    rclpy.init();node=Check()
    try:
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=.1)
            if node.current and node.raw and node.move.server_is_ready() and node.fk.service_is_ready() and node.valid.service_is_ready():break
            if child and child.poll() is not None:raise RuntimeError('Stack exited at startup')
        else:raise RuntimeError('Startup/discovery timeout')
        node.settle(3)
        v=GetStateValidity.Request();v.robot_state.joint_state=node.current
        valid=node.wait(node.valid.call_async(v))
        if not valid.valid:
            raise RuntimeError('Start state invalid: '+str([(c.contact_body_1,c.contact_body_2) for c in valid.contacts]))
        for side in ('right','left'):
            node.joints(side+'_arm',{f'openarm_{side}_joint{i}':(.2 if i==1 else 0.) for i in range(1,8)})
        node.pose()
        for side in ('right','left'):
            node.joints(side+'_gripper',{f'openarm_{side}_finger_joint{i}':.025 for i in (1,2)})
            node.joints(side+'_gripper',{f'openarm_{side}_finger_joint{i}':0. for i in (1,2)})
        report={'passed':True,'physics_feedback_samples':node.samples,'checks':node.results}
        Path('/tmp/openarm-acceptance.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    except Exception:
        if log:
            log.flush()
            print(Path(log.name).read_text()[-10000:])
        raise
    finally:
        node.destroy_node();rclpy.shutdown()
        if child:
            child.send_signal(2)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if log:log.close()

if __name__=='__main__':main()
