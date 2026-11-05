# 04. Software deployment, firmware flashing and versioning

## 1. How Robotont software is deployed today

- The workspace `~/ros2_ws/src` is populated with `vcs import` from a `.rosinstall` that names
  branches, not versions: `jazzy-devel` on the NUC branch of `robotont-setup`, `jazzy` on the RPi
  branch. `jazzy-devel` is behind `jazzy` in four repositories (see [01](01-repository-map.md)).
- Everything is built on the robot with `colcon build`. Dependencies come from `rosdep`, and
  the RPi branch additionally runs `vcs pull` on every run.
- `robotont.service` starts `robotont_support robotont_bringup.launch.py` at boot. Updates are
  activated by rebooting.
- The robot keeps no record of what was deployed, other than the git checkouts themselves.
- Neither `package.xml` versions nor git tags are maintained: `robotont_driver` is tagged 0.1.4
  (2024-05-19) while its `jazzy` branch has 2026 commits; the description packages are at 0.0.0.

### Compatibility coupling between software and firmware

The serial protocol grew in 2026, and driver and firmware must match:

| Packet | Firmware (`v3.0-devel`) | Driver (`jazzy`) |
|---|---|---|
| `ODOM:x:y:z:vx:vy:vz` | always | required for odometry |
| `BATSTATE:` 11 values (motor current, OBC current, wall V, battery V, 5 cell V, cell temp, MOSFET temp) | commits between 2025-11-28 and 2026-02-07 | the plugin accepts **exactly 12 fields**; the 2024 firmware sent 4 values, which the current driver silently ignores (no battery state) |
| `JS` (wheel position, velocity, effort) | since 2026-02-05 | joint state plugin |
| `RS`, `MS`, `DC`, `OR`, `LD`, `LM`, `LS` (inputs) | all | motor and LED plugins |

The fleet repository should keep a small compatibility table per software release: the minimum
firmware commit or version required for full function.

## 2. Proposed versioning for the MVP

1. A release is a vcstool file in this repository, for example `releases/2026.09.repos`, with
   every repository pinned to a tag or a commit SHA (`vcs export --exact` produces this format
   from a known-good stack). Creating a release is a Git commit here, which keeps Git the
   source of truth.
2. `group_vars` sets `robotont_software_release: "2026.09"`; a Semaphore task can override it
   per run.
3. The `robotont_software` role compares the pinned SHAs with `vcs export --exact` on the robot.
   Same SHAs and an existing `install/` directory means "nothing to do". Otherwise it checks out,
   runs `rosdep install`, builds, writes `/etc/robotont/release` and restarts the service.
4. `/etc/robotont/release` is the "software version" for the health check and for monitoring:

   ```
   ROBOTONT_RELEASE=2026.09
   ROBOTONT_BUILT=2026-09-30T12:00:00Z
   robotont_driver=41abb27
   robotont_support=a8d171f
   ...
   ```

5. Upstream request: tag the `jazzy` branches (`robotont_driver`, `robotont_msgs`,
   `robotont_support`, `robotont_description`, `robotont_nuc_description`,
   `robotont_lite_description`) when they are in a known-good state, so releases can reference
   tags instead of SHAs. Until then SHAs work.

Later steps in the same direction, not for the MVP: building `.deb` packages from the stack,
or a container image as sketched in `robotont-supervisor`. The role boundary (`robotont_software`
means "make the desired release run") stays the same in both cases, which is what the context
document asks for (sections 10 and 17).

## 3. Firmware: facts

| Item | Finding |
|---|---|
| MCU | STM32F407VGT6 at 168 MHz on the custom Robotont 3 mainboard (`gen3.0.0-v0.2.0`, 2023-11) |
| Toolchain | PlatformIO, `platform = ststm32@~15.6.0`, `framework = stm32cube`, environments `robotont_stlink` (default) and `robotont_jlink`; `pio run` produces `.pio/build/robotont_stlink/firmware.bin` and `.elf` |
| Documented upload path | SWD only ("a programmer with the SWD interface is required"). The README mentions ST-Link udev rules (`49-stlinkv2*.rules`) and `stlink-tools` |
| Board features (schematic) | `SWD connector` (SWDIO, SWCLK, NRST), `JP_BOOT0` jumper, USB-C to the on-board computer. No on-board ST-Link |
| USB identity | CDC ACM, VID 0x0483 PID 0x5740, product string "Robotont Virtual ComPort", serial number derived from the MCU unique id (`Get_SerialNum`), so each mainboard is distinguishable with `udevadm info` |
| Version reporting | None over serial. The OLED "Firmware information" screen prints hard-coded strings ("Firmware ver 3.0.0", "Last update 2024-04-04") |
| Releases and CI | No tags for gen 3, no GitHub Actions workflow, no published binaries. Tags 2.1.1 to 2.1.3 belong to the gen 2 mbed firmware |
| Current branch | `v3.0-devel` (Veiko, 19 commits in 2025 and 2026, last 2026-06-18). `v3.0-devel-leonid` (the local checkout) stopped in May 2024 |
| Bootloader support in firmware | None (no jump-to-bootloader or DFU code) |
| Second MCU | ATtiny88 power-management controller, flashed with Arduino-as-ISP through a 2x3 header under the OLED. Not reachable from the on-board computer |

## 4. Options for remote firmware updates

| | A. ST-Link permanently connected to the NUC | B. USB DFU via a firmware "enter bootloader" command | C. Status quo |
|---|---|---|---|
| Extra hardware per robot | ST-Link V2 (clone) plus SWD cable, inside the robot | none | none |
| Firmware change needed | none | yes: a serial command that jumps to the STM32 system bootloader (`0x1FFF0000`), or sets a flag and resets | none |
| Tooling on the robot | `stlink-tools` (`st-flash`) or `openocd`, from apt | `dfu-util`, from apt | PlatformIO on a developer PC |
| Remote-capable | yes | yes, once the command exists | no |
| Recovery after a failed flash | always: SWD works regardless of firmware state | needs a person to set `JP_BOOT0` and power-cycle | not applicable |
| Version verification | read back flash and compare with the `.bin` | same after re-enumeration, or a `VER` command | none |
| Effort | Ansible role only | firmware feature plus Ansible role | none |

Recommendation: **A** for the fleet (reliable, recoverable, no firmware work), with **B** as a
later improvement to remove the hardware. Both need release artifacts (section 5).

Flow for option A, matching the context document's conceptual workflow:

```
Semaphore "Update Firmware" (robotont_firmware_version pinned in group_vars)
  -> Ansible role firmware
      1. ensure stlink-tools and 49-stlinkv2*.rules are installed
      2. copy releases/firmware/robotont-firmware-<ver>.bin (+ .sha256) to the robot
      3. st-flash read of the same size from 0x08000000, compare with the .bin
         -> identical: report "already at <ver>" and stop (idempotent)
      4. systemctl stop robotont.service
      5. st-flash --reset write <bin> 0x08000000
         (st-flash verifies after writing; unverified here, stlink-tools is not installed locally)
      6. wait for /dev/robotont to re-enumerate, read a few ODOM lines
      7. write /etc/robotont/firmware-version
      8. systemctl start robotont.service, run the health check
```

Because the firmware cannot report its version, `/etc/robotont/firmware-version` is bookkeeping,
and the flash read-back in step 3 is the actual check. A `VER` command in the firmware (version
and git hash, set from a build flag) would close this gap; the driver could then publish it.

## 5. Firmware artifacts

Proposed, to be done in `robotont-firmware`: a GitHub Actions workflow that runs
`pio run -e robotont_stlink` on every `v3.*` tag and attaches
`robotont-firmware-<tag>.bin` and `.elf` to a GitHub release. Until the workflow exists, a
maintainer builds the `.bin` locally and commits it with a checksum under `releases/firmware/`
in this repository (the binaries are in the order of 100 KB). The fleet role never compiles
firmware on the robot.

## 6. Signals available for monitoring (Milestone 3)

| Question (context section 4) | Source on the robot | Exposure |
|---|---|---|
| Online / offline, uptime, CPU, RAM, disk, temperature | `prometheus-node-exporter` (apt) | scraped by Prometheus |
| Robotont service running | `systemctl is-active robotont.service` | node_exporter systemd collector, or the textfile below |
| Mainboard reachable | `/dev/robotont` exists; the driver logs "No data received ... forcing port reconnect" when silent for 5 s; `battery_state` and `odom` publishing | textfile metric `robotont_mainboard_connected`, written by a small timer script |
| Software version | `/etc/robotont/release` | `robotont_info{release=...}` textfile metric written by the `robotont_software` role |
| Firmware version | `/etc/robotont/firmware-version` (bookkeeping, see above) | same `robotont_info` metric, label `firmware` |
| Mainboard identity | USB serial number of 0483:5740 | optional label |
| Battery voltage and percentage | `sensor_msgs/BatteryState` on `battery_state` (voltage, percentage mapped from 15.0 to 21.0 V, cell voltages, temperatures) | optional: a tiny rclpy node, or `ros2 topic echo --once` in the timer script |
| E-stop pressed | read by the firmware over I2C since 2026-06; not published by the driver | future |

The textfile collector approach avoids a new network service on the robot: one script on a
systemd timer writes `/var/lib/prometheus/node-exporter/robotont.prom`.
