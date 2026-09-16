"""Drop a real MuJoCo body in an explicitly isolated ROS test container."""
import os,signal,time,json
from pathlib import Path
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1','Use only an isolated test container'
import rclpy,mujoco
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool
from visualization_msgs.msg import MarkerArray,Marker
from moveit_msgs.srv import GetPlanningScene
from moveit_msgs.msg import PlanningSceneComponents
from bridge import Bridge
from scene_cli import call
rclpy.init();probe=Node('drop_probe');latest={}
probe.create_subscription(String,'/openarm/sim_state',lambda m:latest.update(json.loads(m.data)),1)
end=time.monotonic()+15
while not latest and time.monotonic()<end:rclpy.spin_once(probe,timeout_sec=.1)
assert latest
original=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:args=(p/'cmdline').read_bytes().split(b'\0')
    except OSError:continue
    if b'/opt/openarm/app/bridge.py' in args:original.append(int(p.name))
assert len(original)==1,original
probe.destroy_node();os.kill(original[0],signal.SIGSTOP)
node=None
try:
    node=Bridge();node.sim.data.time=latest['time']+.01
    response=node.set_obstacles(SetBool.Request(data=True),SetBool.Response());assert response.success
    node.objects.set_enabled('box',True,reposition=True,pose=(.55,0,0))
    m,d=node.sim.model,node.sim.data;bid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'openarm_grasp_box')
    adr=int(m.jnt_qposadr[m.body_jntadr[bid]]);d.qpos[adr+2]+=.35;mujoco.mj_forward(m,d)
    physical=[];display=[]
    def markers(msg):
        for marker in msg.markers:
            if marker.ns=='openarm_grasp_box' and marker.id==0 and marker.action==Marker.ADD:
                display.append(marker.pose.position.z)
    node.create_subscription(MarkerArray,'/openarm/physical_objects',markers,1)
    deadline=time.monotonic()
    for step in range(1500):
        rclpy.spin_once(node,timeout_sec=0);node.sim.step()
        if step%5==0:node.publish_state()
        if step%50==0:node.object_snapshot();physical.append(float(d.qpos[adr+2]))
        if step%100==0:node.snapshot()
        deadline+=.002;delay=deadline-time.monotonic()
        if delay>0:time.sleep(delay)
    assert max(physical)-min(physical)>.30,physical
    assert display and max(display)-min(display)>.15,display
    q=GetPlanningScene.Request();q.components.components=PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
    scene=call(node,GetPlanningScene,'/get_planning_scene',q).scene
    co=next(o for o in scene.world.collision_objects if o.id=='openarm_grasp_box')
    assert abs(co.pose.position.z-float(d.qpos[adr+2]))<.01
    print('PASS physical free fall, changing truth markers and settled planning pose',
          'drop_m',round(max(physical)-min(physical),3),'marker_range_m',round(max(display)-min(display),3),flush=True)
finally:
    if node:node.destroy_node()
    os.kill(original[0],signal.SIGCONT);rclpy.shutdown()
