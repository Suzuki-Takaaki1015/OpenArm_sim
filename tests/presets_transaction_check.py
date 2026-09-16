"""Direct real-physics handler test: fault injection and complete rollback equality."""
import copy,os,tempfile,time
import numpy as np
import rclpy
from bridge import Bridge
from scene_presets import Store,decode,validate
from environment_assets import ITEMS
from scene_objects import OBJECTS
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
rclpy.init();b=Bridge();p=b.presets
p.controllers={k:(time.monotonic(),False) for k in ('a','b','c','d')}
doc=p.capture();doc['tables'][OBJECTS[0]['id']]['enabled']=True
doc['objects']['box']=dict(enabled=True,pose=[.36,-.2,.207,1.,0.,0.,0.],support='worktable')
p.apply(doc);before=p.backup()
original=b.objects.write_pose
def failure(key,pose):
    original(key,pose)
    if key=='bottle':raise RuntimeError('injected mid-commit failure')
b.objects.write_pose=failure
try:p.apply(doc)
except RuntimeError as exc:assert 'injected' in str(exc)
else:raise AssertionError('Failure did not fire')
b.objects.write_pose=original
after=p.backup()
for old,new in zip(before[:2],after[:2]):
    for key in old:assert np.array_equal(old[key],new[key]),key
assert before[2:]==after[2:]
print('PASS injected failure restores qpos/qvel/warmstart/mocap/masks/materials/gravity/support/enabled')
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
trajectory=JointTrajectory();point=JointTrajectoryPoint();point.time_from_start.sec=10;trajectory.points=[point]
p.trajectory('direct',trajectory);deadline=p.trajectory_until['direct']
p.trajectory('direct',JointTrajectory())
assert p.trajectory_until['direct']==deadline
point.time_from_start.sec=1;p.trajectory('direct',trajectory)
assert p.trajectory_until['direct']==deadline
try:p.apply(doc)
except ValueError:pass
else:raise AssertionError('future direct trajectory accepted')
p.trajectory_until.clear()
print('PASS empty/shorter direct trajectory cannot shorten active guard')
p.controllers.clear()
try:p.apply(doc)
except ValueError:pass
else:raise AssertionError('stale controllers accepted')
with tempfile.TemporaryDirectory() as directory:
    store=Store(directory)
    store.save('日本語 scene',doc)
    assert store.load('日本語 scene')==doc
    for name in ('../outside','/absolute','a/b','', 'a'*65):
        try:store.save(name,doc)
        except ValueError:pass
        else:raise AssertionError(name)
    for text in ('{"x":1,"x":2}','{"x":NaN}', '{"x":Infinity}', ' '*300000):
        try:decode(text)
        except ValueError:pass
        else:raise AssertionError('invalid JSON accepted')
    target=store.path('linked');target.symlink_to(store.path('日本語 scene'))
    try:store.load('linked')
    except ValueError:pass
    else:raise AssertionError('symlink accepted')
print('PASS stale controller, bounded JSON, duplicate key, path and link rejection')
b.destroy_node();rclpy.shutdown()
