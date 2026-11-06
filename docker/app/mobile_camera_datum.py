"""Mobile D435i mount in openarm_body_link0 (metres, +X forward, +Z up).

The CAD cover's front opening spans z=0.619..0.657 at its center.
The supplied OpenArm photograph sets the visual target. Pitch and depth
are a project fit to the CAD, not a measured factory calibration.
"""
import math
import numpy as np

FRONT_CENTER = np.array([.057, 0., .631])
PITCH = math.radians(15.)
COLOR_OFFSET = np.array([0., .015, 0.])


def mobile_d435():
    c, s = math.cos(PITCH), math.sin(PITCH)
    rotation = np.array([[c,0.,s], [0.,1.,0.], [-s,0.,c]])
    # Mesh axes are width, height and forward. Camera axes are forward, left, up.
    mesh_rotation = rotation @ np.array([[0.,0.,1.], [1.,0.,0.], [0.,1.,0.]])
    depth = FRONT_CENTER + rotation @ np.array([-.0043,.0175,0.])
    saddle_half = np.array([.004,.019,.0035])
    saddle_center = FRONT_CENTER - rotation[:,0]*(.02505+saddle_half[0])
    return dict(front=FRONT_CENTER, rotation=rotation, mesh_rotation=mesh_rotation,
                depth=depth, color=depth+rotation@COLOR_OFFSET,
                saddle_center=saddle_center, saddle_half=saddle_half)
