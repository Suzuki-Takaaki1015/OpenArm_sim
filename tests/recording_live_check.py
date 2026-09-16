"""Run only in an isolated, disposable OpenArm test container with Xvfb."""
import os
assert os.environ.get('OPENARM_ISOLATED_TEST') == '1'
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import tkinter as tk

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from scene_panel import ScenePanel
from recording import ROOT, TOPICS, Controller, previous_status

root=tk.Tk(); panel=ScenePanel(root)
def wait(predicate, seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        root.update();time.sleep(.05)
        if predicate():return
    raise AssertionError('timeout: '+panel.record_state.get())
def settle(seconds):
    until=time.monotonic()+seconds
    while time.monotonic()<until:root.update();time.sleep(.05)
def start(name):
    panel.record_name.set(name);panel.record_start.invoke()
    wait(lambda: (ROOT/name/'openarm.json').exists() and json.loads((ROOT/name/'openarm.json').read_text())['state']=='recording')
    settle(.5)
def stop(name):
    panel.record_stop.invoke();wait(lambda:not panel.recording.active())
    settle(.3)
    data=json.loads((ROOT/name/'openarm.json').read_text())
    assert data['state']=='complete',data
    assert data['bag_finalized']
    return data
def inspect(name, camera):
    path=ROOT/name
    meta=json.loads((path/'openarm.json').read_text())
    assert meta['model']==os.environ['OPENARM_VERSION']
    assert meta['camera_start']['enabled']==camera
    assert meta['simulation_end_ns']>meta['simulation_start_ns']>0
    for value in meta['files'].values():
        assert hashlib.sha256((path/value['copy']).read_bytes()).hexdigest()==value['sha256']
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path/'bag'),storage_id='mcap'),rosbag2_py.ConverterOptions('',''))
    types={entry.name:entry.type for entry in reader.get_all_topics_and_types()}
    assert set(types)<=set(TOPICS),types
    counts={}; stamps=[]; headers={}; frames=set(); images={}
    while reader.has_next():
        topic,raw,stamp=reader.read_next()
        msg=deserialize_message(raw,get_message(types[topic]))
        counts[topic]=counts.get(topic,0)+1
        assert stamp>0
        assert meta['simulation_start_ns']-1000000000 <= stamp <= meta['simulation_end_ns']+1000000000
        stamps.append(stamp)
        if topic in ('/tf','/tf_static'):
            for transform in msg.transforms:frames.add(transform.child_frame_id)
        if hasattr(msg,'header') and msg.header.stamp.sec+msg.header.stamp.nanosec>0:
            h=msg.header.stamp.sec*1000000000+msg.header.stamp.nanosec
            assert abs(stamp-h)<2000000000,(topic,stamp,h)
            headers.setdefault(topic,[]).append(h)
        if types[topic]=='sensor_msgs/msg/Image':
            assert len(msg.data)==msg.height*msg.step
            if '/color/image' in topic:assert msg.encoding=='rgb8' and (msg.width,msg.height)==(320,180)
            else:assert msg.encoding=='16UC1' and any(msg.data)
            images[topic]=[msg.encoding,msg.width,msg.height]
    for topic in ('/clock','/mujoco/joint_states','/joint_states','/openarm/sim_state','/openarm/object_state','/tf','/tf_static'):
        assert counts.get(topic,0)>0,(topic,counts)
    assert {'camera_link','camera_color_optical_frame','camera_depth_optical_frame'}<=frames,frames
    if camera:
        for topic in TOPICS:
            if topic.startswith('/camera/'):assert counts.get(topic,0)>0,(topic,counts)
        assert len(images)==3
    else:assert not images,images
    print('CONTENT',name,json.dumps(dict(counts=counts,images=images,frames=len(frames),time_range=[min(stamps),max(stamps)])),flush=True)

wait(lambda:not panel.busy,90)
assert not panel.recording.active()
start('camera_off')
assert 'カメラOFF' in panel.record_state.get(),panel.record_state.get()
settle(3);stop('camera_off');inspect('camera_off',False)
old=(ROOT/'camera_off/openarm.json').read_bytes()
panel.record_name.set('camera_off');panel.record_start.invoke();wait(lambda:not panel.recording.active());settle(.3)
assert '同名' in panel.record_state.get(),panel.record_state.get()
assert (ROOT/'camera_off/openarm.json').read_bytes()==old

panel.request('camera-on');wait(lambda:not panel.busy,90);settle(2);wait(lambda:not panel.busy,120)
start('rgbd')
other=Controller();other.start('duplicate')
wait(lambda:not other.active());assert not (ROOT/'duplicate').exists()
events=[]
while not other.events.empty():events.append(other.events.get())
assert any('既に記録中' in x['message'] for x in events),events
settle(5);stop('rgbd');inspect('rgbd',True)

start('gui_close');settle(2)
panel.close()
deadline=time.monotonic()+25
while time.monotonic()<deadline:
    try:root.update()
    except tk.TclError:break
    if not panel.recording.active():break
    time.sleep(.05)
assert not panel.recording.active()
assert json.loads((ROOT/'gui_close/openarm.json').read_text())['state']=='complete'

# A killed monitor triggers the recorder's Linux parent-death SIGINT.
controller=Controller();controller.start('monitor_death')
deadline=time.monotonic()+20
while time.monotonic()<deadline:
    if (ROOT/'monitor_death/openarm.json').exists() and json.loads((ROOT/'monitor_death/openarm.json').read_text())['state']=='recording':break
    time.sleep(.1)
else:raise AssertionError('monitor death setup')
time.sleep(2);controller.proc.kill();controller.proc.wait()
deadline=time.monotonic()+20
while time.monotonic()<deadline and not (ROOT/'monitor_death/bag/metadata.yaml').exists():time.sleep(.1)
assert (ROOT/'monitor_death/bag/metadata.yaml').exists()
assert 'monitor_death' in previous_status()
assert json.loads((ROOT/'monitor_death/openarm.json').read_text())['state']=='recording'
print('PASS GUI CONTENT STOP DUPLICATE COLLISION CLOSE MONITOR-DEATH v'+os.environ['OPENARM_VERSION'],flush=True)
