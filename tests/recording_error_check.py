"""Isolated fault-injection checks; never fill a real filesystem."""
import os
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from scene_panel import ScenePanel
from recording import ROOT, Controller

def injected(name, setup):
    code="import recording,sys,time;from types import SimpleNamespace\n"+setup+"\nsys.exit(recording.record("+repr(name)+"))"
    p=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,cwd='/tmp')
    return p
def finish(p):
    code=p.wait(timeout=30);output=p.stdout.read();print(output,flush=True);p.stdin.close();p.stdout.close();return code,output

p=injected('low_start','recording.shutil.disk_usage=lambda _:SimpleNamespace(free=0)')
code,out=finish(p);assert code==1 and '1 GiB' in out and not (ROOT/'low_start').exists()
p=injected('low_running',"original=recording.shutil.disk_usage\nstarted=time.monotonic()\nrecording.shutil.disk_usage=lambda path: original(path) if time.monotonic()-started<9 else SimpleNamespace(free=0)")
code,out=finish(p);meta=json.loads((ROOT/'low_running/openarm.json').read_text());assert meta['stop_reason']=='low_disk' and meta['state']=='error' and meta['bag_finalized'],meta

p=injected('spawn_failure',"recording.subprocess.Popen=lambda *a,**k: (_ for _ in ()).throw(OSError('injected spawn failure'))")
code,out=finish(p);assert code==1 and 'injected spawn failure' in out
assert json.loads((ROOT/'spawn_failure/openarm.json').read_text())['state']=='error'

# EOF simulates a GUI killed by the OS: only the pipe is closed, no stop command.
p=injected('owner_eof','')
deadline=time.monotonic()+20
while time.monotonic()<deadline:
    if (ROOT/'owner_eof/openarm.json').exists() and json.loads((ROOT/'owner_eof/openarm.json').read_text())['state']=='recording':break
    time.sleep(.1)
else:raise AssertionError('owner eof setup')
time.sleep(2);p.stdin.close();code,out=finish(p)
meta=json.loads((ROOT/'owner_eof/openarm.json').read_text());assert meta['state']=='complete' and meta['stop_reason']=='gui_closed'

# Path traversal and links may never overwrite a sentinel.
sentinel=ROOT/'sentinel';sentinel.write_text('preserve me')
(ROOT/'linked').symlink_to(sentinel)
p=injected('linked','');code,out=finish(p);assert code==1 and sentinel.read_text()=='preserve me'
try:Controller().start('../escape')
except ValueError:pass
else:raise AssertionError('traversal')

root=tk.Tk();panel=ScenePanel(root)
def wait(predicate,seconds=35):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        root.update();time.sleep(.05)
        if predicate():return
    raise AssertionError(panel.record_state.get())
wait(lambda:not panel.busy,90)
panel.record_name.set('gui_restart');panel.record_start.invoke()
wait(lambda:(ROOT/'gui_restart/openarm.json').exists() and json.loads((ROOT/'gui_restart/openarm.json').read_text())['state']=='recording')
for _ in range(10):root.update();time.sleep(.05)
from PIL import ImageGrab
ImageGrab.grab(xdisplay=os.environ['DISPLAY']).save('/tmp/recording-gui.png')
panel.restart_button.invoke()
wait(lambda:panel.restart_button.instate(['disabled']))
assert json.loads((ROOT/'gui_restart/openarm.json').read_text())['state']=='complete'
assert not panel.recording.active()
root.destroy()
print('PASS DISK START/RUNTIME SPAWN EOF PATH GUI-RESTART v'+os.environ['OPENARM_VERSION'],flush=True)
