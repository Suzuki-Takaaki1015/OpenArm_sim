"""Rotation conversion for URDF origins (extrinsic XYZ / fixed-axis RPY)."""
import math


def quaternion_to_rpy(quaternion):
    w, x, y, z = map(float, quaternion)
    norm = math.hypot(w, x, y, z)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Expected a finite nonzero quaternion")
    w, x, y, z = (v / norm for v in (w, x, y, z))
    r00 = 1 - 2 * (y*y + z*z)
    r10 = 2 * (x*y + w*z)
    r20 = 2 * (x*z - w*y)
    r01 = 2 * (x*y - w*z)
    r11 = 1 - 2 * (x*x + z*z)
    r21 = 2 * (y*z + w*x)
    r22 = 1 - 2 * (x*x + y*y)
    horizontal = math.hypot(r00, r10)
    pitch = math.atan2(-r20, horizontal)
    if horizontal < 1e-10:
        # At pitch +/-90 degrees roll and yaw are coupled. Choose roll=0
        # and preserve the actual rotation instead of evaluating atan2(0,0).
        return [0.0, pitch, math.atan2(-r01, r11)]
    return [math.atan2(r21, r22), pitch, math.atan2(r10, r00)]
