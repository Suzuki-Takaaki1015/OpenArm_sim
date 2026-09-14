"""Toggle fixed demo obstacles in MuJoCo and MoveIt; run while robot is stopped."""
import argparse
import rclpy
from rclpy.node import Node
from moveit_msgs.msg import CollisionObject, PlanningScene, PlanningSceneComponents
from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene
from shape_msgs.msg import SolidPrimitive
from geometry_msgs.msg import Pose
from std_srvs.srv import SetBool
from scene_objects import OBJECTS

def call(node, kind, name, request):
    client=node.create_client(kind,name)
    try:
        if not client.wait_for_service(timeout_sec=15):raise RuntimeError(f'Service unavailable: {name}')
        future=client.call_async(request)
        rclpy.spin_until_future_complete(node,future,timeout_sec=15)
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['on','off','status']);args=p.parse_args()
    rclpy.init();node=Node('openarm_scene_cli')
    try:
        ids={o['id'] for o in OBJECTS};before=present(node)
        if args.mode=='status':
            print('MoveIt demo objects:',', '.join(sorted(ids & before)) or 'off');return
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
        print(f'Obstacles {args.mode}: MuJoCo visibility/contact + MoveIt collision scene updated')
    finally:node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
