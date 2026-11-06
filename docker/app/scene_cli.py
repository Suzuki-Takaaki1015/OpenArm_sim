"""Toggle the worktable in MuJoCo and MoveIt; run while robot is stopped."""
import argparse
import os
import socket
import time
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
from environment_assets import ITEMS
def call(node, kind, name, request, timeout=60):
    client=node.create_client(kind,name)
    try:
        if not client.wait_for_service(timeout_sec=timeout):raise RuntimeError(f'Service unavailable: {name}')
        future=client.call_async(request)
        rclpy.spin_until_future_complete(node,future,timeout_sec=timeout)
        if not future.done():raise RuntimeError(f'Service timed out: {name}; check scene state before moving robot')
        return future.result()
    finally:node.destroy_client(client)
def start_lidar(node, allow_restart=True):
    status_service='/openarm/lidar/status'
    def status(timeout):
        reply=call(node,Trigger,status_service,Trigger.Request(),timeout=timeout)
        if not reply.success:raise RuntimeError(reply.message)
        return json.loads(reply.message)

    state=status(8)
    restarting=False
    if not state['mounted']:
        if not allow_restart:
            raise RuntimeError('MID-360Sの自動装着には再起動が必要です。記録・デモを停止してから配信を開始してください。')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(30)  # A concurrent restart can take up to 25 seconds to stop ROS.
            client.connect('/tmp/openarm-supervisor.sock')
            client.sendall(b'lidar-start\n')
            reply=client.recv(64).strip()
        if reply not in (b'restarting',b'mounted'):
            raise RuntimeError('MID-360Sの自動装着を開始できませんでした: '+reply.decode(errors='replace'))
        restarting=reply==b'restarting'
    # A newly mounted stack starts its own scanner. Never enable the old detached node.
    # On an already mounted stack SetBool is only needed if streaming was stopped.
    deadline=time.monotonic()+140
    requested=restarting
    while time.monotonic()<deadline:
        if state['mounted']:
            if state['enabled'] and state.get('last_sim_time') is not None:
                return 'MID-360S 点群配信中'
            if not state['enabled']:
                if requested:
                    raise RuntimeError(state.get('error') or 'MID-360Sの配信が停止しました。')
                result=call(node,SetBool,'/openarm/lidar/set_enabled',SetBool.Request(data=True),timeout=8)
                if not result.success:raise RuntimeError(result.message)
                requested=True
        time.sleep(.4)
        try:state=status(2)
        except RuntimeError:
            # During a restart discovery can still advertise the old service.
            state={"mounted":False}
            continue
    raise RuntimeError('MID-360Sの初回点群を確認できませんでした。装着状態とシミュレーションログを確認してください。')

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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['on','off','status','camera-on','camera-off','lidar-on','lidar-off','lidar-light','lidar-standard','lidar-dense']+[key+'-'+action for key in ITEMS for action in ('on','off','reposition','place')]);p.add_argument('--x',type=float);p.add_argument('--y',type=float);p.add_argument('--yaw',type=float,default=0);p.add_argument('--support',default='worktable');p.add_argument('--no-restart',action='store_true');args=p.parse_args()
    if args.mode.endswith('-place') and (args.x is None or args.y is None or not all(math.isfinite(v) for v in [args.x,args.y,args.yaw])):p.error('Specify finite --x and --y (metres), and --yaw (degrees)')
    rclpy.init();node=Node('openarm_scene_cli')
    try:
        if args.mode in ('lidar-light','lidar-standard','lidar-dense'):
            count={'lidar-light':800,'lidar-standard':8000,'lidar-dense':40000}[args.mode]
            req=SetParametersAtomically.Request()
            req.parameters=[Parameter(name='rays_per_frame',value=ParameterValue(type=ParameterType.PARAMETER_INTEGER,integer_value=count))]
            result=call(node,SetParametersAtomically,'/openarm_mid360s_sim/set_parameters_atomically',req).result
            if not result.successful:raise RuntimeError(result.reason)
            print(f'LiDAR: {count:,} rays/cloud. Actual cloud rate depends on CPU and simulation speed.');return
        if args.mode=='lidar-on':
            print(start_lidar(node,allow_restart=not args.no_restart));return
        if args.mode=='lidar-off':
            req=SetBool.Request();req.data=False
            result=call(node,SetBool,'/openarm/lidar/set_enabled',req)
            if not result.success:raise RuntimeError(result.message)
            print(result.message);return
        if os.getenv('HAPPY_MOBILE') == '1' and args.mode not in ('status','camera-on','camera-off'):
            raise RuntimeError('機体全体モードの家具と机上物体は生活環境エディターで配置してください。')
        if args.mode=='status':
            scene=call(node,Trigger,'/openarm/scene/status',Trigger.Request())
            camera=call(node,Trigger,'/openarm/camera/status',Trigger.Request())
            try:lidar=json.loads(call(node,Trigger,'/openarm/lidar/status',Trigger.Request(),timeout=2).message)
            except Exception as exc:lidar={'enabled':False,'error':str(exc)}
            print(json.dumps({'lidar':lidar,'scene':json.loads(scene.message),'camera':json.loads(camera.message)}));return
        if args.mode.startswith('camera-'):
            req=SetBool.Request();req.data=args.mode=='camera-on'
            result=call(node,SetBool,'/openarm/camera/set_enabled',req)
            if not result.success:raise RuntimeError(result.message)
            print(result.message);return
        ids={o['id'] for o in OBJECTS};before=present(node)
        if args.mode.rsplit('-',1)[0] in ITEMS:
            key,action=args.mode.rsplit('-',1)
            if action!='off' and not ITEMS[key].get('furniture') and args.support=='worktable':
                req=SetBool.Request();req.data=True
                result=call(node,SetBool,'/openarm/set_obstacles',req)
                if not result.success:raise RuntimeError(result.message)
                apply(node,True)
            if action=='reposition' and args.support!='worktable':
                req=SetParametersAtomically.Request()
                req.parameters=[Parameter(name='support',value=ParameterValue(type=ParameterType.PARAMETER_STRING,string_value=args.support))]
                result=call(node,SetParametersAtomically,f'/openarm/objects/{key}/place',req).result
                if not result.successful:raise RuntimeError(result.reason)
                print(result.reason);return
            if action=='place':
                request=SetParametersAtomically.Request()
                request.parameters=[Parameter(name=k,value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=float(v))) for k,v in [('x',args.x),('y',args.y),('yaw',math.radians(args.yaw))]]
                request.parameters.append(Parameter(name='support',value=ParameterValue(type=ParameterType.PARAMETER_STRING,string_value=args.support)))
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
