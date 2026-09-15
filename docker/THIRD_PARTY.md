# Third-party components

The image contains the official OpenArm v1 MJCF and meshes from:
https://github.com/enactic/openarm_mujoco

Pinned revision: 161039cd74ea8675fb8197836fe5674659825c75
The upstream LICENSE is copied unchanged into /opt/openarm/models/LICENSE.
The upstream source headers are retained. This project is an independent prototype.

Other components include Ubuntu 24.04, ROS 2 Jazzy, MuJoCo, NumPy, Mesa,
Xvfb, Openbox, x11vnc and noVNC/websockify. Their upstream licenses apply.
Ubuntu package copyright files remain in /usr/share/doc inside the image;
Python package license metadata remains in the virtual environment.
Installed versions are recorded in /opt/openarm/os-packages.txt and
/opt/openarm/python-packages.txt.

## Camera assets
OpenArm official D435 bracket: CERN-OHL-S-2.0; original STEP and license in app/camera_assets. RealSense D435 mesh and nominal URDF: Apache-2.0; originals, commit and license in app/camera_assets. See app/camera_assets/SOURCES.md and CAMERA_MOUNT.md.
