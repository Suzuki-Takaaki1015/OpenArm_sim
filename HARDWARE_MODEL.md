# Hardware and contact model

## Primary sources

- OpenArm motor specifications: https://docs.openarm.dev/hardware/openarm-2.0/motor/
- Version continuity (same motor lineup in 1.0 and 2.0): https://docs.openarm.dev/overview/whats-new-in-2.0/
- DM-J4310-2EC V1.1 manufacturer manual, hosted by Enactic: https://damiao.enactic.ai/en/products/hardware/dm-j4310-2ec-v1.1/
- OpenArm 1.0 linkage and 88 mm jaw opening over 60 degrees motor travel: https://docs.openarm.dev/hardware/specifications/gripper/
- Official contact settings, pinned research revision: https://github.com/enactic/openarm_mujoco/blob/ce761e2eb1079c3e7cafe515a375930adedad190/v2/openarm_bimanual.xml

## Torque versus jaw force

Official motor rated/peak output torque is 20/40 Nm (DM8009P, joints 1–2), 9/27 Nm (DM4340, joints 3–4), and 3/7 Nm (DM4310, joints 5–7 and gripper motor). Arm actuator force caps retain the official peak limits. Thermal and electrical current limits are not simulated, so peak capability is not a continuous-duty guarantee.

The v1 MJCF replaces the gripper linkage with two prismatic joints. Their actuator units are **newtons**, not motor Nm. The 88 mm total opening and 60 degree travel imply an average 0.042 m/rad displacement per jaw. Ideal virtual work gives about 35.7 N per jaw from 3 Nm, assuming equal loading. The real linkage ratio varies with angle and efficiency is not measured. The simulation therefore uses a deliberately lower **15 N per jaw**, not an assertion of calibrated physical gripping force. A jaw servo of 1500 N/m and 10 Ns/m is identical on both sides.

## Why the previous box slipped

The pinned v1 file used left finger motor actuators and right finger position actuators. The previous bridge converted only motor actuators; the right fingers retained a 100 N/m gain and a different force cap. Both fingers now use the same implicit PD implementation and SI-unit limits.

Force adjustment alone still yielded only about 7.4 cm lift for a 10 cm command. The official v2 MJCF documents jaw creep with the pyramidal friction cone. Adopting its elliptic cone, impratio=10 and condim=4 on contact-enabled finger geoms gave about 9.7 cm physical lift in the v1 box test. This also enables the existing torsional-friction coefficient. No welds, teleports, gravity removal or invisible attachments hold the object up.

The demo now requires at least 9 cm physical lift. The bilateral demo additionally checks both objects for less than 5 mm height drift over a 3 second hold. AttachedCollisionObject affects MoveIt planning only. Allowed contacts are the assigned fingers with their own box, and each box with its support table; cross-arm box contact stays forbidden. The prior collision matrix is restored afterward.

## Verified v1 bilateral result

Both arms ran with a shared start timestamp and finished pickup, a three-second hold, replacement and return home. Each box rose 9.7 cm for a 10 cm command; measured hold-height variation was 0.62 mm on each side. The left hand origin has the same -6 mm world-Y jaw-centre offset for the chosen downward orientation, so its target is Y=+0.186 m for a box at +0.180 m. Blindly mirroring the right hand offset caused premature box contact and has been corrected.
