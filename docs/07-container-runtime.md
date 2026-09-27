# 07. Container runtime (Docker on the robots)

## Why

The Robotont supervisor wants a dockerized *selection* of what runs on a robot: the plain driver,
demo presets for presentations, and a student workspace, switchable without reinstalling anything.
Students (ROS beginners) need a hands-on Linux and ROS environment over SSH or VS Code. Several
containers may hold several pieces of hardware, and monitoring must show which. The firmware's OLED
menu for selecting containers (branch `v3.0-devel-jyrgen`, not merged) proves the intent; the
switch itself is done from Semaphore.

This layer sits on top of v1 ([06](06-v1-reproduce-current-setup.md)) and keeps its contract: the
unit is still `robotont.service`, the user is still `peko`, the mainboard is still `/dev/robotont`,
and the health check still works. Host-installed ROS becomes one preset (`host`) among others.

Decisions taken with the user on 2026-09-23: NUC robots first; students enter through sshd in the
student container on port 2222; the study-room default is `student` (a separate driver container
keeps the hardware); images are built on each robot until a registry exists; this iteration ships
the design plus the D1 files, verified statically.

## How it works

```
/etc/robotont/preset  ──►  robotont.service  ──►  robotont-preset run
   (one word, e.g.               (systemd,             │
    driver)                       User=peko)           ├─ compose.yaml: docker compose -p robotont up   (foreground)
                                                       └─ run.sh:       host bringup (preset "host")
/etc/robotont/robotont.env ─── identity and options (Ansible-managed), read by both
/opt/robotont/presets/<name>/  ─── deployed from robot/presets in this repository
```

- **One preset at a time.** The compose project name is always `robotont`, so `up --remove-orphans`
  removes the previous preset's containers, and fixed container names (`robotont-driver`) make two
  drivers impossible. A preset may contain several containers.
- **Switching** is `robotont-preset switch <name>`: validate, write the word, restart the unit.
  Semaphore runs it through `playbooks/switch_preset.yml` (task "4. Switch preset": Robot number, Preset).
  Deploys never reset the preset; it is operational state, written only on the first deploy
  (`robotont_default_preset: host`).
- **Restarts.** Containers use `restart: unless-stopped`, so a crashing driver is back in seconds
  and other containers (student shells) are untouched. systemd restarts the compose process itself.
  `journalctl -u robotont -f` shows every container's output; the daemon logs to journald too.
- **Devices.** Hardware containers bind-mount `/dev` read-only and get narrow `device_cgroup_rules`
  (ttyACM, ttyUSB, input, USB bus, video4linux). The host udev symlinks are therefore visible and a
  replugged mainboard is picked up without a container restart. No `privileged`.
- **Networking.** `network_mode: host` on every ROS container: DDS discovery with laptops works as
  before, and `ROS_DOMAIN_ID` comes from the env file. Transport is UDP only
  (`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` in every container): Fast DDS shared memory does not work
  between the containers' root and the host's peko even with `ipc: host` (discovery succeeds, data
  never arrives; found on robotont-123, test log). `ipc: host` stays for anything else that needs
  `/dev/shm`.
- **Device declarations.** Each service labels the hardware it opens (`robotont.devices`, vocabulary
  `mainboard lidar gamepad realsense camera`). `robotont-preset check` refuses two claims on an
  exclusive device; `robotont-metrics` turns claims into metrics.

## Files

| Repository path | On the robot | Purpose |
|---|---|---|
| `robot/presets/_common/services.yaml` | `/opt/robotont/presets/_common/` | shared service definitions (`ros-app`, `hardware`, `driver`, `student`, `student-hw`) |
| `robot/presets/<name>/compose.yaml` or `run.sh` | `/opt/robotont/presets/<name>/` | one preset each; see [robot/presets/README.md](../robot/presets/README.md) |
| `robot/images/compose.build.yaml`, `robotont-ros/Dockerfile` | `/opt/robotont/images/` | image builds (native, on the robot) |
| `robot/releases/<release>.repos` | `/opt/robotont/releases/` | pinned sources the image is built from |
| `robot/bin/robotont-preset`, `robotont-metrics`, `robotont-status` | `/usr/local/bin/` | switch and run, metrics and status |
| `roles/docker` | | Docker Engine and Compose plugin from Docker's apt repository, `daemon.json` (journald logging, live-restore, metrics on 127.0.0.1:9323), `peko` in group `docker` |
| `roles/robotont_presets` | `/etc/robotont/`, `/etc/systemd/system/robotont.service`, `/etc/sudoers.d/robotont-preset`, metrics timer | the runtime itself |
| `playbooks/setup_docker.yml` | | Semaphore "3. Setup Docker": Docker, presets, unit, then the image build when it is missing |
| `playbooks/switch_preset.yml` | | Semaphore "4. Switch preset" (Robot number, Preset) |
| `playbooks/status.yml` | | read-only report, preset-aware: containers, declared devices |

## Images

| Image | From | Content |
|---|---|---|
| `ghcr.io/robotont/robotont-ros:<release>` | `ros:jazzy-ros-base` | `vcs import` of the release, `rosdep install` (skipping `rviz2`, `camera_ros`), `ros-jazzy-realsense2-camera`, `depthimage-to-laserscan`, `joy`, `teleop-twist-joy`, `demo-nodes-cpp`; `colcon build --merge-install` into `/opt/robotont/install`; entrypoint sources both overlays |
| `ghcr.io/robotont/robotont-student:<release>` | `robotont-ros` | Phase D3, see [robot/images/robotont-student/README.md](../robot/images/robotont-student/README.md) |

The tag is the release name (`robotont_release` in `group_vars`, `ROBOTONT_RELEASE` in the env
file). Images are named as they will be on GHCR, so presets do not change when the registry
arrives (Phase D4, GitHub Actions on `ubuntu-24.04` and `ubuntu-24.04-arm` runners, then
`pull_images.yml`). Until then `setup_docker.yml` builds on each robot; the same tag can differ
slightly between robots built on different days, and the health check shows the image id.

Lite robots use `2026.09-lite.repos`, read back from the first provisioned Pi with `vcs export --exact`
(the `jazzy` heads of the Lite package list). The NUC release (`2026.09`) pins exactly what the NUC robots run today: the `jazzy-devel` heads
from the robotont-setup package list. Container behaviour therefore equals host behaviour,
including the known bringup quirks (the driver opens the code default `/dev/ttyACM0`; the
RealSense path is on by default). Moving to the `jazzy` heads waits for the upstream fixes listed
in [05](05-implementation-plan.md) section 4.

## Runbook

**Deploy** (first time on an adopted robot, no behaviour change; the image build needs network
on the robot and 15 to 30 minutes):

```
ansible-playbook playbooks/setup_docker.yml -K -e robotont_id=1
robotont-status            # on the robot: preset host, service active, containers none
```

**Switch** to the container bringup, and back:

```
ansible-playbook playbooks/switch_preset.yml -K -e robotont_id=1 -e preset=driver
ansible-playbook playbooks/status.yml -K
ansible-playbook playbooks/switch_preset.yml -K -e robotont_id=1 -e preset=host     # rollback
```

On the robot itself (as peko): `robotont-preset switch driver`, `robotont-preset status`,
`journalctl -u robotont -f`.

**Add a demo**: copy `robot/presets/demo-example` to `robot/presets/demo-<name>`, edit the extra
services (same image, another `command:`, or a `demo-<name>` image added to
`compose.build.yaml`), declare `robotont.devices`, write a `README.md`, run `setup_docker.yml`,
then switch. Validate locally first:

```
docker compose -p robotont --env-file test/robotont.env -f robot/presets/demo-<name>/compose.yaml config
ROBOTONT_ROOT=robot ROBOTONT_ENV_FILE=test/robotont.env robot/bin/robotont-preset check demo-<name>
```

**Change the release**: add `robot/releases/<new>.repos` (pinned SHAs, `vcs export --exact` from a
known-good workspace), set `robotont_release` in `group_vars`, deploy, build, switch (a switch
recreates containers whose image changed).

## Semaphore tasks

"3. Setup Docker" (Robot number) deploys the runtime and builds the image; "4. Switch preset"
(Robot number, Preset) activates a preset. Both run on exactly one robot; there is no fleet-wide
switch. `-e rebuild=true` on the command line forces the image build for an unchanged tag.

## Monitoring hooks

`robotont-metrics.timer` (15 s) writes `/var/lib/prometheus/node-exporter/robotont.prom`
(picked up by node_exporter in Milestone 3) and `/run/robotont/status.json` (shown by
`robotont-status`, also inside containers):

```
robotont_preset_info{preset,release} 1
robotont_info{release,firmware} 1
robotont_service_active 0|1
robotont_docker_available 0|1
robotont_container_state{preset,service,state} 1
robotont_container_up{preset,service,image} 0|1
robotont_container_restarts_total{preset,service}
robotont_container_device{preset,service,device} 1
robotont_device_present{device} 0|1
robotont_device_conflict{device} 0|1
```

Grafana can show per robot which preset runs and which devices are claimed or missing; alerts
later in PromQL (claimed but absent, exclusive device claimed twice, restart loops).

## Student environment (Phase D3, designed)

- Preset `student` = the driver container plus `robotont-student` with sshd on port 2222;
  `ssh -p 2222 peko@robotont-N` lands in the ROS environment with the workspace. VS Code users add
  one Remote-SSH entry. Host port 22 stays for operators; `robotont-shell` (docker exec) is the fallback.
- The whole container home is a bind mount of `/home/peko/student`, so the workspace, shell history
  and the VS Code server survive preset switches and image updates. `apt` installs inside the
  container do not; anything a course needs goes into the image.
- Preset `student-hw` gives the student container the hardware instead of running the driver:
  students start the driver themselves. Exactly one of the two runs at a time.
- Limits (`cpus`, `mem_limit`, `pids_limit`, colcon parallel workers) keep a student build from
  starving the driver.

## What must be verified on hardware

- Opening `/dev/robotont` read-write from inside a container with the read-only `/dev` mount.
- Mainboard replug: the driver in the container reconnects without a restart.
- Gamepad hot-plug in the container (`joy` uses SDL2; `SDL_JOYSTICK_DISABLE_UDEV=1` may be needed).
- RealSense through `/dev/bus/usb` and video4linux cgroup rules.
- DDS discovery from a laptop with the containerised bringup.
- The adoption round trip `host` -> `driver` -> `host` on a robot provisioned by robotont-setup.

## Phases

- **D0**: pin the release file (needs one GitHub lookup for `demo_teleop` and `laserscan_to_ranges`).
- **D1** (this iteration, files done): roles, presets `host`, `driver`, `test-talker`, `demo-example`,
  playbooks, health check. Then on one robot: deploy with `host`, build, switch to `driver`, drive it,
  replug test, a week of soak, rollback path confirmed.
- **D2**: real `demo-*` presets in daily use.
- **D3**: student image and presets, `robotont-shell`, motd, `reset_student_env.yml`, student guide.
- **D4**: GHCR workflow and `pull_images.yml`.
- **D5** (optional): OLED bridge daemon after the firmware merge, or a second USB CDC interface in
  the firmware for the menu channel (cleaner; raise with Veiko).
- **D6**: new robots provisioned Docker-only; existing robots keep host ROS until reinstall.

## Test log

Procedure: [08-hardware-test-guide.md](08-hardware-test-guide.md), Part B.

| Date | Where | What | Result |
|---|---|---|---|
| 2026-09-23 | Mac | compose config of every preset, `robotont-preset check`, `robotont-metrics --print`, Ansible syntax checks | see the verification notes in the commit |
| 2026-09-27 | robotont-123 (Pi 5, Lite, no mainboard) | B1 `setup_docker.yml -e robotont_id=123` from the Mac | Docker 29 installed, `/opt/robotont` deployed, unit swapped, preset `host`, metrics timer running. Three defects found and fixed in the same session: (1) `presets/host/run.sh` used `set -u` and `/opt/ros/jazzy/setup.bash` references an unset variable, so the service restart-looped until the script was fixed (now `set -eo pipefail`); after the fix the host bringup runs through the new unit with the inventory's arguments (`camera:=false`); (2) the image build in the same run got "permission denied" on the Docker socket because the SSH session predated peko's docker group: the docker role now resets the connection and the build runs as the login user; (3) `robotont-metrics` reported `camera=yes` from `/dev/media*`, which the Pi's codec and ISP expose without a camera; detection now uses the CSI video nodes. Image build re-run: see next row |
| 2026-09-27 | robotont-123 | B1 re-run after the fixes | **green**: `ghcr.io/robotont/robotont-ros:2026.09-lite` built on the Pi in 14 min (rosdep and colcon of the Lite release); a further re-run is idempotent (`already present`, only the presets copy changes) |
| 2026-09-27 | robotont-123 | B2 "Switch preset" test-talker from Semaphore | container up in 10 s, `/chatter` discovered on the host, but **no data arrived**: Fast DDS shared memory between root (container) and peko (host) does not work even with `ipc: host` (inside the container the echo works; a UDP-only host subscriber receives). Fix: `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` in every container. After redeploy and re-switch a plain `ros2 topic echo --once /chatter` on the host prints the message; `status.yml` green with `containers_running: 1/1`; metrics `robotont_container_state{service="talker",state="running"} 1` |
| 2026-09-27 | robotont-123 (no mainboard, no lidar) | B4 "Switch preset" driver | `robotont-driver` running from the built image: driver, teleop, laserscan_to_ranges and robot_state_publisher up, 17 `/rt123/...` topics on the host; the driver retries `/dev/ttyACM0` once per second and the rplidar node dies (no `/dev/lidar`), as on the host; metrics show the three claimed devices absent. Odometry and driving wait for the mainboard |
| 2026-09-27 | robotont-123 | B6 reboot, B7 rollback | after the reboot preset `driver` persisted, container up 24 s after login, `NRestarts=0`, 14 topics; "Switch preset" host from Semaphore: no containers, host bringup through `run.sh` running, 15 topics |
| 2026-09-27 | robotont-123, **fresh card**, mainboard and lidar fitted, user-driven from the Semaphore UI | "3. Setup Docker" (task 33) | first attempt red in the build step: the ISP path to `packages.ros.org` and `auth.docker.io` was down from the robot for a while (TCP timeouts from both interfaces, LAN clean); the runtime part had completed (new unit, preset host, camera respawn gone). Build step now retries three times. Second run **green** in 19 min including the image build |
| 2026-09-27 | robotont-123, fresh card | "4. Switch preset" driver (task 34) | **green**: `robotont-driver` from `robotont-ros:2026.09-lite` (4.5 GB), `/dev/robotont` and `/dev/lidar` visible inside, RPLidar identified, driver opens the mainboard; `status.yml` green with `containers_running: 1/1`; metrics show both devices present and the container running with 0 restarts; a `/rt123/scan` message reaches a host subscriber |
