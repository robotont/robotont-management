# 08. Hardware test guide

How to verify, by hand, the host setup of a robot through Semaphore (Part A) and the workspaces
on it (Part B, [07](07-container-runtime.md)); the legacy host-ROS path ([06](06-v1-reproduce-current-setup.md))
is the optional tail of Part A. Every step lists the command, where to run it, what to expect
and where to look when it fails. Record results in the test logs at the end of docs/06 and docs/07.

## 0. Before you have a robot (can be done now)

1. Review and commit the pending work in this repository; push it when you want Semaphore to
   clone from GitHub (pushing is a network action from your machine).
2. Start Semaphore per [semaphore-setup.md](semaphore-setup.md): fill in `server/.env`, then
   `docker compose -f server/compose.yaml up -d`. The project, keys, repository, inventory,
   environment and the four tasks are created automatically. No robot is needed for this part.
3. Make sure the private key named in `server/.env` opens the robots. If it does not, you will
   run `ssh-copy-id` at the robot (A1).
4. Bring an Ethernet cable. "2. Setup ROS" switches the robot's Wi-Fi into hotspot mode and cuts
   a Wi-Fi session.

## Raspberry Pi (Robotont 3 Lite) on Ubuntu Server

Write the card with Raspberry Pi Imager: Ubuntu Server 24.04 LTS (64-bit), OS customisation
with hostname `robotont-<id>`, user `peko`, the lab Wi-Fi, SSH enabled with your public key. Boot,
find the address (`robotont-<id>.local`, or the IP in the router). Nothing else is done by hand:
"1. Setup Ubuntu" installs NetworkManager and BlueZ, completes the network handover and reboots
once (role `robotont_headless`), "2. Setup ROS" runs the upstream playbook. Camera = no unless the IMX500
camera is fitted. Run over Ethernet.

## What you need at the robot

- A Robotont powered on, mainboard connected over USB, on the same network as your machine. Its
  address: `robotont-<id>.local`, or the IP from the router's DHCP list (a `.local` name needs an
  `extra_hosts` entry in `server/compose.yaml` for the Semaphore container).
- The `peko` password (needed for sudo, `ROBOT_SUDO_PASSWORD` in `server/.env`).
- Optional: a laptop with ROS 2 Jazzy for topic checks (the robot itself works too over SSH), a
  gamepad already paired with the robot for drive tests.

Below, N is the robot number and `robotont-N` its inventory name.

## Part A: v1, reproduce the current setup

| Step | Where | Expected | If not |
|---|---|---|---|
| A1 Connectivity | `ssh peko@<address>` (your machine) | a shell on the robot | `Permission denied (publickey)`: run `ssh-copy-id peko@<address>` once, with the password (a Pi written with Imager already has the key) |
| A2 "1. Setup Ubuntu" | Semaphore: Robot address, Robot number N, Robot type, Camera | task green, last line `robotont-N enrolled at <address>. Next: 2. Deploy`; on the robot `hostname` is `robotont-N`, `ls -l /dev/robotont /dev/lidar` lists the symlinks, `nmcli connection show` lists `robotont-N-hotspot` and the lab Wi-Fi, `docker version` works as peko; `inventory/robots/robotont-N.yaml` exists; on a Lite robot `nmcli device status` shows `wlan0 ... connected` | sudo fails: `ROBOT_SUDO_PASSWORD` in `server/.env`; address does not resolve: `extra_hosts` in `server/compose.yaml`; Lite network handover: potential issues 1 to 3 below |
| A3 Status (legacy path only) | `ansible-playbook playbooks/status.yml -K` (your machine) | report per enrolled robot: `service`, `mainboard_present`, `hostname`, `workspace` commits. **Save this report: it is the state you are reproducing.** On a fresh robot there is no `robotont.service` yet, so the run ends red; expected before A4 | mainboard: see Troubleshooting |
| A4 "Setup ROS (legacy)", only for a robot that keeps ROS on the host | Semaphore: Robot number N; robot on **Ethernet** | 20 to 60 minutes: apt upgrade, ROS install, workspace wipe and full `colcon build`, hotspot `robotont-N`, then a reboot. The reboot task may show as failed or skipped; upstream sets `ignore_errors`. The task ends green or with that one warning | Troubleshooting; fix and re-run: it is a reinstall |
| A5 Status after | `ansible-playbook playbooks/status.yml -K`, then `ssh peko@robotont-N` | `ActiveState=active`, hostname `robotont-N`, `mainboard_present: true`; on the robot `source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=N; ros2 topic list` shows `/odom`, `/battery_state`, `/joint_states`, `/cmd_vel` (Lite: under `/rtN/`); `ros2 topic echo --once /battery_state` shows a voltage; the gamepad drives the robot; `nmcli connection show` lists the hotspot `robotont-N-hotspot` | `journalctl -u robotont -n 100` on the robot |
| A6 Repeat A4 (optional) | "Setup ROS (legacy)" again | green again; the workspace commits in A5 unchanged unless the GitHub branch heads moved | |

Milestone reached after A2: the host side of a robot is set up from Semaphore with four dialog fields. Steps A3 to A6 belong to the legacy host-ROS path and are optional; the normal path continues with Part B.

## Part B: workspaces on the same robot

Prerequisite: "1. Setup Ubuntu" green on this robot (Part A, steps A1 and A2). "Setup ROS
(legacy)" is not needed. The robot needs internet for B1 (Docker packages, image pull or build),
so Ethernet or the client Wi-Fi profile.

| Step | Command (where) | Expected | If not |
|---|---|---|---|
| B1 Deploy | Semaphore "2. Deploy": Robot number N (or `ansible-playbook playbooks/deploy.yml -K -e robotont_id=N`); 1 to 6 min with a pull, 15 to 40 min when the image is built on the robot | on the robot `robotont-status` prints `workspace: driver`, `service: active`, the `robotont-driver` container running from `ghcr.io/robotont/robotont-ros:<release>` (`2026.09`, Lite `2026.09-lite`); `docker image ls` shows that image; `systemctl cat robotont.service` shows the unit from `/etc/systemd/system`; `cat /var/lib/prometheus/node-exporter/robotont.prom` shows `robotont_workspace_info{workspace="driver",...} 1`; `status.yml` green with `container runtime, workspace driver` and `containers_running: 1/1` | pull `missing` in the task log: the image is not on GHCR yet (CI not run, package private) or no internet: the role then builds on the robot; `robotont.service` failed: `journalctl -u robotont -n 100` |
| B2 Hardware-free container | "3. Switch workspace": N, test-talker | `docker ps` shows `robotont-talker`; `source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=N; ros2 topic echo --once /chatter` on the robot prints `hello from robotont-N`; `status.yml` green with `containers_running: 1/1` | `sudo: a password is required`: `sudo visudo -cf /etc/sudoers.d/robotont-workspace` |
| B3 Dockerfile change | `ansible-playbook playbooks/deploy.yml -K -e robotont_id=N -e robotont_rebuild=true` | the image id changes; the active workspace is restarted on it | run the build by hand to see the error: `docker compose --env-file /etc/robotont/robotont.env -f /srv/robotont/images/compose.build.yaml build robotont-ros` |
| B4 Containerised bringup | "3. Switch workspace": N, driver | `docker ps` shows `robotont-driver`; `docker exec robotont-driver ls -l /dev/robotont /dev/lidar` lists them; `ros2 topic hz /rtN/scan` (Lite) shows 10 Hz; `ros2 topic hz /rtN/odom` a steady rate; `ros2 topic echo --once /rtN/battery_state` a voltage; gamepad drives the robot; `status.yml` green | `Permission denied` on the device: `ls -l /dev/robotont` must be mode 0666 (udev rule) and major 166; no odom: `docker logs robotont-driver`, then the mainboard (firmware, battery) |
| B5 Replug test | unplug the mainboard USB cable for 5 s, plug it back (robot) | odom resumes within about 10 s; `docker inspect -f '{{.RestartCount}}' robotont-driver` stays `0`; `grep device_present /var/lib/prometheus/node-exporter/robotont.prom` goes 0 then 1 | if the driver never recovers: note it; the documented fallback is `devices:` mapping plus a restart |
| B6 Survives a reboot | `sudo reboot` (robot) | after boot `robotont-status` shows workspace `driver`, container running, topics publishing | `systemctl status docker robotont`; `journalctl -b -u robotont` |
| B7 Release update | bump `robotont_release`, push, wait for the workflow, "2. Deploy" | the task log shows `updated: images of the active workspace`; the driver container runs the new image | `docker image ls`; the workflow run on GitHub |
| B8 Soak | leave the robot on `driver` for a week of normal use | `systemctl show robotont -p NRestarts` low, `docker inspect -f '{{.RestartCount}}' robotont-driver` low, no complaints from students | collect the journal and open an issue |

Write date, robot, image id (`docker image inspect -f '{{.Id}}' ghcr.io/robotont/robotont-ros:<release>`)
and results into the test log of docs/07.

## Potential issues to test (found on 2026-09-26, robotont-123, Ubuntu Server on a Pi 5)

1. **NetworkManager handover on a headless Server install.** First attempt: NetworkManager was
   already running when `netplan apply` switched the renderer, tried to take `wlan0` while the
   old netplan-managed wpa_supplicant still held it, failed five times and gave up (journal:
   "wpa_supplicant couldn't grab this interface ... giving up"). The Wi-Fi kept working only
   because the old networkd association stayed up. Fix in `roles/robotont_headless`: apply, stop the
   leftover `netplan-wpa-*` units (netplan apply leaves them running) and restart NetworkManager
   in one detached step, then assert that NetworkManager has a connected interface. **To re-test**: fresh Server card, run "1. Setup Ubuntu"; expected report shows
   `wlan0:wifi:connected` (and `eth0` when plugged), `.local` name resolves, SSH survives.
2. **Addresses change during the handover.** NetworkManager identifies itself to DHCP differently
   from systemd-networkd, so `eth0` came back with another lease and a `wait_for_connection` on
   the pinned address never returned. Always address robots by `robotont-N.local` (avahi is now
   part of the role) or by a DHCP reservation on the router; never pass `-e ansible_host=<ip>`
   for a first setup.
   **Second finding, 2026-09-27:** the old networkd addresses stay configured next to
   NetworkManager's until their lease expires (about ten minutes later) and avahi announces both;
   an SSH session that landed on an old one was cut in the middle of "2. Setup ROS" and the task
   reported the robot unreachable. The role now reboots right after the handover, so NetworkManager
   owns the interfaces from boot and only its addresses exist. Ansible also retries dropped
   connections (`retries = 5` in `ansible.cfg`) and uses IPv4 only (`-4`), because mDNS also hands
   the container an unusable IPv6 link-local address first.
   **Third finding, 2026-11-04 (Linux laptop, Docker Engine):** the Semaphore container cannot
   resolve `.local` there, so the address *has* to be an IP. On the bench the lease moved from
   `10.42.0.238` to `.239` during the handover and the run failed at the wait step. Expected and
   harmless: find the robot again (`getent hosts robotont-N.local` on the laptop, or the router),
   re-run "1. Setup Ubuntu" with the new address; the handover is not repeated and the enrolment
   file gets the new IP.
3. **Unplugging Ethernet during the run** aborts it at the wait step. If a run is aborted after
   the handover: reboot the robot (NetworkManager owns everything from the next boot), check
   `nmcli device status`, then re-run "1. Setup Ubuntu"; the role's file tasks report `ok` and
   the handover is not repeated.

4. **Missing `noble-updates` on the Imager-written Server image.** The Ubuntu Server 24.04 image
   from Raspberry Pi Imager had only the release and security suites in `ubuntu.sources`, so
   `ros-jazzy-desktop` failed with "held broken packages" (its `-dev` dependencies could not be
   resolved against the already updated runtime libraries). `roles/robotont_headless` now adds the
   updates suite when it is missing. **To re-test**: on a fresh card check
   `grep -r updates /etc/apt/sources.list.d/` before and after "1. Setup Ubuntu".

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

7. **avahi is only installed when the first boot has internet.** Raspberry Pi Imager puts
   `packages: [avahi-daemon]` into the Ubuntu Server cloud-init, but cloud-init runs that step once
   per instance and never retries. A card first booted without a network (seen 2026-10-12: "Temporary
   failure resolving archive.ubuntu.com") never answers `robotont-N.local` until "1. Setup Ubuntu"
   installs avahi over the IP. **To avoid**: first boot on a cable with DHCP and internet, or with
   the Wi-Fi set in Imager in range; `robotont-N.local` then answers within a minute of the first
   boot (verified 2026-11-04 on a fresh 24.04.5 card behind a laptop's shared Ethernet).
8. **dpkg lock held by unattended-upgrades on a fresh card.** For about ten minutes after the first
   boots Ubuntu Server runs `unattended-upgrade`; the Docker install in "1. Setup Ubuntu" failed
   with "Unable to acquire the dpkg frontend lock" after the apt module's default 60 s. Every apt
   task in `roles/docker` and `roles/robotont_headless` now waits up to 600 s (`lock_timeout`).
   **To re-test**: fresh card, "1. Setup Ubuntu" right after the first boot; the Docker step waits
   and then succeeds.
9. **Semaphore container on a Linux laptop with a shared Ethernet connection.** NetworkManager's
   `shared` mode rejects forwarded traffic to the cable from any other subnet, above Docker's own
   rules, so the Semaphore task fails at "Log in over SSH" with "Connection refused" while
   `ssh` from the laptop works. One firewall rule for the session fixes it; see "Linux host" in
   [semaphore-setup.md](semaphore-setup.md). Not an issue on a lab network or a server.

## Troubleshooting

| Symptom | Where to look | Usual cause |
|---|---|---|
| `status.yml`: "A submodule under external/ is empty" | your machine or Semaphore's checkout | `git submodule update --init` |
| `Permission denied (publickey)` | `ssh -v peko@<ip>` | the public key is not in `~peko/.ssh/authorized_keys`: `ssh-copy-id` |
| sudo check fails | Semaphore inventory sudo credential, or `-K` | wrong or missing peko password |
| `status.yml`: `mainboard_present: false` | `lsusb | grep 0483:5740`, `ls -l /dev/ttyACM* /dev/robotont`, `cat /etc/udev/rules.d/99-robotont.rules`, `sudo udevadm trigger` | USB cable, mainboard power, missing udev rule |
| Service active but no `/odom` | `journalctl -u robotont -n 100` | wrong `ROS_DOMAIN_ID` in your shell (must equal the robot number); driver on `/dev/ttyACM0` while the board enumerated as `ttyACM1` |
| "2. Setup ROS" seems stuck at the end | Semaphore task log | the reboot: wait 3 minutes, then `status.yml` |
| `permission denied ... docker.sock` right after "1. Setup Ubuntu" | your shell on the robot | the login predates the docker group: log out and in again (the playbook resets its own connection) |
| Session lost during "2. Setup ROS" | Wi-Fi | `netplan apply` switched to hotspot mode; use Ethernet |
| compose prints "variable is not set" | `cat /etc/robotont/robotont.env` | env file incomplete or unreadable by peko (must be group `peko`, mode 0640) |
| `robotont-workspace switch`: "sudo: a password is required" | `sudo visudo -cf /etc/sudoers.d/robotont-workspace` | sudoers file missing or the systemctl path differs |
| Container cannot open `/dev/robotont` | `ls -l /dev/robotont /dev/ttyACM0` on the host | mode not 0666, or major not 166 (then extend `device_cgroup_rules`) |
| Laptop does not see the topics of a container | `docker inspect -f '{{.HostConfig.NetworkMode}}' robotont-driver` (must be `host`), `ufw status` (inactive), same `ROS_DOMAIN_ID` | workspace service not extending `ros-app`, firewall re-enabled |
| `ros:jazzy-ros-base` cannot be pulled | robot's internet | robot in hotspot mode without uplink: connect Ethernet |
| After the handover `nmcli device status` shows `wlan0 unavailable` | `journalctl -u NetworkManager` ("couldn't grab this interface") | old wpa_supplicant still held the interface; `sudo systemctl restart NetworkManager` or reboot |
| Semaphore: `Log in over SSH` fails with `Connection refused`, `ssh` from the same machine works | `docker exec robotont-semaphore nc -z <ip> 22` | Linux laptop with a shared Ethernet connection: the firewall rule in semaphore-setup.md (issue 9) |
| `Unable to acquire the dpkg frontend lock` in the Docker step | `ps -e \| grep unattended` on the robot | fresh card still running `unattended-upgrade`; the roles wait 600 s, otherwise re-run later (issue 8) |
| `robotont-N.local` never resolved since the first boot | `dpkg -l avahi-daemon` on the robot; `grep avahi /var/log/cloud-init-output.log` | first boot without internet (issue 7): run "1. Setup Ubuntu" with the IP |
| `robotont-N.local` stops resolving after the handover | `systemctl is-active avahi-daemon` on the robot | avahi missing on Server (the role installs it) or restarting; use the IP from the router meanwhile |
| Image build fails on rosdep | build by hand and read the missing key | add it to `ROSDEP_SKIP_KEYS` or to the apt list in the Dockerfile |
| `Install ROS (jazzy-desktop)` fails with "held broken packages" | `apt-cache policy libdbus-1-dev libdbus-1-3` on the robot; `cat /etc/apt/sources.list.d/ubuntu.sources` | the updates suite is missing (Imager Server image); the headless role adds it, or add `noble-updates` by hand and `apt update` |

## What to report upstream after the tests

- Whether the containerised bringup opens `/dev/robotont` or only `/dev/ttyACM0` (docs/05 §4 item 7).
- Replug behaviour with the `/dev` bind mount (B5).
- Gamepad hot-plug inside the container (B4), and whether `SDL_JOYSTICK_DISABLE_UDEV=1` was needed.
- Anything the `jazzy-devel` bringup does that the `jazzy` one changed, before moving the release pins.
