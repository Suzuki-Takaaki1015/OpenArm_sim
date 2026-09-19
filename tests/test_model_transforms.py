"""Regression for the chest bracket singular quaternion, without ROS."""
import importlib.util
import math
from pathlib import Path
import random
import unittest

spec = importlib.util.spec_from_file_location("model_transforms", Path(__file__).resolve().parents[1] / "docker/app/model_transforms.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def rotation(q):
    n=math.hypot(*q); w,x,y,z=(v/n for v in q)
    return [[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
            [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
            [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]]


def urdf_rotation(rpy):
    r,p,y=rpy; cr,sr=math.cos(r),math.sin(r); cp,sp=math.cos(p),math.sin(p); cy,sy=math.cos(y),math.sin(y)
    return [[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
            [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]]


class TransformTests(unittest.TestCase):
    def assert_rotation(self,q):
        a=rotation(q); b=urdf_rotation(module.quaternion_to_rpy(q))
        for ra,rb in zip(a,b):
            for va,vb in zip(ra,rb): self.assertAlmostEqual(va,vb,places=9)

    def test_official_chest_bracket(self):
        self.assert_rotation([.5,-.5,-.5,-.5])
        self.assert_rotation([-.5,.5,.5,.5])

    def test_both_singularities_and_nearby(self):
        for sign in (-1,1):
            for angle in (math.pi/2,math.pi/2-1e-8):
                self.assert_rotation([math.cos(angle/2),0,sign*math.sin(angle/2),0])
        for q in ([.5,.5,.5,-.5],[.5,.5,-.5,.5],[1,0,0,0],[0,1,0,0]): self.assert_rotation(q)

    def test_general_rotations(self):
        rng=random.Random(42)
        for _ in range(200): self.assert_rotation([rng.uniform(-2,2) for _ in range(4)])

    def test_invalid_quaternion(self):
        for q in ([0,0,0,0],[float("nan"),0,0,1],[float("inf"),0,0,1]):
            with self.assertRaises(ValueError): module.quaternion_to_rpy(q)
