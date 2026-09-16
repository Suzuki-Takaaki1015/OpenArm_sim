"""Offline regression tests of sync state machine; ROS integration remains required."""
import ast,time,unittest,asyncio
from types import SimpleNamespace as NS
from pathlib import Path
class Future:
    def __init__(self):self.cb=None
    def add_done_callback(self,cb):self.cb=cb
    def result(self):return self.response
    def finish(self,response):self.response=response;self.cb(self)
    def cancel(self):pass
class Client:
    def service_is_ready(self):return True
    def call_async(self,request):self.request=request;self.future=Future();return self.future
class Request:
    def __init__(self,**kw):self.components=NS(components=0);self.__dict__.update(kw)
class Scene:
    def __init__(self,**kw):self.robot_state=NS(is_diff=False);self.world=NS(collision_objects=[])
source_path=Path(__file__).resolve().parents[1]/'docker/app/object_scene_sync.py'
if not source_path.exists():source_path=Path(__file__).with_name('object_scene_sync.py')
source=ast.parse(source_path.read_text())
selected=ast.Module(body=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('same','values') or isinstance(n,ast.ClassDef)],type_ignores=[])
namespace=dict(Node=object,time=time,asyncio=asyncio,PlanningScene=Scene,
 CollisionObject=NS(ADD=0,REMOVE=1,MOVE=3),
 PlanningSceneComponents=NS(ROBOT_STATE_ATTACHED_OBJECTS=4,WORLD_OBJECT_GEOMETRY=16),
 GetPlanningScene=NS(Request=Request),ApplyPlanningScene=NS(Request=Request),
 collision=lambda identifier,description,position,operation:NS(id=identifier,position=position,operation=operation),
 ITEMS={'box':{'id':'box'},'other':{'id':'other'}},OBJECTS=[dict(id='table',position=[.5,0,.12])])
exec(compile(selected,'sync','exec'),namespace)
Sync=namespace['SceneSync']
def state(x):return dict(enabled=True,position=[x,0,0],quaternion_wxyz=[1,0,0,0])
def make():
 n=Sync();n.latest=dict(objects=dict(box=state(1),other=state(2)),obstacles=False)
 n.received=time.monotonic();n.pending=None;n.pending_since=0;n.next_query=time.monotonic()+10
 n.verified=True;n.paused=False;n.attached=set();n.known={};n.descriptions={'box':{},'other':{},'table':{}}
 n.client=Client();n.apply=Client();n.get_logger=lambda:NS(warning=lambda *a,**k:None)
 return n
# Construct without ROS __init__.
Sync.__init__=lambda self:None
class Tests(unittest.TestCase):
 def test_only_acknowledge_success(self):
  n=make();n.tick();self.assertEqual(n.known,{})
  n.apply.future.finish(NS(success=False));self.assertFalse(n.verified);self.assertEqual(n.known,{})
 def test_latest_wins_while_pending(self):
  n=make();n.tick();n.latest['objects']['box']=state(3)
  n.apply.future.finish(NS(success=True));self.assertEqual(n.known['box'][0],1)
  n.tick();self.assertEqual(n.apply.request.scene.world.collision_objects[0].position[0],3)
 def test_attachment_not_readded_others_continue(self):
  n=make();n.attached={'box'};n.tick()
  self.assertEqual([o.id for o in n.apply.request.scene.world.collision_objects],['other'])
 def test_disabled_present_object_removed(self):
  n=make();n.latest['objects']['box']['enabled']=False;n.known={'box':[1,0,0,1,0,0,0]};n.tick()
  self.assertEqual(n.apply.request.scene.world.collision_objects[0].operation,1)
 def test_pause_and_resume_forces_readback(self):
  n=make();asyncio.run(n.pause_sync(NS(data=True),NS()));n.tick();self.assertIsNone(n.pending)
  asyncio.run(n.pause_sync(NS(data=False),NS()));n.tick();self.assertIs(n.pending,n.client.future)
 def test_dead_future_invalidates_ack_cache(self):
  n=make();n.tick();n.pending_since=time.monotonic()-4;n.tick()
  self.assertIsNone(n.pending);self.assertFalse(n.verified)
 def test_no_write_with_stale_truth(self):
  n=make();n.received=time.monotonic()-3;n.tick();self.assertIsNone(n.pending)
 def test_legacy_table_forces_add(self):
  n=make();p=NS(position=NS(x=0.,y=0.,z=0.),orientation=NS(w=1.,x=0.,y=0.,z=0.))
  old=NS(position=NS(x=.5,y=0.,z=.12),orientation=p.orientation)
  response=NS(scene=NS(robot_state=NS(attached_collision_objects=[]),world=NS(collision_objects=[NS(id='table',pose=p,primitive_poses=[old])])))
  n.readback(response);self.assertNotIn('table',n.known)
 def test_antipodal_quaternions_are_same_rotation(self):
  self.assertTrue(namespace['same']([1,2,3,1,0,0,0],[1,2,3,-1,0,0,0]))
 def test_pause_waits_for_service_completion(self):
  async def check():
   n=make();pending=asyncio.get_running_loop().create_future();n.pending=pending
   response=NS();task=asyncio.create_task(n.pause_sync(NS(data=True),response))
   await asyncio.sleep(0);self.assertTrue(n.paused);self.assertFalse(task.done())
   pending.set_result(NS(success=True));await task;self.assertTrue(response.success)
  asyncio.run(check())
if __name__=='__main__':unittest.main()
