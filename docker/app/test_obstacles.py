"""Contact toggling integration test using real MuJoCo collision detection."""
import unittest
from types import SimpleNamespace
import mujoco
from std_srvs.srv import SetBool
from bridge import Bridge
from scene_objects import OBJECTS

class ObstacleTest(unittest.TestCase):
    def test_contact_enable_disable_and_overlap_rejection(self):
        geoms=''.join(f'<geom name="{o["id"]}" type="box" pos="{" ".join(map(str,o["position"]))}" size="{" ".join(str(v/2) for v in o["size"])}" contype="0" conaffinity="0" rgba="0 0 0 0"/>' for o in OBJECTS)
        xml=f'<mujoco><worldbody>{geoms}<body pos="0.5 0 0.3"><joint type="slide" axis="0 0 1"/><geom type="sphere" size="0.05" mass="1"/></body></worldbody></mujoco>'
        m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m)
        holder=SimpleNamespace(sim=SimpleNamespace(model=m,data=d),obstacles_enabled=False)
        def toggle(enabled):
            request=SetBool.Request();request.data=enabled
            return Bridge.set_obstacles(holder,request,SetBool.Response())
        self.assertTrue(toggle(True).success)
        d.qpos[0]=-0.17;mujoco.mj_forward(m,d)
        self.assertGreater(d.ncon,0,'enabled obstacle must create real contact')
        self.assertTrue(toggle(False).success)
        self.assertEqual(d.ncon,0,'disabled obstacle must remove real contact')
        self.assertFalse(toggle(True).success,'overlapping activation must be rejected')
        self.assertEqual(d.ncon,0)
        self.assertFalse(holder.obstacles_enabled)

if __name__=='__main__':unittest.main()
