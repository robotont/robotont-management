# 08. Hardware test guide

How to verify, by hand, first that v1 reproduces the current setup through Semaphore
([06](06-v1-reproduce-current-setup.md)), then that the container runtime works on one robot
([07](07-container-runtime.md)). Every step lists the command, where to run it, what to expect
and where to look when it fails. Record results in the test logs at the end of docs/06 and docs/07.

## 0. Before you have a robot (can be done now)

1. Review and commit the pending work in this repository; push it when you want Semaphore to
   clone from GitHub (pushing is a network action from your machine).
2. Start Semaphore and configure it once, per [semaphore-setup.md](semaphore-setup.md): project,
   key store (`peko-ssh`, `peko-sudo`), repository (GitHub URL, or the local-path fallback with
   the bind mount so nothing needs to be pushed), inventory file, environment `robotont-secrets`
   with `wifi_pass`, and the task templates. No robot is needed for this part.
3. Make sure the private key that opens the robots exists on this machine (robotont-setup
   convention: `~/.ssh/robotont`). If it does not, you will run `ssh-copy-id` at the robot (A1).
4. Bring an Ethernet cable. Provisioning switches the robot's Wi-Fi into hotspot mode and cuts a
   Wi-Fi session.

## Raspberry Pi (Robotont 3 Lite) on Ubuntu Server

Write the card with Raspberry Pi Imager: Ubuntu Server 24.04 LTS (64-bit), OS customisation
with hostname `robotont-<id>`, user `peko`, the lab Wi-Fi, SSH enabled with your public key. Boot,
find the IP in the router, `ssh peko@<ip>`. Nothing else is done by hand: `provision.yml` installs
NetworkManager and BlueZ and completes the network handover (role `robotont_headless`) before the
upstream playbook runs. Put the Pi in the `robotont_rpi` group, run Provision with
`--skip-tags camera` unless the IMX500 camera is fitted, and over Ethernet.

## What you need at the robot

- A Robotont 3 (Intel NUC) powered on, mainboard connected over USB, on the same network as your
  machine. Its IP address (`ip -4 addr` on the robot, or the router's DHCP list).
- The `peko` password (needed for sudo).
- Optional: a laptop with ROS 2 Jazzy for topic checks (the robot itself works too over SSH), a
  gamepad already paired with the robot for drive tests.

Set these once in a terminal on your machine and reuse them below:

```
cd ~/uni/robotont/robotont-management
export ROBOT=robotont-1            # inventory name of the robot under test
# edit inventory/hosts.yaml: ansible_host of $ROBOT = the robot's IP, robotont_id = its number
```

## Part A: v1, reproduce the current setup

| Step | Command (where) | Expected | If not |
|---|---|---|---|
| A1 Connectivity | `ssh -i ~/.ssh/robotont peko@<ip>` (your machine) | a shell on the robot, prompt `peko@robotont-N` | `Permission denied (publickey)`: run `ssh-copy-id -i ~/.ssh/robotont peko@<ip>` once, with the password |
| A2 Ansible reaches it | `ansible robots -m ping --limit $ROBOT` | `pong` | check `ansible_host` in the inventory; `ssh -v` for key problems |
| A3 Test connection | `ansible-playbook playbooks/test_connection.yml -K --limit $ROBOT` | all tasks ok: submodule present, `community.general` found, ping, `id -un` is `root` | submodule: `git submodule update --init`; sudo: wrong password |
| A4 Health check, read-only | `ansible-playbook playbooks/healthcheck.yml -K --limit $ROBOT` | report with `ActiveState=active`, `mainboard_present: true`, hostname `robotont-N`, and the workspace commits (`vcs export`). **Save this report: it is the current state you are reproducing.** | see Troubleshooting: service, mainboard |
| A5 Same two tasks from Semaphore | UI: "Test connection", then "Health Check" (with `--limit $ROBOT` in the CLI args) | same output as A3 and A4 in the task log | Semaphore lacks the submodule: fallback in semaphore-setup.md section 8; `.local` names do not resolve in the container: use the IP |
| A6 Restart services | UI: "Restart services" | task green; A4 again shows `NRestarts` unchanged and `ActiveState=active`; `ros2 topic list` on the robot shows `/odom` again after about 10 s | `journalctl -u robotont -n 50` on the robot |
| A7 Reboot | UI: "Reboot" | robot comes back within 2 to 3 minutes, task green, Health Check green | wait longer on first boot after updates; check power |
| A8 Set up service | UI: "Set up service" | `changed=0` on a robot provisioned from `jazzy-devel-veiko` (unit identical), or `changed=1` on an older robot; service active afterwards | the unit differs on purpose only if the robot predates the Jazzy port |

Milestone reached after A5 to A8: every non-destructive operation of the current setup runs from
Semaphore.

**A9 Provision (destructive, 30 to 60 minutes).** Only on a spare robot, a fresh Ubuntu 24.04
install with user `peko`, or a robot you are willing to reinstall. Robot on **Ethernet**.

1. UI: "Provision Robotont" with CLI args `--limit $ROBOT` and the environment holding `wifi_pass`.
2. Expect: apt upgrade, ROS install, workspace wipe and full `colcon build`, `netplan apply`
   (Wi-Fi becomes the hotspot `robotont-N`), then a reboot. The reboot task may show as failed or
   as skipped; upstream sets `ignore_errors`. The task ends green or with that one warning.
3. After the reboot: "Health Check" green; `ssh peko@robotont-N` (or the IP) shows the hostname;
   on the robot `source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=N; ros2 topic list`
   shows `/odom`, `/battery_state`, `/joint_states`, `/cmd_vel`; `ros2 topic echo --once
   /battery_state` shows a voltage around 15 to 21 V; the hotspot `robotont-N` is visible on
   Wi-Fi; unplug Ethernet and the robot keeps running.
4. Drive it with the gamepad (teleop is part of the bringup).
5. Do not run Provision again on the same robot as an "update": v1 rebuilds and reboots every time
   by design (see docs/06, "What v1 knowingly keeps").
6. Write date, robot, duration and result into the test log of docs/06.

## Part B: container runtime (D1) on the same robot

Prerequisite: Part A green on this robot, so it is in the adopted state (host ROS working). The
robot needs internet for B3 (base image, apt, GitHub), so Ethernet or the client Wi-Fi profile.

| Step | Command (where) | Expected | If not |
|---|---|---|---|
| B1 Deploy the runtime | `ansible-playbook playbooks/deploy_runtime.yml -K --limit $ROBOT` | Docker installed; run ends with the health check green and the runtime line `container runtime, preset host`. On the robot: `robotont-status` prints `preset: host`, `service: active`, `containers: none`; `systemctl cat robotont.service` shows the new unit from `/etc/systemd/system`; `journalctl -u robotont -n 30` shows the bringup started by `run.sh`; `ls /lib/systemd/system/robotont.service` says no such file; `docker ps` is empty; `cat /var/lib/prometheus/node-exporter/robotont.prom` shows `robotont_preset_info{preset="host",...} 1` | Docker apt repo: robot needs internet; `robotont.service` failed: `journalctl -u robotont -n 100`, most likely the workspace path in `ROBOTONT_HOST_WS` |
| B2 First container, no hardware | `ansible-playbook playbooks/switch_preset.yml -e preset=test-talker -K --limit $ROBOT` | on the robot `docker ps` shows `robotont-talker` running; `source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=N; ros2 topic echo /chatter` prints `hello from robotont-N` (container to host DDS over host networking); `journalctl -u robotont -f` shows the talker's output; `robotont-preset status` lists the container; health check green with `containers_running: 1/1`. The mainboard is idle in this preset, by design | image pull failed: robot has no internet; `sudo: a password is required`: `sudo visudo -cf /etc/sudoers.d/robotont-preset` |
| B3 Build the runtime image | `ansible-playbook playbooks/build_images.yml -K --limit $ROBOT` (15 to 30 min) | `docker image ls ghcr.io/robotont/robotont-ros` shows tag `2026.09` | run the build by hand to see the error: `docker compose --env-file /etc/robotont/robotont.env -f /opt/robotont/images/compose.build.yaml build robotont-ros` |
| B4 Containerised bringup | `ansible-playbook playbooks/switch_preset.yml -e preset=driver -K --limit $ROBOT` | `docker ps` shows `robotont-driver`; `docker exec robotont-driver ls -l /dev/robotont /dev/ttyACM0` lists both; `ros2 topic hz /odom` on the robot shows a steady rate; `ros2 topic echo --once /battery_state` has a voltage; gamepad drives the robot; health check green | `Permission denied` on the device: `ls -l /dev/robotont` must be mode 0666 (udev rule) and `ls -l /dev/ttyACM0` major 166; no `/odom`: `docker logs robotont-driver` |
| B5 Replug test | unplug the mainboard USB cable for 5 s, plug it back (robot) | `/odom` resumes within about 10 s; `docker inspect -f '{{.RestartCount}}' robotont-driver` stays `0`; `grep device_present /var/lib/prometheus/node-exporter/robotont.prom` goes 0 then 1 | if the driver never recovers: note it; the documented fallback is `devices:` mapping plus a restart |
| B6 Survives a reboot | `sudo reboot` (robot) | after boot `robotont-status` shows preset `driver`, container running, `/odom` publishing | `systemctl status docker robotont`; `journalctl -b -u robotont` |
| B7 Rollback | `ansible-playbook playbooks/switch_preset.yml -e preset=host -K --limit $ROBOT` | `docker ps` empty, host bringup running again, health check green | `journalctl -u robotont -n 50` |
| B8 Soak | leave the robot on `driver` for a week of normal use | `systemctl show robotont -p NRestarts` low, `docker inspect -f '{{.RestartCount}}' robotont-driver` low, no complaints from students | collect the journal and open an issue |

Write date, robot, image id (`docker image inspect -f '{{.Id}}' ghcr.io/robotont/robotont-ros:2026.09`)
and results into the test log of docs/07.

## Potential issues to test (found on 2026-09-26, robotont-123, Ubuntu Server on a Pi 5)

1. **NetworkManager handover on a headless Server install.** First attempt: NetworkManager was
   already running when `netplan apply` switched the renderer, tried to take `wlan0` while the
   old netplan-managed wpa_supplicant still held it, failed five times and gave up (journal:
   "wpa_supplicant couldn't grab this interface ... giving up"). The Wi-Fi kept working only
   because the old networkd association stayed up. Fix in `roles/robotont_headless`: apply, stop the
   leftover `netplan-wpa-*` units (netplan apply leaves them running) and restart NetworkManager
   in one detached step, then assert that NetworkManager has a connected interface. **To re-test**: fresh Server card, run `provision.yml`; expected report shows
   `wlan0:wifi:connected` (and `eth0` when plugged), `.local` name resolves, SSH survives.
2. **Addresses change during the handover.** NetworkManager identifies itself to DHCP differently
   from systemd-networkd, so `eth0` came back with another lease and a `wait_for_connection` on
   the pinned address never returned. Always address robots by `robotont-N.local` (avahi is now
   part of the role) or by a DHCP reservation on the router; never pass `-e ansible_host=<ip>`
   for a first Provision.
3. **Unplugging Ethernet during the run** aborts it at the wait step. If a run is aborted after
   the handover: reboot the robot (NetworkManager owns everything from the next boot), check
   `nmcli device status`, then re-run Provision; the role's file tasks report `ok` and the
   handover is not repeated.

4. **Missing `noble-updates` on the Imager-written Server image.** The Ubuntu Server 24.04 image
   from Raspberry Pi Imager had only the release and security suites in `ubuntu.sources`, so
   `ros-jazzy-desktop` failed with "held broken packages" (its `-dev` dependencies could not be
   resolved against the already updated runtime libraries). `roles/robotont_headless` now adds the
   updates suite when it is missing. **To re-test**: on a fresh card check
   `grep -r updates /etc/apt/sources.list.d/` before and after `provision.yml`.

5. **Upstream service template starts the camera and lidar unconditionally on Lite robots**
   (`camera:=true lidar:=true`). Without the camera `camera_node` dies and respawns every 3 s,
   filling the journal; without the lidar the rplidar node retries. Harmless, but an upstream
   ask: derive the arguments from the inventory (the container runtime already does this through
   `ROBOTONT_BRINGUP_ARGS`). **To test** once the camera and lidar are fitted: the respawns stop
   and `/rt<id>/scan` and `/rt<id>/camera/image_raw` publish.
6. **Driver opens `/dev/ttyACM0`, not `/dev/robotont`** (confirmed in the journal: "Error creating
   serial port: /dev/ttyACM0"). Works as long as the mainboard is the only ACM device. Upstream
   ask from docs/05 §4 stands. **To test** with the mainboard: `ls -l /dev/robotont /dev/ttyACM0`
   and `ros2 topic hz /rt<id>/odom`.

## Troubleshooting

| Symptom | Where to look | Usual cause |
|---|---|---|
| Test connection: "external/robotont-setup is empty" | your machine or Semaphore's checkout | `git submodule update --init`; Semaphore fallback A or B in semaphore-setup.md |
| `Permission denied (publickey)` | `ssh -v peko@<ip>` | the public key is not in `~peko/.ssh/authorized_keys`: `ssh-copy-id` |
| sudo check fails | Semaphore inventory sudo credential, or `-K` | wrong or missing peko password |
| Health check: `mainboard_present: false` | `lsusb | grep 0483:5740`, `ls -l /dev/ttyACM* /dev/robotont`, `cat /etc/udev/rules.d/99-robotont.rules`, `sudo udevadm trigger` | USB cable, mainboard power, missing udev rule |
| Service active but no `/odom` | `journalctl -u robotont -n 100` | wrong `ROS_DOMAIN_ID` in your shell (must equal the robot number); driver on `/dev/ttyACM0` while the board enumerated as `ttyACM1` |
| Provision seems stuck at the end | Semaphore task log | the reboot: wait 3 minutes, then Health Check |
| Session lost during Provision | Wi-Fi | `netplan apply` switched to hotspot mode; use Ethernet |
| compose prints "variable is not set" | `cat /etc/robotont/robotont.env` | env file incomplete or unreadable by peko (must be group `peko`, mode 0640) |
| `robotont-preset switch`: "sudo: a password is required" | `sudo visudo -cf /etc/sudoers.d/robotont-preset` | sudoers file missing or the systemctl path differs |
| Container cannot open `/dev/robotont` | `ls -l /dev/robotont /dev/ttyACM0` on the host | mode not 0666, or major not 166 (then extend `device_cgroup_rules`) |
| Laptop does not see the topics of a container | `docker inspect -f '{{.HostConfig.NetworkMode}}' robotont-driver` (must be `host`), `ufw status` (inactive), same `ROS_DOMAIN_ID` | preset service not extending `ros-app`, firewall re-enabled |
| `ros:jazzy-ros-base` cannot be pulled | robot's internet | robot in hotspot mode without uplink: connect Ethernet |
| After the handover `nmcli device status` shows `wlan0 unavailable` | `journalctl -u NetworkManager` ("couldn't grab this interface") | old wpa_supplicant still held the interface; `sudo systemctl restart NetworkManager` or reboot |
| `robotont-N.local` stops resolving after the handover | `systemctl is-active avahi-daemon` on the robot | avahi missing on Server (the role installs it) or restarting; use the IP from the router meanwhile |
| Image build fails on rosdep | build by hand and read the missing key | add it to `ROSDEP_SKIP_KEYS` or to the apt list in the Dockerfile |
| `Install ROS (jazzy-desktop)` fails with "held broken packages" | `apt-cache policy libdbus-1-dev libdbus-1-3` on the robot; `cat /etc/apt/sources.list.d/ubuntu.sources` | the updates suite is missing (Imager Server image); the headless role adds it, or add `noble-updates` by hand and `apt update` |

## What to report upstream after the tests

- Whether the containerised bringup opens `/dev/robotont` or only `/dev/ttyACM0` (docs/05 §4 item 7).
- Replug behaviour with the `/dev` bind mount (B5).
- Gamepad hot-plug inside the container (B4), and whether `SDL_JOYSTICK_DISABLE_UDEV=1` was needed.
- Anything the `jazzy-devel` bringup does that the `jazzy` one changed, before moving the release pins.
