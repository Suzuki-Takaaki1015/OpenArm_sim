"""Synchronized left/right grasp demo using MoveIt plans and physical contacts."""
import argparse, bisect, math, os
from .grasp_demo import *
from moveit_msgs.srv import GetStateValidity
from trajectory_msgs.msg import JointTrajectory
from builtin_interfaces.msg import Duration

SIDES={
 'right':dict(key='box',object='openarm_grasp_box',y=-.18,hand_y=-.174,pre=PREGRASP),
 'left':dict(key='box_left',object='openarm_grasp_box_left',y=.18,hand_y=.186,
             pre=[-.3975221472,-.0649792659,-.0382371851,1.0988613001,-.0405829185,-.0635393631,1.4989152352])}

V2=os.environ.get('OPENARM_VERSION','1')=='2'
X=.29 if V2 else .30
GRASP_Z=.38 if V2 else .29
LIFT_Z=GRASP_Z+.10
PRE_Z=.48 if V2 else .38
def finger_links(side):
    return [f'openarm_{side}_{f}' for f in (('ee_inner_finger','ee_outer_finger') if V2 else ('left_finger','right_finger'))]
if V2:
    SIDES['right'].update(hand_y=-.18,pre=[.5073065009,.4915191421,-.7337599241,1.1678323865,-.7771141993,.3661480740,1.3280855189])
    SIDES['left'].update(hand_y=.18,pre=[-.5073065009,-.4915191421,.7337599241,1.1678323865,.7771141993,-.3661480740,-1.3280855189])

def seconds(t):return t.sec+t.nanosec*1e-9
def duration(t):return Duration(sec=int(t),nanosec=int((t-int(t))*1e9))

class BimanualDemo(Demo):
    def __init__(self,sides):
        super().__init__();self.sides=sides;self.goals=[];self.attachments=[];self.action_clients={}
        for side in sides:
            for part in ('arm','gripper'):
                key=(side,part);c=ActionClient(self,FollowJointTrajectory,f'/{side}_{part}_controller/follow_joint_trajectory');self.action_clients[key]=c
                if not c.wait_for_server(timeout_sec=20):raise RuntimeError(f'Controller unavailable: {key}')
    def execute_together(self,trajectories,closing=False):
        # Stretch to the same duration, then use a shared simulation-time start stamp.
        longest=max(seconds(t.points[-1].time_from_start) for t in trajectories.values())
        goals={}
        for key,original in trajectories.items():
            t=copy.deepcopy(original);scale=longest/seconds(t.points[-1].time_from_start)
            for p in t.points:
                p.time_from_start=duration(seconds(p.time_from_start)*scale)
                p.velocities=[v/scale for v in p.velocities];p.accelerations=[v/(scale*scale) for v in p.accelerations]
            goal=FollowJointTrajectory.Goal();goal.trajectory=t
            if key[1]=='gripper':
                for name in t.joint_names:
                    goal.goal_tolerance.append(JointTolerance(name=name,position=(.8 if closing else .04) if V2 else (.035 if closing else .005)))
                    if closing:goal.path_tolerance.append(JointTolerance(name=name,position=.8 if V2 else .035))
            goals[key]=goal
        self.pause(.1)
        stamp=copy.deepcopy(self.joints.header.stamp);stamp.sec+=1
        for goal in goals.values():goal.trajectory.header.stamp=stamp
        try:
            pending=[self.action_clients[key].send_goal_async(goal) for key,goal in goals.items()]
            for f in pending:
                h=self.wait(f)
                if not h.accepted:raise RuntimeError('A synchronized goal was rejected')
                self.goals.append(h)
            pending=[h.get_result_async() for h in self.goals]
            deadline=time.monotonic()+120
            while not all(f.done() for f in pending):
                if time.monotonic()>deadline:raise RuntimeError('Synchronized motion timed out')
                rclpy.spin_once(self,timeout_sec=.05)
                for f in pending:
                    if f.done() and (f.result().status!=4 or f.result().result.error_code!=0):raise RuntimeError('Controller failed: '+str(f.result().result))
            for f in pending:
                if f.result().status!=4 or f.result().result.error_code!=0:raise RuntimeError('Controller failed: '+str(f.result().result))
            self.goals=[]
        finally:
            for h in self.goals:
                try:self.wait(h.cancel_goal_async(),5)
                except Exception as exc:print('[WARN] Cancel: '+str(exc),flush=True)
            self.goals=[]
    def arm_names(self,side):return [f'openarm_{side}_joint{i}' for i in range(1,8)]
    def move_both(self,home=False):
        q=GetMotionPlan.Request();r=q.motion_plan_request;r.group_name='both_arms' if len(self.sides)==2 else self.sides[0]+'_arm';r.start_state.is_diff=True;r.allowed_planning_time=10.;r.num_planning_attempts=5;r.max_velocity_scaling_factor=.3;r.max_acceleration_scaling_factor=.3
        c=Constraints()
        for side in self.sides:
            for name,value in zip(self.arm_names(side),[0.]*7 if home else SIDES[side]['pre']):c.joint_constraints.append(JointConstraint(joint_name=name,position=float(value),tolerance_above=.001,tolerance_below=.001,weight=1.))
        r.goal_constraints=[c]
        for attempt in range(5):
            out=self.call(GetMotionPlan,'/plan_kinematic_path',q).motion_plan_response
            if out.error_code.val==1:break
            print(f'[CHECK] Replanning rejected path ({attempt+1}/5, code {out.error_code.val})',flush=True)
        if out.error_code.val!=1:raise RuntimeError('Arm planning failed: '+str(out.error_code.val))
        paths={};t=out.trajectory.joint_trajectory
        for side in self.sides:
            path=copy.deepcopy(t);path.joint_names=self.arm_names(side);indices=[t.joint_names.index(name) for name in path.joint_names]
            for p in path.points:
                for field in ('positions','velocities','accelerations','effort'):
                    values=getattr(p,field)
                    if values:setattr(p,field,[values[i] for i in indices])
            paths[(side,'arm')]=path
        self.execute_together(paths)
    def vertical_both(self,z):
        paths={}
        for side in self.sides:
            q=GetCartesianPath.Request();q.header.frame_id='world';q.start_state.is_diff=True;q.group_name=side+'_arm';q.link_name=f'openarm_{side}_hand';q.max_step=.003;q.revolute_jump_threshold=.3;q.avoid_collisions=True;q.max_velocity_scaling_factor=.2;q.max_acceleration_scaling_factor=.2;q.cartesian_speed_limited_link=q.link_name;q.max_cartesian_speed=.04
            p=Pose();p.position.x=X;p.position.y=SIDES[side]['hand_y'];p.position.z=z;p.orientation.x=math.sqrt(.5) if V2 else 1.;p.orientation.y=(math.sqrt(.5) if side=='right' else -math.sqrt(.5)) if V2 else 0.;p.orientation.w=0.;q.waypoints=[p]
            out=self.call(GetCartesianPath,'/compute_cartesian_path',q)
            if out.error_code.val!=1 or out.fraction<.999:raise RuntimeError(f'{side}: incomplete Cartesian path {out.fraction:.1%}')
            paths[(side,'arm')]=out.solution.joint_trajectory
        # Validate the synchronized pair, not just each arm against a stationary peer.
        for fraction in [i/50 for i in range(51)]:
            req=GetStateValidity.Request();req.robot_state.is_diff=True;req.group_name='both_arms'
            for path in paths.values():
                times=[seconds(p.time_from_start) for p in path.points];t=fraction*times[-1];i=min(max(bisect.bisect_right(times,t)-1,0),len(times)-2);w=(t-times[i])/max(times[i+1]-times[i],1e-9)
                values=[a+(b-a)*w for a,b in zip(path.points[i].positions,path.points[i+1].positions)]
                req.robot_state.joint_state.name.extend(path.joint_names);req.robot_state.joint_state.position.extend(values)
            checked=self.call(GetStateValidity,'/check_state_validity',req)
            if not checked.valid:raise RuntimeError('Synchronized Cartesian collision: '+str([(c.contact_body_1,c.contact_body_2,c.depth) for c in checked.contacts]))
        self.execute_together(paths)
    def grip_both(self,opening):
        paths={}
        for side in self.sides:
            t=JointTrajectory();t.joint_names=[f'openarm_{side}_finger_joint{i}' for i in ((1,) if V2 else (1,2))];p=JointTrajectoryPoint();p.positions=[((.65 if side=='left' else -.65) if opening else 0.) if V2 else opening]*len(t.joint_names);p.velocities=[0.]*len(t.joint_names);p.time_from_start.sec=3;t.points=[p];paths[(side,'gripper')]=t
        self.execute_together(paths,closing=opening==0.);self.pause(.5)
    def allow_contacts(self):
        matrix=self.scene(PlanningSceneComponents.ALLOWED_COLLISION_MATRIX).allowed_collision_matrix;self.saved_acm=copy.deepcopy(matrix)
        names=['openarm_demo_table']+[v['object'] for v in SIDES.values()]+[link for side in SIDES for link in finger_links(side)]
        for name in names:
            if name not in matrix.entry_names:
                matrix.entry_names.append(name)
                for row in matrix.entry_values:row.enabled.append(False)
                matrix.entry_values.append(AllowedCollisionEntry(enabled=[False]*len(matrix.entry_names)))
        for side,cfg in SIDES.items():
            for other in SIDES:
                for finger in finger_links(other):
                    i=matrix.entry_names.index(cfg['object']);j=matrix.entry_names.index(finger);matrix.entry_values[i].enabled[j]=matrix.entry_values[j].enabled[i]=(side==other and side in self.sides)
            i=matrix.entry_names.index(cfg['object']);j=matrix.entry_names.index('openarm_demo_table');matrix.entry_values[i].enabled[j]=matrix.entry_values[j].enabled[i]=side in self.sides
        s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True;s.allowed_collision_matrix=matrix;self.apply(s)
        actual=self.scene(PlanningSceneComponents.ALLOWED_COLLISION_MATRIX).allowed_collision_matrix
        for side in self.sides:
            for finger in finger_links(side):
                i=actual.entry_names.index(SIDES[side]['object']);j=actual.entry_names.index(finger);assert actual.entry_values[i].enabled[j]
                other='left' if side=='right' else 'right'
                k=actual.entry_names.index(finger.replace(f'openarm_{side}_',f'openarm_{other}_',1));assert not actual.entry_values[i].enabled[k]
        print('[OK] Left/right contact rules verified; cross-arm object contact remains forbidden',flush=True)
    def attach_both(self):
        self.pause_sync(True)
        world=self.scene(PlanningSceneComponents.WORLD_OBJECT_GEOMETRY).world;s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True
        for side in self.sides:
            obj=next(o for o in world.collision_objects if o.id==SIDES[side]['object']);a=AttachedCollisionObject();a.link_name=f'openarm_{side}_hand';a.touch_links=[a.link_name,*finger_links(side)];a.object=obj;a.object.operation=CollisionObject.ADD;s.robot_state.attached_collision_objects.append(a)
        self.apply(s);self.attachments=list(s.robot_state.attached_collision_objects);self.pause(1.)
        names={o.id for o in self.scene(PlanningSceneComponents.WORLD_OBJECT_NAMES).world.collision_objects};s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True
        for a in self.attachments:
            if a.object.id in names:s.world.collision_objects.append(CollisionObject(id=a.object.id,operation=CollisionObject.REMOVE))
        if s.world.collision_objects:self.apply(s)
    def detach(self):
        if not self.attachments:return
        s=PlanningScene();s.is_diff=True;s.robot_state.is_diff=True
        for a in self.attachments:
            item=AttachedCollisionObject();item.link_name=a.link_name;item.object.id=a.object.id;item.object.operation=CollisionObject.REMOVE;s.robot_state.attached_collision_objects.append(item)
        self.apply(s);self.attachments=[];self.pause(1.);self.pause_sync(False)
    def object_state(self,side):
        if self.snapshot is None or time.monotonic()-self.received>2:raise RuntimeError('Stale MuJoCo state')
        result=self.snapshot['objects'][SIDES[side]['key']]
        if not result['enabled']:raise RuntimeError('Object removed while running demo')
        return result
    def run(self):
        deadline=time.monotonic()+20
        while (self.joints is None or self.snapshot is None) and time.monotonic()<deadline:self.pause(.1)
        if self.joints is None or self.snapshot is None:raise RuntimeError('Start simulation first')
        positions=dict(zip(self.joints.name,self.joints.position))
        if any(abs(positions.get(name,99))>.08 for side in SIDES for name in self.arm_names(side)):raise RuntimeError('Use the simulation restart button before running this demo')
        if self.scene(PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS).robot_state.attached_collision_objects:raise RuntimeError('Existing attached objects must be cleared first')
        print('[1/8] Prepare two boxes and worktable',flush=True)
        self.clear_objects()
        self.toggle('/openarm/set_obstacles',True);apply_table(self,True)
        for side in self.sides:
            cfg=SIDES[side];q=SetParametersAtomically.Request();q.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=v)) for k,v in [('x',X),('y',cfg['y']),('yaw',0.)]];r=self.call(SetParametersAtomically,f'/openarm/objects/{cfg["key"]}/place',q).result
            if not r.successful:raise RuntimeError(r.reason)
        self.pause(1.);initial={side:self.object_state(side)['position'][2] for side in self.sides}
        print('[2/8] Open grippers together',flush=True);self.grip_both(.03)
        print('[3/8] Plan both arms jointly and approach together',flush=True);self.move_both()
        self.allow_contacts()
        print('[4/8] Descend together',flush=True);self.vertical_both(GRASP_Z)
        print('[5/8] Close grippers together',flush=True);self.grip_both(0.);self.attach_both()
        print('[6/8] Lift 10 cm together and hold',flush=True);self.vertical_both(LIFT_Z)
        rises={side:[] for side in self.sides}
        for _ in range(12):
            self.pause(.25)
            for side in self.sides:rises[side].append(self.object_state(side)['position'][2]-initial[side])
        for side,values in rises.items():
            if min(values)<.09 or max(values)-min(values)>.005:raise RuntimeError(f'{side}: unstable lift, min={min(values)*100:.1f} cm')
            print(f'[PASS] {side}: sustained lift {min(values)*100:.1f} cm, drift {(max(values)-min(values))*1000:.2f} mm',flush=True)
        print('[7/8] Replace boxes on table',flush=True);self.vertical_both(GRASP_Z+.01);self.detach();self.grip_both(.03)
        print('[8/8] Retreat and return home together',flush=True);self.vertical_both(PRE_Z)
        # Once clear, restore normal object collision checks before planning home.
        # Keeping grasp-only contact permission here lets a return path hit a box.
        restored=PlanningScene();restored.is_diff=True;restored.robot_state.is_diff=True;restored.allowed_collision_matrix=self.saved_acm;self.apply(restored)
        # Fold empty fingers after leaving the box. Open v2 fingers can touch
        # the chest while the arm follows an otherwise valid return path.
        self.grip_both(0.)
        self.move_both(home=True);self.pause(1.)
        for side in self.sides:
            obj=self.object_state(side);w,x,y,z=obj['quaternion_wxyz'];extent=abs(2*(x*z-w*y))*.025+abs(2*(y*z+w*x))*.02+abs(1-2*(x*x+y*y))*.04
            if abs(obj['position'][2]-extent-.16)>.006:raise RuntimeError(side+': box did not return to table')
        print('[DONE] Synchronized grasp demo completed',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--arms',choices=['both','left','right'],default='both');args=parser.parse_args()
    lock=open('/tmp/openarm-pick-demo.lock','w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:print('Another grasp demo is running',file=sys.stderr);return 1
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    def interrupted(*_):raise KeyboardInterrupt()
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    node=None;code=0
    try:node=BimanualDemo(['right','left'] if args.arms=='both' else [args.arms]);node.run()
    except KeyboardInterrupt:print('[STOP] Demo stopped; restart simulation before retrying.',flush=True);code=130
    except Exception as exc:print('[FAIL] '+str(exc),file=sys.stderr,flush=True);code=1
    finally:
        if node:
            try:node.cleanup()
            except Exception as exc:print('[WARN] Cleanup: '+str(exc),flush=True)
            node.destroy_node()
        rclpy.shutdown();lock.close()
    return code
if __name__=='__main__':sys.exit(main())
