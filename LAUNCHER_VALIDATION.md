# Environment validation (2026-09-14)

Ubuntu 24.04 VMware, 4 vCPUs, 7.7 GiB RAM, CPU rendering.

- All five ROS controllers active; 18 robot joints remain independent of object free joints.
- Box and bottle settle onto the table and move under applied force.
- GUI placement, removal, random repositioning and camera stop checked.
- RGB, raw depth, aligned depth, CameraInfo and static TF received.
- Dynamic object poses appear in the MoveIt planning scene.
- Camera uses ideal simulated optics. Official chest mount assembly transform is NOT calibrated; camera_config.json marks this explicitly.
- End-to-end visual recognition and autonomous grasping are not included or validated.

Validation scripts are outside the distributed repository. Removed historical scripts are backed up under /home/mignon/openarm-validation-archive/20260914-182208 on the development VM.
