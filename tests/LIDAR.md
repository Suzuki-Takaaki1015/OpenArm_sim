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
