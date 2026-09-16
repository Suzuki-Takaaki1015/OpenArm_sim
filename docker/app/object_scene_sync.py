"""Reconcile planning geometry and display physical truth independently."""
import copy
import asyncio
import json
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import SetBool
from geometry_msgs.msg import Pose, Point
from moveit_msgs.msg import PlanningScene, CollisionObject, PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene, ApplyPlanningScene
from shape_msgs.msg import SolidPrimitive, Mesh, MeshTriangle
from visualization_msgs.msg import Marker, MarkerArray
from environment_assets import ITEMS
from scene_objects import OBJECTS


@lru_cache(maxsize=4096)
def collision_mesh(filename):
    mesh = Mesh()
    for line in Path(filename).read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == 'v':
            mesh.vertices.append(Point(x=float(fields[1]), y=float(fields[2]), z=float(fields[3])))
        elif fields[0] == 'f':
            indices = [int(v.split('/')[0])-1 for v in fields[1:]]
            for i in range(1, len(indices)-1):
                mesh.triangles.append(MeshTriangle(vertex_indices=[indices[0], indices[i], indices[i+1]]))
    return mesh


def pose(values):
    p = Pose()
    p.position.x, p.position.y, p.position.z = map(float, values[:3])
    p.orientation.w, p.orientation.x, p.orientation.y, p.orientation.z = map(float, values[3:])
    return p


def values(p):
    return [p.position.x, p.position.y, p.position.z,
            p.orientation.w, p.orientation.x, p.orientation.y, p.orientation.z]


def same(a, b):
    if a is None or b is None:
        return a is b
    translation = max(abs(x-y) for x, y in zip(a[:3], b[:3]))
    rotation = min(max(abs(x-y) for x, y in zip(a[3:], b[3:])),
                   max(abs(x+y) for x, y in zip(a[3:], b[3:])))
    return translation < 1e-5 and rotation < 1e-5


def collision(identifier, description, position, operation):
    co = CollisionObject(id=identifier, operation=operation)
    co.header.frame_id = 'world'
    if position is None:
        return co
    co.pose = pose(position)
    if operation != CollisionObject.ADD:
        return co
    for geom in description['geoms']:
        if not geom.get('collision', True):
            continue
        local = pose(list(geom['pos']) + [1, 0, 0, 0])
        if geom['type'] == 'mesh':
            co.meshes.append(copy.deepcopy(collision_mesh(geom['mesh'])))
            co.mesh_poses.append(local)
        else:
            primitive = SolidPrimitive()
            if geom['type'] == 'box':
                primitive.type = SolidPrimitive.BOX
                primitive.dimensions = [2*v for v in geom['size']]
            else:
                primitive.type = SolidPrimitive.CYLINDER
                primitive.dimensions = [2*geom['size'][-1], geom['size'][0]]
            co.primitives.append(primitive)
            co.primitive_poses.append(local)
    return co


class SceneSync(Node):
    def __init__(self):
        super().__init__('openarm_object_scene_sync')
        self.descriptions = {o['id']: o for o in ITEMS.values()}
        self.descriptions.update({o['id']: dict(geoms=[dict(type='box', size=[v/2 for v in o['size']],
            pos=[0, 0, 0], rgba=o['rgba'])]) for o in OBJECTS})
        self.latest = None
        self.hidden_markers = {}
        self.received = 0.
        self.attached = set()
        self.known = {}
        self.pending = None
        self.pending_since = 0.
        self.next_query = 0.
        self.verified = False
        self.paused = False
        self.create_subscription(String, '/openarm/object_state', self.update, 1)
        self.markers = self.create_publisher(MarkerArray, '/openarm/physical_objects',
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.pause_group = MutuallyExclusiveCallbackGroup()
        self.create_service(SetBool, '/openarm/objects/pause_sync', self.pause_sync,
                            callback_group=self.pause_group)
        self.client = self.create_client(GetPlanningScene, '/get_planning_scene')
        self.apply = self.create_client(ApplyPlanningScene, '/apply_planning_scene')
        self.create_timer(.1, self.tick)

    async def pause_sync(self, request, response):
        # The grasp module pauses only its attachment transaction, never truth display.
        self.paused = request.data
        if self.paused and self.pending is not None:
            # Acknowledge only after the previous planning service completes.
            pending = self.pending
            try:
                await pending
                if pending.cancelled():
                    raise RuntimeError('Planning request timed out')
            except (asyncio.CancelledError, Exception):
                response.success = False
                response.message = 'Planning request did not finish; attachment must not start'
                return response
        self.next_query = 0.
        self.verified = False
        response.success = True
        response.message = 'Planning synchronization paused' if self.paused else 'Planning synchronization resumed'
        return response

    def update(self, msg):
        self.latest = json.loads(msg.data)
        self.received = time.monotonic()
        self.display()

    def desired(self):
        result = {}
        for key, description in ITEMS.items():
            state = self.latest['objects'].get(key)
            result[description['id']] = (state['position'] + state['quaternion_wxyz']) if state and state['enabled'] else None
        for obj in OBJECTS:
            result[obj['id']] = obj['position'] + [1, 0, 0, 0] if self.latest['obstacles'] else None
        return result

    def display(self):
        array = MarkerArray()
        for identifier, position in self.desired().items():
            for index, geom in enumerate(self.descriptions[identifier]['geoms']):
                if geom.get('rgba', [0, 0, 0, 0])[3] == 0:
                    continue
                if position is None:
                    # Reuse immutable tombstones in the complete retained frame.
                    # Most catalog objects are hidden: avoid rebuilding hundreds
                    # of ROS messages every tick without losing late-subscriber reset.
                    key = (identifier, index)
                    marker = self.hidden_markers.get(key)
                    if marker is None:
                        marker = Marker(ns=identifier, id=index, action=Marker.DELETE)
                        marker.header.frame_id = 'world'
                        self.hidden_markers[key] = marker
                    array.markers.append(marker)
                    continue
                marker = Marker(ns=identifier, id=index)
                marker.header.frame_id = 'world'
                marker.action = Marker.DELETE if position is None else Marker.ADD
                if position is not None:
                    marker.pose = pose(position)
                    w, x, y, z = position[3:]
                    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
                    marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = map(float,
                        np.array(position[:3]) + rotation @ np.array(geom['pos']))
                    marker.color.r, marker.color.g, marker.color.b, marker.color.a = map(float, geom['rgba'])
                    if geom['type'] == 'mesh':
                        marker.type = Marker.MESH_RESOURCE
                        marker.mesh_resource = Path(geom['mesh']).as_uri()
                        marker.mesh_use_embedded_materials = True
                        scale = [1., 1., 1.]
                    elif geom['type'] == 'box':
                        marker.type = Marker.CUBE
                        scale = [2*v for v in geom['size']]
                    elif geom['type'] == 'ellipsoid':
                        marker.type = Marker.SPHERE
                        scale = [2*v for v in geom['size']]
                    else:
                        marker.type = Marker.CYLINDER
                        scale = [2*geom['size'][0], 2*geom['size'][0], 2*geom['size'][-1]]
                    marker.scale.x, marker.scale.y, marker.scale.z = map(float, scale)
                array.markers.append(marker)
        self.markers.publish(array)

    def tick(self):
        now = time.monotonic()
        if self.pending is not None:
            if now-self.pending_since > 3:
                # Abandon a dead server's future; never acknowledge an unknown result.
                self.pending.cancel()
                self.pending = None
                self.verified = False
                self.next_query = 0.
            return
        if not self.latest or now-self.received > 2 or self.paused:
            return
        if not self.client.service_is_ready() or not self.apply.service_is_ready():
            self.verified = False
            return
        if not self.verified or now >= self.next_query:
            request = GetPlanningScene.Request()
            request.components.components = (PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS |
                PlanningSceneComponents.WORLD_OBJECT_GEOMETRY)
            self.start(self.client.call_async(request), self.readback)
            return
        desired = self.desired()
        changes = {}
        scene = PlanningScene(is_diff=True)
        scene.robot_state.is_diff = True
        for identifier, position in desired.items():
            if identifier in self.attached or same(position, self.known.get(identifier)):
                continue
            operation = (CollisionObject.REMOVE if position is None else
                         CollisionObject.MOVE if identifier in self.known else CollisionObject.ADD)
            scene.world.collision_objects.append(collision(identifier, self.descriptions[identifier], position, operation))
            changes[identifier] = position
        if not changes:
            return
        def applied(response):
            if not response.success:
                self.verified = False
                return
            for identifier, position in changes.items():
                if position is None:
                    self.known.pop(identifier, None)
                else:
                    self.known[identifier] = position
        self.start(self.apply.call_async(ApplyPlanningScene.Request(scene=scene)), applied)

    def start(self, future, callback):
        self.pending = future
        self.pending_since = time.monotonic()
        def done(result):
            if result is not self.pending:
                return
            self.pending = None
            try:
                callback(result.result())
            except Exception as exc:
                self.verified = False
                self.get_logger().warning(str(exc), throttle_duration_sec=5.)
        future.add_done_callback(done)

    def readback(self, response):
        scene = response.scene
        self.attached = {o.object.id for o in scene.robot_state.attached_collision_objects}
        self.known = {o.id: values(o.pose) for o in scene.world.collision_objects if o.id in self.descriptions}
        # Normalize legacy table geometry before MOVE to avoid doubling offsets.
        table_ids = {o['id'] for o in OBJECTS}
        for obj in scene.world.collision_objects:
            if obj.id in table_ids and (len(obj.primitive_poses) != 1 or
                    not same(values(obj.primitive_poses[0]), [0, 0, 0, 1, 0, 0, 0])):
                self.known.pop(obj.id, None)
        self.verified = True
        self.next_query = time.monotonic()+.5


def main():
    rclpy.init()
    node = SceneSync()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
