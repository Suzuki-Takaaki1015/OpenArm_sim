# MID-360S validation (2026-10-18)

Environment: Ubuntu VM, approximately 8 GiB RAM, CPU/software rendering.

- Existing regression suite: 45 tests passed; Python/shell syntax and `git diff --check` passed.
- Both generated models: joint/mocap layout unchanged by sensor asset filtering; ideal ray intersections match the original model for empty, box, and box+bottle scenes.
- Both models: sampled chest RGB/depth rays show no obstruction by the added LiDAR mount (0/2304 per stream).
- Shared renderer: RGB/depth pixels match independent render contexts at chest and wrist stream sizes.
- OpenArm 1.0: headless ROS integration passed: cloud fields/TF, table hits, table removal, camera images, object toggle, LiDAR stop/resume.
- OpenArm 2.0: the same integration passed with RViz and MuJoCo windows running, including both wrist camera streams. RViz point cloud rendering was visually verified.
- All five ROS controllers activated in both integration runs.

Limits: final 1.0 integration was run without GUI on this 8 GiB VM. Full simultaneous 1.0 GUI/camera/LiDAR use on larger-memory hardware remains to be checked. Earlier full-GUI builds exceeded this VM's practical memory budget. No real-device accuracy, Livox proprietary scan pattern, intensity/noise, physical mounting calibration, or new grasp planner was validated.

Defaults retain both RViz and MuJoCo windows. LiDAR starts disabled; use the scene panel MID-360S controls. The mount pose is a project-defined fixed position, not a measured robot calibration. No GitHub push was performed.


## CAD fidelity and density correction (2026-10-18)

- Removed destructive visual decimation: retained 111613 original CAD triangles. Close-up MuJoCo renders confirm the dome and cooling fins retain their curved shape. Collision envelopes and mounting TF are unchanged.
- Both model versions compile, retain expected actuator counts and have no initial LiDAR contacts. Sampled chest RGB/depth rays are unobstructed by the sensor (0/2304 in each camera, both models).
- Same-pose local ray check: table returns increase from 108 at 800 rays to 1088 at 8000 and 5448 at 40000, on both robots. Dense clouds contain approximately 19700 returns; missing geometry is not padded with fake points.
- `lidar_density_check.py` passed against real ROS nodes for both versions: dense default, live density changes, invalid-parameter rejection, disable/resume. OpenArm 1.0 used a headless verification container; OpenArm 2.0 had both RViz and MuJoCo windows enabled. This verification choice does not change the launcher's both-window default.
- On this 8GB VM, sampled dense-mode wall-clock rates were approximately 1.5 Hz (v1) and 2.3 Hz (v2), below the configured 5 Hz maximum. Dense raycasting took approximately 583 ms and 397 ms respectively under concurrent simulation load. These are sample measurements, not guaranteed throughput on another PC. No automatic density reduction is applied.
- All 45 existing lightweight unit tests passed. GPU hardware performance and OpenArm 1.0 with all GUI/camera streams simultaneously were not revalidated in this correction.

Run the density test only in a disposable simulation; it changes table and LiDAR state:

```bash
python /workspaces/OpenArm_sim/tests/lidar_density_check.py
```
