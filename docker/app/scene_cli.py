"""Toggle the worktable in MuJoCo and MoveIt; run while robot is stopped."""
import argparse
import json, math
import rclpy
from rclpy.node import Node
from moveit_msgs.msg import CollisionObject, PlanningScene, PlanningSceneComponents
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
from shape_msgs.msg import SolidPrimitive
from geometry_msgs.msg import Pose
from std_srvs.srv import SetBool, Trigger
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
from scene_objects import OBJECTS
def call(node, kind, name, request):
    client=node.create_client(kind,name)
    try:
        if not client.wait_for_service(timeout_sec=60):raise RuntimeError(f'Service unavailable: {name}')
        future=client.call_async(request)
        rclpy.spin_until_future_complete(node,future,timeout_sec=60)
        if not future.done():raise RuntimeError(f'Service timed out: {name}; check scene state before moving robot')
        return future.result()
    finally:node.destroy_client(client)
def present(node):
    request=GetPlanningScene.Request()
    request.components.components=PlanningSceneComponents.WORLD_OBJECT_NAMES
    scene=call(node,GetPlanningScene,'/get_planning_scene',request).scene
    return {obj.id for obj in scene.world.collision_objects}
def apply(node, enabled):
    scene=PlanningScene();scene.is_diff=True;scene.robot_state.is_diff=True
    for obj in OBJECTS:
        msg=CollisionObject();msg.id=obj['id'];msg.header.frame_id='world'
        msg.operation=CollisionObject.ADD if enabled else CollisionObject.REMOVE
        if enabled:
            shape=SolidPrimitive();shape.type=SolidPrimitive.BOX;shape.dimensions=obj['size']
            pose=Pose();pose.orientation.w=1.0
            pose.position.x,pose.position.y,pose.position.z=obj['position']
            msg.primitives=[shape];msg.primitive_poses=[pose]
        scene.world.collision_objects.append(msg)
    request=ApplyPlanningScene.Request();request.scene=scene
    if not call(node,ApplyPlanningScene,'/apply_planning_scene',request).success:
        raise RuntimeError('MoveIt rejected planning scene')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['on','off','status','box-on','box-off','box-reposition','bottle-on','bottle-off','bottle-reposition','camera-on','camera-off','box-place','bottle-place']);p.add_argument('--x',type=float);p.add_argument('--y',type=float);p.add_argument('--yaw',type=float,default=0);args=p.parse_args()
    if args.mode.endswith('-place') and (args.x is None or args.y is None or not all(math.isfinite(v) for v in [args.x,args.y,args.yaw])):p.error('Specify finite --x and --y (metres), and --yaw (degrees)')
    rclpy.init();node=Node('openarm_scene_cli')
    try:
        ids={o['id'] for o in OBJECTS};before=present(node)
        if args.mode=='status':
            scene=call(node,Trigger,'/openarm/scene/status',Trigger.Request())
            camera=call(node,Trigger,'/openarm/camera/status',Trigger.Request())
            print(json.dumps({'scene':json.loads(scene.message),'camera':json.loads(camera.message)}));return
        if args.mode.startswith('camera-'):
            req=SetBool.Request();req.data=args.mode=='camera-on'
            result=call(node,SetBool,'/openarm/camera/set_enabled',req)
            if not result.success:raise RuntimeError(result.message)
            print(result.message);return
        if args.mode.startswith(('box-','bottle-')):
            key,action=args.mode.split('-')
            if action!='off':
                req=SetBool.Request();req.data=True
                result=call(node,SetBool,'/openarm/set_obstacles',req)
                if not result.success:raise RuntimeError(result.message)
                apply(node,True)
            if action=='place':
                request=SetParametersAtomically.Request()
                request.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=float(v))) for k,v in [('x',args.x),('y',args.y),('yaw',math.radians(args.yaw))]]
                placed=call(node,SetParametersAtomically,f'/openarm/objects/{key}/place',request).result
                if not placed.successful:raise RuntimeError(placed.reason)
                print(placed.reason);return
            if action=='reposition':
                result=call(node,Trigger,f'/openarm/objects/{key}/reposition',Trigger.Request())
            else:
                req=SetBool.Request();req.data=action=='on'
                result=call(node,SetBool,f'/openarm/objects/{key}/set_enabled',req)
            if not result.success:raise RuntimeError(result.message)
            print(result.message);return
        enabled=args.mode=='on'
        request=SetBool.Request();request.data=enabled
        result=call(node,SetBool,'/openarm/set_obstacles',request)
        if not result.success:raise RuntimeError(result.message)
        try:apply(node,enabled)
        except Exception:
            request.data=ids.issubset(before)
            rollback=call(node,SetBool,'/openarm/set_obstacles',request)
            if not rollback.success:print('Rollback failed:',rollback.message)
            raise
        after=present(node)
        if (enabled and not ids.issubset(after)) or (not enabled and ids & after):raise RuntimeError('Scene verification failed')
        print(f'Worktable {args.mode}: MuJoCo visibility/contact + MoveIt collision scene updated')
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':
    try:main()
    except Exception as exc:
        import sys
        print(str(exc),file=sys.stderr);sys.exit(1)
