"""Isolated-container regression: real ROS services, truth markers and recovery."""
import json, time, os, statistics
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import SetBool
from visualization_msgs.msg import MarkerArray, Marker
from moveit_msgs.msg import PlanningScene, PlanningSceneComponents, CollisionObject, AttachedCollisionObject
from moveit_msgs.srv import GetPlanningScene, ApplyPlanningScene
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from scene_cli import call
from environment_assets import ITEMS

rclpy.init();node=Node('render_sync_regression')
latest={};markers={};times=[];latencies=[]
def truth(msg):
    latest.update(json.loads(msg.data));times.append(time.monotonic())
def display(msg):
    for m in msg.markers:
        if m.action==Marker.DELETE:markers.pop((m.ns,m.id),None)
        else:markers[m.ns,m.id]=m
node.create_subscription(String,'/openarm/object_state',truth,1)
node.create_subscription(MarkerArray,'/openarm/physical_objects',display,
    QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.01)
def toggle(path,enabled):
    response=call(node,SetBool,path,SetBool.Request(data=enabled));assert response.success,response.message
def scene():
    req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.WORLD_OBJECT_GEOMETRY|PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
    return call(node,GetPlanningScene,'/get_planning_scene',req).scene
def apply(sc):
    assert call(node,ApplyPlanningScene,'/apply_planning_scene',ApplyPlanningScene.Request(scene=sc)).success
def diff():
    s=PlanningScene(is_diff=True);s.robot_state.is_diff=True;return s
def wait_for(predicate,timeout=4):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        pump(.03)
        if predicate():return time.monotonic()-start
    raise AssertionError('state did not converge')
def present(key):return ITEMS[key]['id'] in {o.id for o in scene().world.collision_objects}
def set_object(key,enabled):
    start=time.monotonic();toggle('/openarm/objects/'+key+'/set_enabled',enabled)
    wait_for(lambda:present(key)==enabled)
    identifier=ITEMS[key]['id'];wait_for(lambda:((identifier,0) in markers)==enabled)
    delay=time.monotonic()-start;latencies.append(delay);print(key,enabled,'convergence_sec',round(delay,3),flush=True)
def place(key,x,y,support='worktable'):
    req=SetParametersAtomically.Request()
    req.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=v)) for k,v in [('x',float(x)),('y',float(y)),('yaw',.25)]]
    req.parameters.append(Parameter(name='support',value=ParameterValue(type=ParameterType.PARAMETER_STRING,string_value=support)))
    response=call(node,SetParametersAtomically,'/openarm/objects/'+key+'/place',req).result
    assert response.successful,response.reason
    identifier=ITEMS[key]['id']
    def matched():
        co=next((o for o in scene().world.collision_objects if o.id==identifier),None)
        return co and abs(co.pose.position.x-x)<.02 and abs(co.pose.position.y-y)<.02
    delay=wait_for(matched);latencies.append(delay);pump(.2)
    assert abs(markers[identifier,0].pose.position.x-x)<.08

try:
    wait_for(lambda: bool(latest), 15)
    assert latest,'truth topic absent'
    for key,state in latest['objects'].items():
        if state['enabled']:toggle('/openarm/objects/'+key+'/set_enabled',False)
    pump(.8);toggle('/openarm/set_obstacles',True)
    wait_for(lambda:'openarm_demo_table' in {o.id for o in scene().world.collision_objects})
    set_object('box',True);place('box',.30,-.18)
    # Server-side deletion must recover even though physical object did not move.
    sc=diff();sc.world.collision_objects=[CollisionObject(id=ITEMS['box']['id'],operation=CollisionObject.REMOVE)];apply(sc)
    wait_for(lambda:present('box'));print('PASS lost world object recovered',flush=True)
    # A wrong pose must recover: exercise periodic authoritative readback.
    co=next(o for o in scene().world.collision_objects if o.id==ITEMS['box']['id'])
    sc=diff();co.operation=CollisionObject.MOVE;co.pose.position.x=3.;co.primitives=[];co.primitive_poses=[];sc.world.collision_objects=[co];apply(sc)
    wait_for(lambda:abs(next(o for o in scene().world.collision_objects if o.id==co.id).pose.position.x-.30)<.02)
    print('PASS stale pose recovered',flush=True)
    # Logical attachment has a distinct owner; physical truth keeps moving.
    toggle('/openarm/objects/pause_sync',True);pump(.4)
    co=next(o for o in scene().world.collision_objects if o.id==ITEMS['box']['id'])
    attached=AttachedCollisionObject(link_name='openarm_right_hand',object=co);attached.object.operation=CollisionObject.ADD
    sc=diff();sc.robot_state.attached_collision_objects=[attached];apply(sc)
    toggle('/openarm/objects/pause_sync',False);pump(.8)
    set_object('box_left',True)
    # Keep the independently updated object away from the next box destination.
    # set_enabled chooses a random pose and can otherwise obstruct (.4, -.18).
    place('box_left',.4,.18)
    # Move physical box while the planning object remains attached.
    req=SetParametersAtomically.Request();req.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=v)) for k,v in [('x',.4),('y',-.18),('yaw',0.)]]
    result=call(node,SetParametersAtomically,'/openarm/objects/box/place',req).result
    assert result.successful,result.reason
    wait_for(lambda:abs(markers[ITEMS['box']['id'],0].pose.position.x-.4)<.02)
    actual=scene();assert co.id not in {o.id for o in actual.world.collision_objects}
    assert co.id in {o.object.id for o in actual.robot_state.attached_collision_objects}
    print('PASS attached ownership and independent physical display',flush=True)
    attached.object=CollisionObject(id=co.id,operation=CollisionObject.REMOVE)
    sc=diff();sc.robot_state.attached_collision_objects=[attached];apply(sc)
    wait_for(lambda:present('box'));set_object('box',False);set_object('box_left',False)
    for key in ('ycb_025_mug','opl_lemonade'):
        set_object(key,True);place(key,.40,0.);set_object(key,False)
    toggle('/openarm/set_obstacles',False)
    wait_for(lambda:'openarm_demo_table' not in {o.id for o in scene().world.collision_objects})
    place('opl_coffee_table',1.05,0.,'ground');place('opl_coffee_table',1.2,0.,'ground')
    set_object('opl_coffee_table',False)
    intervals=[b-a for a,b in zip(times,times[1:]) if b-a<.5]
    print(json.dumps(dict(version=os.environ.get('OPENARM_VERSION'),truth_interval_median=statistics.median(intervals),truth_interval_p95=sorted(intervals)[int(.95*len(intervals))],convergence_max=max(latencies),convergence_median=statistics.median(latencies))),flush=True)
    print('PASS real ROS synchronization regression',flush=True)
finally:
    node.destroy_node();rclpy.shutdown()
