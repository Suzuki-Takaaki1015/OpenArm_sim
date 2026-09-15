"""Publish physical object poses to MoveIt; attached objects are left to the member's grasp module."""
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool
from geometry_msgs.msg import Pose
from moveit_msgs.msg import PlanningScene,CollisionObject,PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene
from shape_msgs.msg import SolidPrimitive
from environment_assets import ITEMS

class SceneSync(Node):
    def __init__(self):
        super().__init__('openarm_object_scene_sync')
        self.pub=self.create_publisher(PlanningScene,'/planning_scene',10)
        self.create_subscription(String,'/openarm/sim_state',self.update,2)
        self.attached=set();self.pending=None;self.sent=set();self.paused=False
        self.create_service(SetBool,'/openarm/objects/pause_sync',self.pause_sync)
        self.client=self.create_client(GetPlanningScene,'/get_planning_scene')
        self.create_timer(.5,self.refresh_attached)
    def pause_sync(self,request,response):
        self.paused=request.data;response.success=True;response.message='Object synchronization paused' if self.paused else 'Object synchronization resumed';return response
    def refresh_attached(self):
        if not self.client.service_is_ready() or (self.pending and not self.pending.done()):return
        req=GetPlanningScene.Request();req.components.components=PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        self.pending=self.client.call_async(req)
        def done(f):
            try:self.attached={o.object.id for o in f.result().scene.robot_state.attached_collision_objects}
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
                co.operation=CollisionObject.ADD;self.sent.add(obj['id'])
                co.pose.position.x,co.pose.position.y,co.pose.position.z=state['position']
                w,x,y,z=state['quaternion_wxyz'];co.pose.orientation.w=w;co.pose.orientation.x=x;co.pose.orientation.y=y;co.pose.orientation.z=z
                # Bottle collision mesh is a conservative stack of cylinders.
                for geom in obj['geoms']:
                    primitive=SolidPrimitive();pose=Pose();pose.orientation.w=1.0
                    pose.position.x,pose.position.y,pose.position.z=map(float,geom['pos'])
                    if geom['type']=='box':primitive.type=SolidPrimitive.BOX;primitive.dimensions=[2*v for v in geom['size']]
                    else:
                        primitive.type=SolidPrimitive.CYLINDER
                        primitive.dimensions=[2*geom['size'][-1],geom['size'][0]]
                    co.primitives.append(primitive);co.primitive_poses.append(pose)
            scene.world.collision_objects.append(co)
        self.pub.publish(scene)

def main():
    rclpy.init();node=SceneSync()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
