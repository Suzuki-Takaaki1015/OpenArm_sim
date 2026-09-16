"""Run in an explicitly isolated container with Xvfb and its own persistent workspace."""
import copy,json,os,time,subprocess,sys,tkinter as tk
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter,ParameterValue,ParameterType
from moveit_msgs.srv import GetPlanningScene
from moveit_msgs.msg import PlanningSceneComponents
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from rclpy.action import ActionClient
from sensor_msgs.msg import JointState
from scene_panel import ScenePanel
from scene_presets import Store
from preset_cli import call
from environment_assets import ITEMS

rclpy.init();node=Node('presets_live_check');root=tk.Tk();panel=ScenePanel(root)
states=[]
node.create_subscription(JointState,'/joint_states',states.append,10)
def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        root.update();rclpy.spin_once(node,timeout_sec=.01)
def wait_panel():
    end=time.monotonic()+40
    while panel.busy and time.monotonic()<end:pump(.05)
    assert not panel.busy,'GUI timeout'
def gui(action,name,success=True):
    wait_panel();panel.preset_name.set(name);panel.named_preset(action);wait_panel()
    print('GUI',action,name,panel.state.get(),panel.detail.get(),flush=True)
    assert ('操作できませんでした' not in panel.state.get())==success
def cli(*args):
    result=subprocess.run([sys.executable,'/opt/openarm/app/scene_cli.py',*args],capture_output=True,text=True,timeout=140)
    assert result.returncode==0,result.stdout+result.stderr
def capture():
    response=call(node,Trigger,'/openarm/scene/capture',Trigger.Request())
    assert response.success,response.message
    return json.loads(response.message)
def restore(doc,success):
    request=SetParametersAtomically.Request(parameters=[Parameter(name='document',value=ParameterValue(type=ParameterType.PARAMETER_STRING,string_value=json.dumps(doc)))])
    result=call(node,SetParametersAtomically,'/openarm/scene/restore',request).result
    assert result.successful==success,result.reason
    return result.reason

pump(2);wait_panel()
cli('box-place','--x','.36','--y','-.2','--yaw','25')
cli('ycb_025_mug-place','--x','.55','--y','.2','--yaw','-30')
cli('opl_side_table-place','--x','1.5','--y','0','--yaw','20')
cli('opl_yakult-place','--x','1.5','--y','0','--support','opl_side_table:top')
cli('opl_clothes-place','--x','.58','--y','-.2','--yaw','10')
cli('opl_dining_table-place','--x','1.5','--y','1.5')
for index in range(2,13):
    x=1.5+((index-2)%4-1.5)*.25;y=1.5+((index-2)//4-1)*.21
    cli('opl_clothes_'+str(index)+'-place','--x',str(x),'--y',str(y),'--support','opl_dining_table:top')
pump(2)
gui('save','mixed')
store=Store();saved=store.load('mixed');original=store.path('mixed').read_bytes()
gui('save','mixed',False);assert store.path('mixed').read_bytes()==original
for key in ['box','ycb_025_mug','opl_yakult','opl_clothes']+['opl_clothes_'+str(i) for i in range(2,13)]+['opl_side_table','opl_dining_table']:cli(key+'-off')
cli('off');gui('load','mixed');pump(2)
current=capture()
for key,state in saved['objects'].items():
    actual=current['objects'][key]
    assert state['enabled']==actual['enabled'] and state['support']==actual['support'],key
    if state['enabled']:
        assert max(abs(a-b) for a,b in zip(state['pose'],actual['pose']))<.012,(key,state,actual)
request=GetPlanningScene.Request();request.components.components=PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
scene=call(node,GetPlanningScene,'/get_planning_scene',request).scene
world={o.id:o for o in scene.world.collision_objects}
for key in ('box','ycb_025_mug','opl_side_table','opl_yakult','opl_clothes'):
    p=world[ITEMS[key]['id']].pose.position
    assert max(abs(a-b) for a,b in zip([p.x,p.y,p.z],current['objects'][key]['pose'][:3]))<.012,key
assert 'openarm_demo_table' in world
print('PASS GUI mixed save/restore + ROS physics/MoveIt poses + overwrite protection',flush=True)
for mutate in [lambda d:d.update(version=2),lambda d:d.update(robot_model='2' if os.environ['OPENARM_VERSION']=='1' else '1'),lambda d:d.update(extra=1),lambda d:d['objects']['box'].update(enabled=1),lambda d:d['objects']['box']['pose'].__setitem__(0,float('nan')),lambda d:d['objects']['box']['pose'].__setitem__(0,6),lambda d:d['objects']['box'].update(support='missing:top'),lambda d:d['objects']['opl_side_table'].update(enabled=False)]:
    invalid=copy.deepcopy(saved);mutate(invalid);print('REJECT',restore(invalid,False),flush=True)
invalid=copy.deepcopy(saved);invalid['objects']['box']['pose']=saved['objects']['ycb_025_mug']['pose'][:]
print('COLLISION',restore(invalid,False),flush=True)
assert capture()['objects']['box']['enabled']

# A real controller action with a stationary hold remains an active trajectory.
pump(.5);joints=['openarm_right_joint'+str(i) for i in range(1,8)]
positions=dict(zip(states[-1].name,states[-1].position))
client=ActionClient(node,FollowJointTrajectory,'/right_arm_controller/follow_joint_trajectory')
assert client.wait_for_server(timeout_sec=5)
goal=FollowJointTrajectory.Goal();goal.trajectory.joint_names=joints
point=JointTrajectoryPoint(positions=[positions[n] for n in joints]);point.time_from_start.sec=5;goal.trajectory.points=[point]
future=client.send_goal_async(goal);rclpy.spin_until_future_complete(node,future,timeout_sec=5);handle=future.result();assert handle.accepted
pump(.3);print('TRAJECTORY',restore(saved,False),flush=True)
cancel=handle.cancel_goal_async();rclpy.spin_until_future_complete(node,cancel,timeout_sec=5);pump(1)
gui('load','mixed');print('PASS real hold action guard and recovery',flush=True)
panel.refresh_presets();assert 'mixed' in panel.preset_choices['values']
root.destroy();node.destroy_node();rclpy.shutdown()
print('PASS LIVE '+os.environ['OPENARM_VERSION'],flush=True)
