"""Check sequential viewports preserve pixels/depth compared to separate contexts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path('/opt/openarm/app')))
import mujoco,numpy as np
from shared_renderer import SharedRenderer
m=mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="box" size=".2 .1 .1" rgba="1 0 0 1"/><camera name="cam" pos="0 0 2"/></worldbody></mujoco>')
d=mujoco.MjData(m);mujoco.mj_forward(m,d)
r=SharedRenderer(m,width=424,height=240)
try:
 for w,h in [(320,180),(424,240),(320,200),(320,180)]:
  ref=mujoco.Renderer(m,width=w,height=h)
  try:
   r.resize_viewport(w,h)
   for depth in (False,True):
    for renderer in (r,ref):
     (renderer.enable_depth_rendering if depth else renderer.disable_depth_rendering)()
     renderer.update_scene(d,camera='cam')
    np.testing.assert_allclose(r.render(),ref.render(),rtol=1e-6,atol=1e-6)
  finally:ref.close()
 print('PASS shared viewport RGB/depth identical to separate renderers',flush=True)
finally:r.close()
