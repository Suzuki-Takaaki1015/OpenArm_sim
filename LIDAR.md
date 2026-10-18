# MID-360S simulation

OpenArm 1.0 / 2.0 share a fixed, project-designed chest-column mount. This is an ideal range sensor with MID-360S field of view, not a Livox SDK/device emulator.

## Use

Run `bash start.sh`, select the robot, and use **MID-360S 点群 → 配信開始** in the scene panel. RViz has **MID-360S PointCloud** enabled. Stop with **配信停止**. Sensor streaming defaults OFF; the physical sensor stays mounted. Server users use the same panel in the browser or the ROS services below.

```bash
oa-ros service call /openarm/lidar/set_enabled std_srvs/srv/SetBool '{data: true}'
```

```bash
oa-ros service call /openarm/lidar/status std_srvs/srv/Trigger '{}'
```

```bash
oa-ros topic echo /lidar/points --once --field header
```

| Interface | Type | Meaning |
|---|---|---|
| `/lidar/points` | `sensor_msgs/msg/PointCloud2` | Metre XYZ in `mid360s_link`, simulation timestamp |
| `/openarm/lidar/set_enabled` | `std_srvs/srv/SetBool` | Enable/disable point clouds; disable sends an empty cloud |
| `/openarm/lidar/status` | `std_srvs/srv/Trigger` | JSON: enabled, error, points, scan_ms, last_sim_time, rate limits |
| `mid360s_mount` | fixed TF link | Bottom mounting datum |
| `mid360s_link` | fixed TF link | Optical origin 47 mm above bottom in sensor coordinates |

TF is published by robot_state_publisher from generated URDF, not a second broadcaster. MuJoCo and MoveIt use the same mounting geometry. The housing/bracket are included in collision checking.

## Fixed project mount

Relative to `openarm_body_link0`, bottom datum XYZ = (0.065, 0, 0.420) m, rotation = 55 degrees nose-down about +Y. The optical origin is approximately (0.103500, 0, 0.446958) m. Forward-section vertical coverage is -62 to -3 degrees. Full coverage is a tilted 360-degree band, not a rectangular camera image. The support is a project approximation, not an official OpenArm or Livox bracket. Height/angle are design values, not a measured real-robot calibration. The pre-existing chest D435 and wrist cameras stay in place.

To change mounting settings edit `docker/app/lidar_config.json` and rebuild. If changing the mount, also redesign the bracket mesh; merely changing TF does not reposition the hardware support.

## Performance and limitations

- Default: at most 5 clouds/s, 800 attempted rays/cloud (4000 rays/s); actual rate also depends on simulation snapshots and CPU. This is deliberately below device throughput for VMware.
- ROS parameters `fps` (0 < fps <= 20) and `rays_per_frame` (32..20000) are startup settings for lidar_node.py. Snapshot feed is currently 5 Hz in simulation time; raising fps alone cannot create newer states.
- 360-degree azimuth, -7..+52 degree elevation, 0.1..40 m range gate. 40 m is a conservative simplified cap, not the actual direction/material-dependent range envelope.
- Changing low-discrepancy ray directions approximate non-repetitive coverage. They do not reproduce Livox's proprietary optical trajectory, exact density, or per-point acquisition timing. Each cloud is an instantaneous simulation snapshot.
- Only XYZ is published. No fabricated measured reflectivity, confidence tags, hardware timestamps, or IMU stream. Transparent objects are treated as opaque geometric surfaces; material-dependent noise and multipath are not simulated.
- Geometry is raycast on a separate MuJoCo copy. It never steps the physics state or sends joint commands. Hidden table/objects and invisible collision proxies are excluded; visible arms can occlude the scene.
- This does not enable MoveIt Octomap updates or change grasp selection. Existing ground-truth collision synchronization remains. Side-grasp candidate generation is a separate task.

## CAD provenance

User supplied `mid-360S.stp` from Livox downloads; conversion metadata and SHA-256 are in `docker/app/lidar_assets/SOURCE.json`. Source CAD uses +Y up and connector toward +X; runtime uses +Z up and connector toward -X according to the manual. Visual mesh was tessellated and simplified. Conservative collision envelope and bracket are generated geometry. Original STEP/PDFs are not copied into the repository.

References: Livox Mid-360S User Manual (2026), pages 11, 15-16, 19, 22; https://www.livoxtech.com/mid-360s/downloads . Manual specifies bottom mounting, four M3 holes depth 5 mm, airflow gap >=10 mm, and a thermally conductive mounting plate. Simulated bracket is not a manufacturing drawing or thermal validation.

## Verification

`tests/lidar_runtime_check.py` is an explicit integration check for a disposable running simulator. It changes table/camera/LiDAR state; do not run it during a user demo.

```bash
python /workspaces/OpenArm_sim/tests/lidar_runtime_check.py
```

Mount placement was moved down the column to preserve the existing chest RGB/depth camera field of view. This project position is below the chest, not inside the chest shell.

## Memory use
Camera streams share one rendering context without changing stream resolution,
intrinsics, or optical transforms. Sensor models keep the joint/mocap layout but
omit invisible environment geometry and unreferenced meshes. Switching an object
on/off rebuilds the sensor model, so sensor delivery may pause briefly. The
physics/control model is unchanged. Disabling a sensor releases its model and
rendering resources. LiDAR uses flat placeholder textures because RGB pixels do
not affect ideal geometric ray intersections. This is not a guarantee of an
unlimited number of visible YCB objects on an 8GB host.
