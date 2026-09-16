# OPL integration checks

These scripts require the built OpenArm image and a working NVIDIA Docker setup.
Run commands in the **Ubuntu host terminal at the repository root**.
They use an isolated container, ROS domain and virtual display; the normal GUI is unaffected.

Physics, all 34 rows, 14 furniture types, support/collision/rollback, open cavities and RGB/depth (both versions):

```bash
docker run --rm --gpus all -e LIBGL_ALWAYS_SOFTWARE=0 -e MUJOCO_GL=egl -e NVIDIA_DRIVER_CAPABILITIES=all -v "$PWD/tests/opl_physics_check.py:/tmp/opl_physics_check.py:ro" openarm-sim:0.6.0 python /tmp/opl_physics_check.py
```

Start an isolated GUI/ROS test environment (use OPENARM_VERSION=1 for version 1):

```bash
docker run -d --name openarm-opl-check --network none --gpus all -e OPENARM_VERSION=2 -e ROS_DOMAIN_ID=74 -e LIBGL_ALWAYS_SOFTWARE=0 -e NVIDIA_DRIVER_CAPABILITIES=all openarm-sim:0.6.0 headless
```

Copy the test:

```bash
docker cp tests/opl_live_check.py openarm-opl-check:/tmp/opl_live_check.py
```

Run actual Tk GUI operations, MoveIt geometry/pose comparison and six live camera streams:

```bash
docker exec openarm-opl-check /opt/openarm/scripts/entrypoint.sh xvfb-run -a python /tmp/opl_live_check.py
```

Remove only this test environment after checking the result:

```bash
docker rm -f openarm-opl-check
```

The full GUI test takes several minutes. Physics evidence is saved under /tmp/opl-evidence
inside its container. GUI checks intentionally change only their isolated scene.
These checks are separate from host-only unit test discovery because they need ROS, MuJoCo and rendering.
