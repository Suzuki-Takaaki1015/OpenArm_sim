# Source assets

chest-camera_D435.step: Enactic OpenArm hardware 1.1.0, CERN-OHL-S-2.0. Original unmodified STEP included; tessellated chest_mount.obj is a derived representation.
https://github.com/enactic/openarm_hardware/releases/tag/1.1.0

d435.dae and _d435.urdf.xacro: RealSense realsense-ros commit 9a11121700cb4780e273e34141f6402fe184321d, Apache-2.0; originals included. d435.obj is a simplified visual derivative (trimesh / fast-simplification). Nominal housing collision is a primitive box.

pedestal_collision.obj / column_collision.obj: derived from the pinned OpenArm MuJoCo body mesh, Apache-2.0. Lower pedestal convex hull below 221.05 mm plus the original 60x60x750 mm column; chest cover removed. Original source remains in docker/vendor/v1.

See the included license texts and CAMERA_MOUNT.md for coordinate derivation.
