"""Real MJCF acceptance tests, also executable without ROS or a display."""
import unittest
import numpy as np
from physics import Simulation


class PhysicsTest(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation()

    def test_hold_and_track(self):
        sim = self.sim
        for _ in range(1000):
            sim.step()
        arm = [j for j, name in enumerate(sim.names) if 'finger' not in name]
        self.assertLess(float(np.max(np.abs(sim.data.qpos[sim.qadr[arm]]))), 0.05)
        name = 'openarm_right_joint1'
        sim.command([name], [0.2])
        for _ in range(2000):
            sim.step()
        measured = sim.data.qpos[sim.qadr[sim.index[name]]]
        self.assertAlmostEqual(measured, 0.2, delta=0.04)
        self.assertAlmostEqual(sim.data.time, 6.0, places=6)

    def test_invalid_commands_are_atomic(self):
        for names, values in [(['missing'], [0]), (['openarm_right_joint1'], [float('nan')]),
                              (['openarm_right_joint1'], [100]),
                              (['openarm_right_joint1'] * 2, [0, 0]),
                              (['openarm_right_joint1'], []),
                              (['openarm_right_joint1', 'missing'], [0.2, 0])]:
            before = self.sim.target.copy()
            with self.assertRaises(ValueError):
                self.sim.command(names, values)
            np.testing.assert_array_equal(self.sim.target, before)

    def test_reset(self):
        self.sim.command(['openarm_right_joint1'], [0.2])
        self.sim.step()
        self.sim.reset()
        self.assertEqual(self.sim.data.time, 0)
        np.testing.assert_array_equal(self.sim.target, self.sim.model.qpos0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
