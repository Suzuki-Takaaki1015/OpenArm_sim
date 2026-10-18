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

- Default: **dense**, at most 5 clouds/s, 40000 attempted rays/cloud (200000 rays/s). The scene GUI offers **light** (800 rays/cloud), **standard** (8000), and **dense** (40000); density can change during streaming without restarting physics. Restarting the node restores the configured default.
- The [official MID-360S specification](https://www.livoxtech.com/mid-360s) is 200000 points/s. Dense mode attempts 200000 rays/s at 5 Hz; this is a computation budget, not a promise of device-equivalent output. Rays missing geometry or outside the range gate are omitted. CPU cost can reduce the actual rate. `/openarm/lidar/status` reports returned `points`, measured wall-clock `cloud_hz` (last interval), and `scan_ms`; the GUI shows points and Hz. This geometric raycast runs on CPU, not CUDA.
- RViz displays the latest cloud (Decay Time 0). No artificial point duplication or accumulated stale geometry is used. Increasing decay time manually accumulates previous measurements, including old object poses.
- ROS parameters `fps` (0 < fps <= 20) and `rays_per_frame` (integer 32..40000, also no greater than 200000/fps) configure lidar_node.py. `fps` is startup-only; `rays_per_frame` can be changed live with the GUI or ROS parameter service `/openarm_mid360s_sim/set_parameters_atomically`. Snapshot feed is currently 5 Hz in simulation time; raising fps alone cannot create newer states.
- 360-degree azimuth, -7..+52 degree elevation, 0.1..40 m range gate. 40 m is a conservative simplified cap, not the actual direction/material-dependent range envelope.
- Scan directions replay Livox-SDK's published **MID-360** reference CSV, preserving row order and azimuth. Its elevation range (-7.2123..52.164 degrees) is affinely mapped to MID-360S (-7..52 degrees). This is a related-device approximation, **not measured/calibrated MID-360S scanning**. See `docker/app/lidar_assets/SCAN_SOURCE.json` and `LIVOX_SCAN_LICENSE.txt` for pinned source, hashes, transformation and license.
- The CSV's `Time/s` column contains integer row indices, not seconds. We assign the target's nominal 200000 samples/s; the 800000-row reference repeats every 4 seconds of simulation time. This finite replay is not indefinitely non-repetitive.
- Each published cloud covers the directions of a 1/fps scan window ending at the snapshot simulation timestamp (0.2 seconds by default). Sampling phase follows simulation time, including skipped callbacks, time resets and live density switches. Reduced density selects source samples across the same window, rather than shortening the window or repeatedly selecting one interleaved beam.
- Rays are intersected against **one instantaneous scene snapshot**. Per-point motion distortion, rolling acquisition and deskew are not implemented. The source's temporal direction pattern is retained, but a moving scene is not physically integrated over that window. There is no automatic cloud accumulation and no invented fill-in points.
- Only XYZ is published. No fabricated measured reflectivity, confidence tags, hardware timestamps, or IMU stream. Transparent objects are treated as opaque geometric surfaces; material-dependent noise and multipath are not simulated.
- Geometry is raycast on a separate MuJoCo copy. It never steps the physics state or sends joint commands. Hidden table/objects and invisible collision proxies are excluded; visible arms can occlude the scene.
- This does not enable MoveIt Octomap updates or change grasp selection. Existing ground-truth collision synchronization remains. Side-grasp candidate generation is a separate task.

## CAD provenance

User supplied `mid-360S.stp` from Livox downloads; conversion metadata and SHA-256 are in `docker/app/lidar_assets/SOURCE.json`. Source CAD uses +Y up and connector toward +X; runtime uses +Z up and connector toward -X according to the manual. Visual mesh retains all 111613 triangles of the original CAD tessellation. Quadric decimation was removed because it visibly damaged the dome and cooling fins. Mount coordinates and conservative collision geometry are unchanged. Conservative collision envelope and bracket are generated geometry. Original STEP/PDFs are not copied into the repository.

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

The launcher applies no Docker CPU or RAM quota and no RAM-based density reduction. Software rendering can use all CPUs reported by Docker instead of a fixed eight-thread cap. GPU rendering is selected when available. Retaining one shared camera context and excluding invisible sensor geometry are efficiency improvements, not reduced sensor resolution. Both RViz and MuJoCo windows remain enabled by default.


## Scan reference and small-object validation

Source: [Livox-SDK/livox_laser_simulation](https://github.com/Livox-SDK/livox_laser_simulation/tree/1cce1073633a062b92e30243a4c2920e45551bb5), `scan_mode/mid360.csv` (MIT). The reference is bundled as compressed float32 azimuth/zenith angles for offline startup. No network download is needed at runtime. For reproduction, download that exact CSV and run inside the development container:

```bash
python scripts/import_livox_scan.py /path/to/mid360.csv --output /tmp/mid360_scan.npz
```

The [MID-360S manual](https://www.livoxtech.com/mid-360s/downloads), sections 2.1–2.2, specifies the FOV and illustrates sparse short scans becoming denser with integration. We do not claim the supplied MID-360 reference matches the MID-360S manual's exact coverage curve or that 200000 configured rays/s guarantees measured device throughput.

`tests/lidar_pattern_model_check.py` compares the previous generator and vendor reference at equal ray budgets, using each actual OpenArm model: 1 cm worktable bins, 10/20/40 mm cubes at 25 placements across 20 phases, and an opaque-wall occlusion check. It measures single-window misses and five consecutive windows (1 simulated second of directions), not one wall-clock second on a slow host. A point hit is not an object detector or a grasp-success guarantee. Tests assume static, opaque, geometrically visible surfaces; they do not model material-dependent returns or beam divergence.

```bash
python /workspaces/OpenArm_sim/tests/lidar_pattern_check.py
python /workspaces/OpenArm_sim/tests/lidar_pattern_model_check.py --output /tmp/lidar-pattern-report.json
```

Exact results and limitations are in [tests/LIDAR.md](tests/LIDAR.md). With RViz Decay Time 0, short-window gaps remain visible; we do not conceal them by enlarging points or retaining stale object positions.
