"""Simulated mobile base limits. Linear units are m/s, angular units are rad/s."""

MANUAL_SPEEDS = {
    '低速': (0.18, 0.5),
    '標準': (0.40, 0.9),
    '高速': (0.60, 1.2),
}
MAX_LINEAR, MAX_YAW = MANUAL_SPEEDS['高速']
NAV_LINEAR, NAV_YAW = MANUAL_SPEEDS['標準']
LINEAR_ACCEL = 0.9
YAW_ACCEL = 2.0
