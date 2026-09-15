"""Publish physical object poses to MoveIt; attached objects are left to the member's grasp module."""
import json
import copy
from functools import lru_cache
from pathlib import Path
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool
from geometry_msgs.msg import Pose, Point
from moveit_msgs.msg import PlanningScene,CollisionObject,PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene
from shape_msgs.msg import SolidPrimitive, Mesh, MeshTriangle
from environment_assets import ITEMS

@lru_cache(maxsize=4096)
def collision_mesh(filename):
    mesh=Mesh()
    for line in Path(filename).read_text().splitlines():
        fields=line.split()
        if not fields:continue
        if fields[0]=='v':mesh.vertices.append(Point(x=float(fields[1]),y=float(fields[2]),z=float(fields[3])))
        elif fields[0]=='f':
            indices=[int(v.split('/')[0])-1 for v in fields[1:]]
            for i in range(1,len(indices)-1):mesh.triangles.append(MeshTriangle(vertex_indices=[indices[0],indices[i],indices[i+1]]))
    return mesh

class SceneSync(Node):
    def __init__(self):
        super().__init__('openarm_object_scene_sync')
        self.pub=self.create_publisher(PlanningScene,'/planning_scene',10)
        self.create_subscription(String,'/openarm/sim_state',self.update,2)
        self.attached=set();self.pending=None;self.sent=set();self.paused=False;self.poses={}
        self.create_service(SetBool,'/openarm/objects/pause_sync',self.pause_sync)
        self.client=self.create_client(GetPlanningScene,'/get_planning_scene')
        self.create_timer(.5,self.refresh_attached)
    def pause_sync(self,request,response):
        self.paused=request.data
        if not self.paused:self.sent.clear();self.poses.clear()
        response.success=True;response.message='Object synchronization paused' if self.paused else 'Object synchronization resumed';return response
    def refresh_attached(self):
        if not self.client.service_is_ready() or (self.pending and not self.pending.done()):return
        req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS | PlanningSceneComponents.WORLD_OBJECT_NAMES
        self.pending=self.client.call_async(req)
        def done(f):
            try:
                scene=f.result().scene
                self.attached={o.object.id for o in scene.robot_state.attached_collision_objects}
                self.sent.intersection_update({o.id for o in scene.world.collision_objects})
            except Exception as exc:self.get_logger().warning(str(exc))
        self.pending.add_done_callback(done)
    def update(self,msg):
        if self.paused:return
        snapshot=json.loads(msg.data);scene=PlanningScene();scene.is_diff=True;scene.robot_state.is_diff=True
        for key,obj in ITEMS.items():
            if obj['id'] in self.attached:continue
            state=snapshot['objects'][key]
            co=CollisionObject();co.id=obj['id'];co.header.frame_id='world'
            if not state['enabled']:
                if obj['id'] not in self.sent:continue
                co.operation=CollisionObject.REMOVE;self.sent.discard(obj['id'])
            else:
                pose_values=state['position']+state['quaternion_wxyz']
                old=self.poses.get(obj['id'])
                if obj['id'] in self.sent and old is not None and max(abs(a-b) for a,b in zip(old,pose_values))<1e-5:continue
                co.operation=CollisionObject.MOVE if obj['id'] in self.sent else CollisionObject.ADD
                self.sent.add(obj['id']);self.poses[obj['id']]=pose_values
                co.pose.position.x,co.pose.position.y,co.pose.position.z=state['position']
                w,x,y,z=state['quaternion_wxyz'];co.pose.orientation.w=w;co.pose.orientation.x=x;co.pose.orientation.y=y;co.pose.orientation.z=z
                # Bottle collision mesh is a conservative stack of cylinders.
                for geom in obj['geoms'] if co.operation==CollisionObject.ADD else []:
                    if not geom.get('collision',True):continue
                    if geom['type']=='mesh':
                        co.meshes.append(copy.deepcopy(collision_mesh(geom['mesh'])))
                        pose=Pose();pose.orientation.w=1.0;co.mesh_poses.append(pose);continue
                    primitive=SolidPrimitive();pose=Pose();pose.orientation.w=1.0
                    pose.position.x,pose.position.y,pose.position.z=map(float,geom['pos'])
                    if geom['type']=='box':primitive.type=SolidPrimitive.BOX;primitive.dimensions=[2*v for v in geom['size']]
                    else:
                        primitive.type=SolidPrimitive.CYLINDER
                        primitive.dimensions=[2*geom['size'][-1],geom['size'][0]]
                    co.primitives.append(primitive);co.primitive_poses.append(pose)
            scene.world.collision_objects.append(co)
        if scene.world.collision_objects:self.pub.publish(scene)

def main():
    rclpy.init();node=SceneSync()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
