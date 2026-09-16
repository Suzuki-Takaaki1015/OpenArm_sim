import os,time,json,tkinter as tk
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from visualization_msgs.msg import MarkerArray,Marker
from scene_panel import ScenePanel
rclpy.init();node=Node('verify_gui_restart');states=[];frames=[]
node.create_subscription(String,'/openarm/object_state',lambda m:states.append(json.loads(m.data)),1)
node.create_subscription(MarkerArray,'/openarm/physical_objects',frames.append,1)
root=tk.Tk();panel=ScenePanel(root)
def pump(t):
 end=time.monotonic()+t
 while time.monotonic()<end:root.update();rclpy.spin_once(node,timeout_sec=.02)
ready=time.monotonic()+20
while (not states or not frames) and time.monotonic()<ready:pump(.1)
assert states and frames
old=states[-1]['time'];restart_index=len(states);panel.restart()
assert panel.restart_button.instate(['disabled']),panel.detail.get()
pump(22)
assert min(s['time'] for s in states[restart_index:])<old,('simulation did not reset',old,states[-1]['time'])
assert not states[-1]['obstacles'] and not any(o['enabled'] for o in states[-1]['objects'].values())
assert not any(m.action==Marker.ADD for m in frames[-1].markers)
print('PASS actual GUI restart handler: new physics time, cleared table/objects and RViz markers',flush=True)
root.destroy();node.destroy_node();rclpy.shutdown()
