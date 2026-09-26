# 01. Repository map

State of the downloaded Robotont repositories on 2026-09-23. Everything below was read from the
local clones in `~/uni/robotont` (working trees plus already-fetched remote branches, read with
`git show origin/<branch>:<path>`). No network access was used, so anything that lives only on
GitHub or on a robot is marked as unverified.

## Target platform

| Generation | On-board computer | OS / ROS | Mainboard MCU | Status |
|---|---|---|---|---|
| Robotont 3 | Intel NUC (x86_64) | Ubuntu 24.04, ROS 2 Jazzy | STM32F407VGT6 on the custom mainboard (`gen3.0.0-v0.2.0`) plus an ATtiny88 power-management MCU | Current target of this project |
| Robotont 3 Lite | Raspberry Pi 5 (arm64) | Ubuntu 24.04, ROS 2 Jazzy | Same mainboard | Supported by the `jazzy-rpi` setup branch and by `generation:=3lite` in the bringup |
| Robotont 2.1 | Intel NUC | Ubuntu 20.04, ROS 1 Noetic | Nucleo L476RG, mbed firmware | Legacy. ROS 1 code is listed below only to tell it apart |

## Repositories that matter for fleet management

| Repository | Why it matters | Branch to use | Last commit | Notes |
|---|---|---|---|---|
| `robotont-setup` | The existing provisioning Ansible. Primary source for reuse. | `jazzy-devel-veiko` (NUC) and `jazzy-rpi` (RPi 5). The default branch `noetic-devel`, which is checked out locally, is ROS 1. | 2025-12-03 / 2026-03-26 | Analysed in [02](02-existing-ansible-analysis.md). |
| `robotont_support` | `robotont_bringup.launch.py`, the single entry point started by `robotont.service`. | `jazzy` | 2026-03-13 | Launch arguments: `namespace`, `frame_prefix`, `generation` (2.1, 3, 3lite), `realsense`, `lidar`, `camera`, `slam`, `gamepad_conf`. |
| `robotont_driver` | Serial driver between ROS 2 and the mainboard. | `jazzy` | 2026-03-05 | Opens `/dev/robotont` at 115200 baud and reconnects on its own. Publishes `odom`, `battery_state` (sensor_msgs/BatteryState), `joint_states`. |
| `robotont_msgs` | Custom messages (LED module, PowerSupply). | `jazzy` | 2024-09-13 | |
| `robotont_description` | URDF for generations 2.1 and 3. | `jazzy` | 2026-01-26 | |
| `robotont_nuc_description` | URDF with NUC and RealSense D435i. | `jazzy` | 2025-10-28 | Used by the bringup when `realsense:=true`. |
| `robotont_lite_description` | URDF for Robotont 3 Lite. | `jazzy` | 2026-02-06 | |
| `robotont_navigation` | Nav2 parameters and launch. | `jazzy` | 2026-03-14 | Only in the RPi package list. |
| `robotont-firmware` | Mainboard firmware (PlatformIO, STM32Cube). | `v3.0-devel` | 2026-06-18 | `master` is the gen 2 mbed firmware, declared unmaintained in its README. The local checkout `v3.0-devel-leonid` stopped in May 2024. Details in [04](04-software-firmware-versioning.md). |
| `robotont-firmware-power-management` | ATtiny88 firmware. | `main` | 2024-03-21 | Flashed only via Arduino-as-ISP on a header under the OLED. Not automatable. |
| `robotont-electronics-mainboard` | Schematics. Tells us how the MCU can be flashed. | `main` | 2026-02-26 | Has an SWD connector, a `JP_BOOT0` jumper and `NRST`. No on-board ST-Link. |
| `robotont.github.io` | User documentation (Sphinx). | `jazzy` | 2026-04-06 | Documents PC-side setup, networking and SSH. The Generation 3 Lite build tab in `overview.rst` points to `robotont-setup` branch `jazzy-rpi` for software setup; the Generation 3 tab only links the replication package. No page on flashing firmware. |
| `robotont-supervisor` | Earlier experiment: a Flask supervisor that starts ROS containers and talks to the firmware over serial (`SC:` commands, matching firmware branch `v3.0-devel-jyrgen`). | `devel-jyrgen` | 2025-06-08 | Not merged, `main` is empty. Reference for the future containerised runtime, not for the MVP. |
| `robotont-management` | This repository. | `main` | 2026-09-20 | README with architecture pictures, empty inventory. |

### External code referenced but not on disk

The Jazzy package lists and the bringup launch file pull in repositories outside the `robotont`
organisation that were not downloaded:

| Dependency | Source | Referenced by |
|---|---|---|
| `demo_teleop` | github.com/robotont-demos, branch `jazzy` or `jazzy-devel` | `.rosinstall` (both Jazzy branches); the bringup always includes `teleop_joy.launch.py` |
| `demo_slam` | github.com/robotont-demos | `.rosinstall` (RPi); bringup when `slam:=true` |
| `laserscan_to_ranges` | github.com/ut-ims-robotics | `.rosinstall` (both); the bringup always starts it |
| `rplidar_ros` | github.com/Slamtec, branch `ros2` | `.rosinstall` (RPi); bringup for `3lite` |
| `realsense2_camera`, `depthimage_to_laserscan`, `camera_ros`, `joy` | apt (`ros-jazzy-*`) | bringup and teleop; availability in the Jazzy apt index not verified offline |

Fetching them for inspection needs network access and therefore an explicit go-ahead.

## Legacy or out-of-scope repositories

| Repository | State | Decision |
|---|---|---|
| `robotont_demos`, `robotont_tutorials`, `robotont_laserscan_to_distance`, `leap_motion_demo`, `robotont` (meta repo) | ROS 1 only (Melodic/Noetic branches, no Jazzy branch) | Ignore |
| `robotont_gazebo` | Noetic default; a `jazzy-devel-sygis` draft exists | Simulation, not needed on robots |
| `robotont_webapp` | ROS 1 (Node.js, ttyd, rosbridge). The Jazzy docs still mention the web UI on port 3000, but the Jazzy bringup does not start it | Ignore for the fleet MVP |
| `robotont_simple_simulator` | Jazzy, simulation only | Ignore |
| `robotont-hardware-x-2023-replication-package`, `robotont-frobt-2024-replication-package` | Snapshots for papers. The 2024 package pins `robotont-firmware` at `v3.0-devel` and mechanics at `gen3.0-devel` | Reference only |
| `robotont-mechanics*`, `robotont-electronics-*` (except the mainboard) | Hardware design files | Ignore |

## Branch and version conventions found

- ROS 2 packages use `jazzy` as the default branch and `jazzy-devel` as a development branch. In
  practice development lands on `jazzy` directly: `jazzy-devel` is *behind* `jazzy` in
  `robotont_driver` (5 commits), `robotont_description` (9), `robotont_support` (11) and
  `robotont_lite_description` (4). The NUC setup branch still imports `jazzy-devel`; the RPi
  branch imports `jazzy`.
- No software release tags since `robotont_driver` 0.1.4 (2024-05-19). `package.xml` versions
  are not maintained (driver still 0.1.4 with 2026 commits, descriptions at 0.0.0). A software
  version therefore has to be identified by git commit, or by a release name that this repository
  defines. See [04](04-software-firmware-versioning.md).
- Gen 3 firmware has no tags and no release artifacts. The OLED shows a hard-coded
  "Firmware ver 3.0.0 / Last update 2024-04-04" that no longer reflects the code.
- `robotont-setup` uses one branch per ROS distribution and per person (`*-veiko`, `*-sygis`),
  never tags.

## Maintainers

Veiko Vunder authored nearly all 2025 and 2026 commits in `robotont-setup`, `robotont_support`,
`robotont_driver` and `robotont-firmware`, and is the maintainer listed in the `package.xml`
files. Karl Kruusamäe co-maintains the description and simulator packages. Markus Erik Sügis
produced the first Jazzy port of the setup repository (April 2025). Changes to the setup roles or
to the firmware should be coordinated with Veiko.
