"""Pick, lift, replace a 100 g box using MoveIt and physical MuJoCo contact."""
import copy, fcntl, json, signal, sys, time, os
from pathlib import Path
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from std_srvs.srv import SetBool
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from geometry_msgs.msg import Pose
from trajectory_msgs.msg import JointTrajectoryPoint
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTolerance
from moveit_msgs.srv import GetMotionPlan, GetCartesianPath, GetPlanningScene, ApplyPlanningScene
from moveit_msgs.msg import Constraints, JointConstraint, PlanningScene, PlanningSceneComponents, AllowedCollisionEntry, AttachedCollisionObject, CollisionObject
from scene_cli import apply as apply_table

BOX='openarm_grasp_box'
HAND='openarm_right_hand'
FINGERS=['openarm_right_right_finger','openarm_right_left_finger']
ARM=[f'openarm_right_joint{i}' for i in range(1,8)]
PREGRASP=[.3968589323,.0578203197,.0345118925,1.1007402905,.0359803744,.0569160115,-1.49962056]

class Demo(Node):
    def __init__(self):
        super().__init__('openarm_pick_demo');self.joints=None;self.snapshot=None;self.received=0.;self.active_goal=None;self.saved_acm=None;self.attached=False;self.sync_paused=False
        self.create_subscription(JointState,'/joint_states',self.joint_update,10)
        self.create_subscription(String,'/openarm/sim_state',self.state_update,2)
    def joint_update(self,msg):self.joints=msg
    def state_update(self,msg):self.snapshot=json.loads(msg.data);self.received=time.monotonic()
    def pause(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:rclpy.spin_once(self,timeout_sec=.05)
    def wait(self,future,seconds=30):
        rclpy.spin_until_future_complete(self,future,timeout_sec=seconds)
        if not future.done():raise RuntimeError('ROS response timed out')
        return future.result()
    def call(self,kind,name,req):
        c=self.create_client(kind,name)
        try:
            if not c.wait_for_service(timeout_sec=15):raise RuntimeError('Service unavailable: '+name)
            return self.wait(c.call_async(req))
        finally:self.destroy_client(c)
    def toggle(self,name,value):
        req=SetBool.Request();req.data=value;r=self.call(SetBool,name,req)
        if not r.success:raise RuntimeError(r.message)
    def clear_objects(self):
        if self.snapshot is None:raise RuntimeError("Simulation state unavailable")
        for key,state in self.snapshot["objects"].items():
            if state["enabled"]:self.toggle(f"/openarm/objects/{key}/set_enabled",False)
    def scene(self,flags):
        req=GetPlanningScene.Request();req.components.components=flags
        return self.call(GetPlanningScene,'/get_planning_scene',req).scene
    def apply(self,scene):
        req=ApplyPlanningScene.Request();req.scene=scene
        if not self.call(ApplyPlanningScene,'/apply_planning_scene',req).success:raise RuntimeError('Planning scene rejected')
    def action(self,kind,name,goal):
        c=ActionClient(self,kind,name)
        try:
            if not c.wait_for_server(timeout_sec=15):raise RuntimeError('Action unavailable: '+name)
            h=self.wait(c.send_goal_async(goal));
            if not h.accepted:raise RuntimeError('Goal rejected: '+name)
            self.active_goal=h
            r=self.wait(h.get_result_async(),90)
            code=r.result.error_code
            value=code.val if hasattr(code,'val') else code
            expected=0
            if r.status!=4 or value!=expected:raise RuntimeError(f'{name}: status={r.status}, error={value} {getattr(r.result,"error_string","")}')
            self.active_goal=None
        finally:
            if self.active_goal:
                try:self.wait(self.active_goal.cancel_goal_async(),5)
                except Exception as exc:print('[WARN] Action cancellation: '+repr(exc),file=sys.stderr,flush=True)
                self.active_goal=None
            c.destroy()
    def execute(self,traj):
        # MoveIt computes and collision-checks the path; send it directly to the
        # controller so cancellation does not depend on ExecuteTrajectory's server.
        self.pause(.1)
        current=dict(zip(self.joints.name,self.joints.position))
        jt=traj.joint_trajectory
        if not jt.points or any(abs(current.get(name,99)-value)>.05 for name,value in zip(jt.joint_names,jt.points[0].positions)):
            raise RuntimeError('Trajectory start no longer matches the robot; replan')
        goal=FollowJointTrajectory.Goal();goal.trajectory=jt
        self.action(FollowJointTrajectory,'/right_arm_controller/follow_joint_trajectory',goal)
    def move_joints(self,target):
        req=GetMotionPlan.Request();q=req.motion_plan_request;q.group_name='right_arm';q.start_state.is_diff=True;q.allowed_planning_time=10.;q.num_planning_attempts=5;q.max_velocity_scaling_factor=.3;q.max_acceleration_scaling_factor=.3
        constraints=Constraints()
        for name,pos in zip(ARM,target):
            j=JointConstraint();j.joint_name=name;j.position=float(pos);j.tolerance_above=.001;j.tolerance_below=.001;j.weight=1.;constraints.joint_constraints.append(j)
        q.goal_constraints=[constraints];r=self.call(GetMotionPlan,'/plan_kinematic_path',req).motion_plan_response
        if r.error_code.val!=1:raise RuntimeError(f'MoveIt plan failed: {r.error_code.val}')
        self.execute(r.trajectory)
    def vertical(self,z):
        q=GetCartesianPath.Request();q.header.frame_id='world';q.start_state.is_diff=True;q.group_name='right_arm';q.link_name=HAND;q.max_step=.003;q.revolute_jump_threshold=.3;q.avoid_collisions=True;q.max_velocity_scaling_factor=.2;q.max_acceleration_scaling_factor=.2
        p=Pose();p.position.x=.30;p.position.y=-.174;p.position.z=z;p.orientation.x=1.;p.orientation.w=0.;q.waypoints=[p]
        q.cartesian_speed_limited_link=HAND;q.max_cartesian_speed=.04
        r=self.call(GetCartesianPath,'/compute_cartesian_path',q)
        if r.error_code.val!=1 or r.fraction<.999:raise RuntimeError(f'Cartesian path incomplete: {r.fraction:.1%}, error={r.error_code.val}')
        self.execute(r.solution)
    def grip(self,opening):
        goal=FollowJointTrajectory.Goal();names=[f'openarm_right_finger_joint{i}' for i in (1,2)];goal.trajectory.joint_names=names
        p=JointTrajectoryPoint();p.positions=[opening]*2;p.velocities=[0.]*2;p.time_from_start.sec=3;goal.trajectory.points=[p]
        # Closing stops at contact, not necessarily at the commanded zero opening.
        for name in names:
            t=JointTolerance();t.name=name;t.position=.035 if opening==0 else .005;goal.goal_tolerance.append(t)
            if opening==0:goal.path_tolerance.append(JointTolerance(name=name,position=.035))
        goal.goal_time_tolerance.sec=5
        self.action(FollowJointTrajectory,'/right_gripper_controller/follow_joint_trajectory',goal)
        self.pause(.5)
    def allow_contact(self):
        matrix=self.scene(PlanningSceneComponents.ALLOWED_COLLISION_MATRIX).allowed_collision_matrix;self.saved_acm=copy.deepcopy(matrix)
        for name in [BOX,*FINGERS,'openarm_demo_table']:
            if name not in matrix.entry_names:
                matrix.entry_names.append(name)
                for row in matrix.entry_values:row.enabled.append(False)
                matrix.entry_values.append(AllowedCollisionEntry(enabled=[False]*len(matrix.entry_names)))
        for finger in [*FINGERS,'openarm_demo_table']:
            i=matrix.entry_names.index(BOX);j=matrix.entry_names.index(finger);matrix.entry_values[i].enabled[j]=matrix.entry_values[j].enabled[i]=True
        s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.allowed_collision_matrix=matrix;self.apply(s)
    def pause_sync(self,paused):
        self.toggle('/openarm/objects/pause_sync',paused);self.sync_paused=paused;self.pause(.3)
    def attach(self):
        self.pause_sync(True)
        world=self.scene(PlanningSceneComponents.WORLD_OBJECT_GEOMETRY).world
        obj=next((o for o in world.collision_objects if o.id==BOX),None)
        if obj is None:raise RuntimeError('Box missing from MoveIt scene')
        item=AttachedCollisionObject();item.link_name=HAND;item.touch_links=[HAND,*FINGERS];item.object=obj;item.object.operation=CollisionObject.ADD
        s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.robot_state.attached_collision_objects=[item];self.apply(s);self.attached=True;self.pause(1.)
        # A final world removal clears a pose update queued before the sync node saw attachment.
        if any(o.id==BOX for o in self.scene(PlanningSceneComponents.WORLD_OBJECT_NAMES).world.collision_objects):
            remove=CollisionObject();remove.id=BOX;remove.operation=CollisionObject.REMOVE
            s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.world.collision_objects=[remove];self.apply(s)
    def detach(self):
        if not self.attached:return
        item=AttachedCollisionObject();item.link_name=HAND;item.object.id=BOX;item.object.operation=CollisionObject.REMOVE
        s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.robot_state.attached_collision_objects=[item];self.apply(s);self.attached=False;self.pause(.7);self.pause_sync(False)
    def position(self):
        self.pause(.25)
        if self.snapshot is None or time.monotonic()-self.received>2:raise RuntimeError('MuJoCo object state is stale')
        box=self.snapshot['objects']['box']
        if not box['enabled']:raise RuntimeError('Box was removed during demo')
        return box['position']
    def run(self):
        deadline=time.monotonic()+20
        while (self.joints is None or self.snapshot is None) and time.monotonic()<deadline:self.pause(.1)
        if self.joints is None or self.snapshot is None:raise RuntimeError('Start the simulation first')
        state=dict(zip(self.joints.name,self.joints.position))
        if any(abs(state.get(f'openarm_{side}_joint{i}',99))>.08 for side in ('left','right') for i in range(1,8)):
            raise RuntimeError('Start from home: use the GUI simulation restart button, then run this demo')
        if self.scene(PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS).robot_state.attached_collision_objects:raise RuntimeError('Remove existing attached objects before running demo')
        print('[1/8] Prepare worktable and box; remove bottle',flush=True)
        self.clear_objects();self.toggle('/openarm/set_obstacles',True);apply_table(self,True)
        q=SetParametersAtomically.Request();q.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=v)) for k,v in [('x',.30),('y',-.18),('yaw',0.)]]
        r=self.call(SetParametersAtomically,'/openarm/objects/box/place',q).result
        if not r.successful:raise RuntimeError(r.reason)
        self.pause(1.);initial=self.position()[2]
        print('[2/8] Open gripper',flush=True);self.grip(.03)
        print('[3/8] MoveIt approach above box',flush=True);self.move_joints(PREGRASP)
        self.allow_contact()
        print('[4/8] Descend along a collision-checked Cartesian path',flush=True);self.vertical(.29)
        print('[5/8] Close fingers using physical contact',flush=True);self.grip(0.)
        self.attach() # Planning representation only; never welds or teleports MuJoCo bodies.
        print('[6/8] Lift 10 cm and hold for 2 seconds',flush=True);self.vertical(.39)
        heights=[]
        for _ in range(8):heights.append(self.position()[2])
        rise=min(heights)-initial
        if rise<.09:raise RuntimeError(f'Physical grasp failed: sustained lift only {rise*100:.1f} cm')
        print(f'[PASS] Physical object stayed {rise*100:.1f} cm above its starting height',flush=True)
        print('[7/8] Lower and release on table',flush=True);self.vertical(.30);self.detach();self.grip(.03)
        print('[8/8] Retreat and return home',flush=True);self.vertical(.38)
        restored=PlanningScene();restored.is_diff=True;restored.robot_state.is_diff=True;restored.allowed_collision_matrix=self.saved_acm;self.apply(restored)
        self.move_joints([0.]*7)
        self.pause(1.);final=self.position()
        # A released box may rest on a different face: check its oriented bottom.
        w,x,y,z=self.snapshot['objects']['box']['quaternion_wxyz']
        extent=abs(2*(x*z-w*y))*.025+abs(2*(y*z+w*x))*.02+abs(1-2*(x*x+y*y))*.04
        if abs(final[2]-extent-.16)>.006 or abs(final[0]-.30)>.05 or abs(final[1]+.18)>.05:raise RuntimeError('Box did not settle back on the table')
        print('[DONE] Pick-and-place demo completed',flush=True)
    def cleanup(self):
        try:self.detach()
        finally:
            if self.sync_paused:self.pause_sync(False)
        if self.saved_acm is not None:
            s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.allowed_collision_matrix=self.saved_acm;self.apply(s)

def main():
    if os.environ.get('OPENARM_VERSION','1')=='2':
        from . import bimanual_demo
        sys.argv=[sys.argv[0],'--arms','right']
        return bimanual_demo.main()

    lock=open('/tmp/openarm-pick-demo.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('A grasp demo is already running',file=sys.stderr);return 1
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    # Keep ROS alive long enough to cancel the active action and restore the scene.
    def interrupted(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    node=Demo();code=0
    try:node.run()
    except KeyboardInterrupt:print('[STOP] Demo stopped. Restart the simulation before retrying.',flush=True);code=130
    except Exception as exc:print('[FAIL] '+str(exc),file=sys.stderr,flush=True);code=1
    finally:
        try:node.cleanup()
        except Exception as exc:print('[WARN] Scene cleanup: '+str(exc),file=sys.stderr)
        node.destroy_node();rclpy.shutdown();lock.close()
    return code
if __name__=='__main__':sys.exit(main())
