"""Destructive only to an isolated test container's MoveIt process."""
import os,signal,subprocess,time,json
from pathlib import Path
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool
from std_msgs.msg import String
from visualization_msgs.msg import MarkerArray,Marker
from rclpy.qos import QoSProfile,DurabilityPolicy
from moveit_msgs.msg import PlanningSceneComponents
from moveit_msgs.srv import GetPlanningScene
from scene_cli import call
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1','Use only an isolated test container'
rclpy.init();n=Node('verify_moveit_restart');latest={}
n.create_subscription(String,'/openarm/object_state',lambda m:latest.update(json.loads(m.data)),1)
def pump(t):
    end=time.monotonic()+t
    while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.02)
for service in ['/openarm/set_obstacles','/openarm/objects/box/set_enabled','/openarm/objects/ycb_025_mug/set_enabled']:
    assert call(n,SetBool,service,SetBool.Request(data=True)).success
pump(2)
start_pose=latest['objects']['box']['position'][:]
ids={'openarm_demo_table','openarm_grasp_box','openarm_ycb_025_mug'}
def names():
    q=GetPlanningScene.Request();q.components.components=PlanningSceneComponents.WORLD_OBJECT_NAMES
    client=n.create_client(GetPlanningScene,'/get_planning_scene')
    try:
        if not client.wait_for_service(timeout_sec=1):return set()
        future=client.call_async(q);rclpy.spin_until_future_complete(n,future,timeout_sec=2)
        if not future.done():future.cancel();return set()
        return {o.id for o in future.result().scene.world.collision_objects}
    finally:n.destroy_client(client)

for _ in range(10):
    if ids<=names():break
    pump(.2)
else:raise AssertionError("initial scene unavailable")
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:args=(p/'cmdline').read_bytes().split(b'\0')
    except OSError:continue
    if args and args[0].endswith(b'/move_group'):processes.append((int(p.name),[a.decode() for a in args if a]))
assert len(processes)==1,processes
pid,args=processes[0]
parent=int(next(l.split()[1] for l in Path(f'/proc/{pid}/status').read_text().splitlines() if l.startswith('PPid:')))
# Freeze only the test launch supervisor so its intentional fail-fast handler
# cannot reset physics when exercising an independently restarted MoveIt.
assert parent>1,'Test requires a separate launch parent'
os.kill(parent,signal.SIGSTOP);os.kill(pid,signal.SIGTERM)
time.sleep(2)
log=open('/tmp/restarted-moveit.log','w');replacement=subprocess.Popen(args,stdout=log,stderr=log)
Path('/tmp/recovery_processes.json').write_text(json.dumps(dict(parent=parent,replacement=replacement.pid)))
begin=time.monotonic()
try:
    while time.monotonic()-begin<20:
        pump(.2)
        if ids<=names():break
    else:raise AssertionError('MoveIt did not recover geometry')
    assert max(abs(a-b) for a,b in zip(start_pose,latest['objects']['box']['position']))<.005
    # A newly subscribing display must receive a complete retained truth snapshot.
    received=[]
    n.create_subscription(MarkerArray,'/openarm/physical_objects',received.append,
        QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    pump(2);assert received
    assert ids<={m.ns for m in received[-1].markers if m.action==Marker.ADD}
    print('PASS MoveIt-only restart, unchanged physics, recovered table/YCB/box, late display; seconds',round(time.monotonic()-begin,3),flush=True)
finally:
    n.destroy_node();rclpy.shutdown()
