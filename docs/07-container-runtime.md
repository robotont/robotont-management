# 07. Workspaces (Docker on the robots)

## Why

What runs on a robot is a *workspace*: the plain driver, a demo for a presentation
(`university-celebration-day-demo-2026`), a development setup (`leonid-development-camera`), a
student environment. Workspaces are switched from Semaphore without reinstalling anything, and a
robot needs no ROS on the host: everything ROS lives in images that CI builds and the robots
pull. Several containers may hold several pieces of hardware, and monitoring shows which. The
firmware's OLED menu for selecting containers (branch `v3.0-devel-jyrgen`, not merged) proves the
intent; the switch itself is done from Semaphore.

Decisions taken with the user: 2026-09-23 students enter through sshd in the student container
on port 2222, the study-room default is `student`; 2026-09-27 the term is *workspace*, robots are
Docker-only (the upstream host-ROS setup stays as "Setup ROS (legacy)"), the docker files live
under `/srv/robotont`, images are built by GitHub Actions and pulled from GHCR (public).

## How it works

```
/etc/robotont/workspace  ──►  robotont.service  ──►  robotont-workspace run
   (one word, e.g.                (systemd,               │
    driver)                        User=peko)             ├─ compose.yaml: docker compose -p robotont up   (foreground)
                                                          └─ run.sh:       host bringup (workspace "host", legacy)
/etc/robotont/robotont.env ─── identity and options (Ansible-managed), read by both
/srv/robotont/workspaces/<name>/ ─── deployed from robot/workspaces in this repository
/srv/robotont/images/, releases/ ─── the Dockerfiles and pinned releases (fallback build only)
```

- **One workspace at a time.** The compose project name is always `robotont`, so `up
  --remove-orphans` removes the previous workspace's containers, and fixed container names
  (`robotont-driver`) make two drivers impossible. A workspace may contain several containers.
- **Switching** is `robotont-workspace switch <name>`: validate, write the word, restart the unit.
  Semaphore runs it through `playbooks/switch_workspace.yml` (task "3. Switch workspace": Robot
  number, Workspace; the dropdown lists the directories under `robot/workspaces`). Deploys never
  reset the selection; it is operational state, written only on the first deploy
  (`robotont_default_workspace: driver`).
- **Deploying** is `playbooks/deploy.yml` (task "2. Deploy"): copy `robot/` to `/srv/robotont`,
  write the env file, `robotont-workspace pull` (every image every workspace references), then
  the unit. When an image of the active workspace changed, the unit is restarted and compose
  recreates that container. Without registry access the `robotont-ros` image is built on the
  robot as a fallback (15 to 40 minutes).
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
  `mainboard lidar gamepad realsense camera`). `robotont-workspace check` refuses two claims on an
  exclusive device; `robotont-metrics` turns claims into metrics.

## Files

| Repository path | On the robot | Purpose |
|---|---|---|
| `robot/workspaces/_common/services.yaml` | `/srv/robotont/workspaces/_common/` | shared service definitions (`ros-app`, `hardware`, `driver`, `student`, `student-hw`) |
| `robot/workspaces/<name>/compose.yaml` or `run.sh` | `/srv/robotont/workspaces/<name>/` | one workspace each; see [robot/workspaces/README.md](../robot/workspaces/README.md) |
| `robot/images/compose.build.yaml`, `robotont-ros/Dockerfile` | `/srv/robotont/images/` | image definitions: built by CI, on the robot only as fallback |
| `robot/releases/<release>.repos` | `/srv/robotont/releases/` | pinned sources the image is built from |
| `robot/bin/robotont-workspace`, `robotont-metrics`, `robotont-status` | `/usr/local/bin/` | switch, run and pull; metrics and status |
| `.github/workflows/images.yml` | | builds `robotont-ros` per release on native runners and pushes to GHCR |
| `roles/robotont_host` | hostname, `/etc/udev/rules.d/99-robotont.rules`, groups, NetworkManager profiles | what robotont-setup did on the host besides ROS; part of "1. Setup Ubuntu" |
| `roles/docker` | | Docker Engine and Compose plugin from Docker's apt repository, `daemon.json` (journald logging, live-restore, metrics on 127.0.0.1:9323), `peko` in group `docker`; part of "1. Setup Ubuntu" |
| `roles/robotont_workspaces` | `/srv/robotont`, `/etc/robotont/`, `/etc/systemd/system/robotont.service`, `/etc/sudoers.d/robotont-workspace`, metrics timer | the runtime itself, including the image pull |
| `playbooks/deploy.yml` | | Semaphore "2. Deploy" (Robot number) |
| `playbooks/switch_workspace.yml` | | Semaphore "3. Switch workspace" (Robot number, Workspace) |
| `playbooks/status.yml` | | read-only report: active workspace, containers, declared devices |

## Images

| Image | From | Content |
|---|---|---|
| `ghcr.io/robotont/robotont-ros:<release>` | `ros:jazzy-ros-base` | two layers: the apt dependencies rosdep resolves for the release (skipping `rviz2`, `camera_ros`) plus `ros-jazzy-realsense2-camera`, `depthimage-to-laserscan`, `joy`, `teleop-twist-joy`, `demo-nodes-cpp`; then the release sources and `colcon build --merge-install` into `/opt/robotont/install`; entrypoint sources both overlays |
| `ghcr.io/robotont/robotont-student:<release>` | `robotont-ros` | Phase D3, see [robot/images/robotont-student/README.md](../robot/images/robotont-student/README.md) |

The tag is the release name (`robotont_release` in `group_vars`, `ROBOTONT_RELEASE` in the env
file): `2026.09` for NUC robots (amd64), `2026.09-lite` for Lite robots (arm64). The workflow
builds each on a native runner (`ubuntu-24.04`, `ubuntu-24.04-arm`) on every push to `main` that
touches `robot/images/` or `robot/releases/`, with a registry build cache
(`robotont-ros:cache-<release>`). The dependency layer is derived from a package list the first
build stage writes with `rosdep --simulate`, so it is cached across releases while the
dependencies are unchanged; a release bump pushes and pulls only the small last layer.

Lite robots use `2026.09-lite.repos`, read back from the first provisioned Pi with `vcs export --exact`
(the `jazzy` heads of the Lite package list). The NUC release (`2026.09`) pins the `jazzy-devel`
heads from the robotont-setup package list, so container behaviour equals what the NUC robots ran
on the host, including the known bringup quirks (the driver opens the code default
`/dev/ttyACM0`; the RealSense path is on by default). Moving to the `jazzy` heads waits for the
upstream fixes listed in [05](05-implementation-plan.md) section 4.

A robot without registry access builds the image itself from the same files (`robotont-workspace`
reports `missing`, the role builds). Such an image differs from the CI one only in build date.

## Runbook

**New robot**: "1. Setup Ubuntu" (address, number, type, camera), then "2. Deploy" (number). The
robot comes up in the `driver` workspace. Command line:

```
ansible-playbook playbooks/setup_ubuntu.yml -K -e robot_address=robotont-123.local -e robotont_id=123 -e robot_type=3lite -e robotont_camera=false
ansible-playbook playbooks/deploy.yml -K -e robotont_id=123
```

**Switch** workspaces, and back:

```
ansible-playbook playbooks/switch_workspace.yml -K -e robotont_id=123 -e workspace=test-talker
ansible-playbook playbooks/status.yml -K
ansible-playbook playbooks/switch_workspace.yml -K -e robotont_id=123 -e workspace=driver
```

On the robot itself (as peko): `robotont-workspace switch driver`, `robotont-workspace status`,
`journalctl -u robotont -f`.

**Add a workspace**: copy `robot/workspaces/demo-example` to `robot/workspaces/<name>` (`[a-z0-9-]`,
up to 63 characters), edit the services (same image with another `command:`, or a new image added
to `compose.build.yaml` and the workflow), declare `robotont.devices`, write a `README.md`.
Validate locally, commit, run "2. Deploy" on the robot, then switch. `docker compose -f
server/compose.yaml up -d` refreshes the Workspace dropdown in Semaphore.

```
docker compose -p robotont --env-file test/robotont.env -f robot/workspaces/<name>/compose.yaml config
ROBOTONT_ROOT=robot ROBOTONT_ENV_FILE=test/robotont.env robot/bin/robotont-workspace check <name>
```

**Run any image** without touching the repository: "4. Run image" (Robot number, Image, Name,
Command, Hardware access) generates `/srv/robotont/workspaces/<name>/compose.yaml` on the robot
from `roles/robotont_workspaces/templates/image-workspace.compose.yaml.j2` (one service that
extends `ros-app` or `hardware`), pulls the image as peko and activates it. Deploy leaves such
directories alone and keeps pulling their images. Good for demos, a quick exporter, a test
build from a personal registry. Anything with volumes, several services or devices beyond the
shared definitions is a repository workspace.

```
ansible-playbook playbooks/run_image.yml -K -e robotont_id=123 -e image=traefik/whoami:v1.11.0
ansible-playbook playbooks/run_image.yml -K -e robotont_id=123 -e image=ghcr.io/robotont/robotont-ros:2026.09-lite \
  -e workspace=talker-image -e hardware=yes -e command='ros2 run demo_nodes_cpp talker'
```

**Change the release**: add `robot/releases/<new>.repos` (pinned SHAs, `vcs export --exact` from a
known-good workspace), add the release to the workflow matrix, set `robotont_release` in
`group_vars`, push (CI builds), then "2. Deploy" on each robot: the pull brings the new layer and
the active workspace is restarted on it.

**Adopted robots** (ROS installed on the host by the legacy setup): "1. Setup Ubuntu" and
"2. Deploy" work unchanged; the first deploy selects `driver`, and `host` remains available as a
workspace for as long as the host ROS is there.

## Semaphore tasks

"2. Deploy" (Robot number), "3. Switch workspace" (Robot number, Workspace) and "4. Run image"
(Robot number, Image, Name, Command, Hardware access). All run on exactly one robot; there is no
fleet-wide switch. Command-line only: `-e robotont_rebuild=true`
forces a build on the robot (to test a Dockerfile change before pushing), `-e
robotont_pull_images=false` skips the pull on a robot without internet.

## Monitoring hooks

`robotont-metrics.timer` (15 s) writes `/var/lib/prometheus/node-exporter/robotont.prom`
(picked up by node_exporter in Milestone 3) and `/run/robotont/status.json` (shown by
`robotont-status`, also inside containers):

```
robotont_workspace_info{workspace,release} 1
robotont_info{release,firmware} 1
robotont_service_active 0|1
robotont_docker_available 0|1
robotont_container_state{workspace,service,state} 1
robotont_container_up{workspace,service,image} 0|1
robotont_container_restarts_total{workspace,service}
robotont_container_device{workspace,service,device} 1
robotont_device_present{device} 0|1
robotont_device_conflict{device} 0|1
```

Grafana can show per robot which workspace runs and which devices are claimed or missing; alerts
later in PromQL (claimed but absent, exclusive device claimed twice, restart loops).

## Student environment (Phase D3, designed)

- Workspace `student` = the driver container plus `robotont-student` with sshd on port 2222;
  `ssh -p 2222 peko@robotont-N` lands in the ROS environment with the workspace. VS Code users add
  one Remote-SSH entry. Host port 22 stays for operators; `robotont-shell` (docker exec) is the fallback.
- The whole container home is a bind mount of `/home/peko/student`, so the work, shell history
  and the VS Code server survive workspace switches and image updates. `apt` installs inside the
  container do not; anything a course needs goes into the image.
- Workspace `student-hw` gives the student container the hardware instead of running the driver:
  students start the driver themselves. Exactly one of the two runs at a time.
- Limits (`cpus`, `mem_limit`, `pids_limit`, colcon parallel workers) keep a student build from
  starving the driver.

## What must be verified on hardware

- Mainboard replug: the driver in the container reconnects without a restart.
- Odometry and driving from the container (the board on robotont-123 sent no odometry on 2026-09-27).
- Gamepad hot-plug in the container (`joy` uses SDL2; `SDL_JOYSTICK_DISABLE_UDEV=1` may be needed).
- RealSense through `/dev/bus/usb` and video4linux cgroup rules (NUC robots).
- DDS discovery from a laptop with the containerised bringup.
- The whole path on a NUC robot: `roles/robotont_host` writes NetworkManager profiles there too,
  next to the netplan-rendered ones a legacy setup left; untested.

## Phases

- **D1** done 2026-09-27: runtime, `driver`, `test-talker`, `demo-example`, deploy and switch, verified on a Lite robot.
- **D2**: real demo workspaces in daily use.
- **D3**: student image and workspaces, `robotont-shell`, motd, `reset_student_env.yml`, student guide.
- **D4** files done 2026-09-27: GHCR workflow, pull-based deploy; first CI run pending a push.
- **D5** (optional): OLED bridge daemon after the firmware merge, or a second USB CDC interface in
  the firmware for the menu channel (cleaner; raise with Veiko).
- **D6** done 2026-09-27: robots are Docker-only ("1. Setup Ubuntu" covers the host side); the
  upstream host-ROS setup remains as "Setup ROS (legacy)".

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
| 2026-09-27 | robotont-123 (lidar fitted, mainboard unplugged after the user's reboot) | Restructure to workspaces under `/srv/robotont`, pull-based "2. Deploy", two-layer Dockerfile, CI workflow (files only), "1. Setup Ubuntu" with the new host role | **green** through Semaphore: 1. Setup Ubuntu (host role idempotent on a robot set up by the legacy path: only the profile files and `/etc/hosts` rewritten once; Docker already present); 2. Deploy migrated `/etc/robotont/preset` to `workspace`, removed `/opt/robotont`, pull from GHCR denied as expected (no CI push yet) and the local image used; forced rebuild with the two-layer Dockerfile 12 min on the Pi: image 3.9 GB (was 4.5), release in two layers of 140 MB (sources) and 95 MB (install), dependency list of 14 packages from `rosdep --simulate`; 3. Switch workspace driver runs the driver on the rebuilt image; second Deploy changes nothing but the files edited in between; `status.yml` green with `workspace driver`, 1/1 containers. Defect found: an unquoted YAML condition in the host role (fixed) |
| 2026-11-04 | robotont-123, **fresh 24.04.5 card** (Imager: hostname, user, avahi via cloud-init), no mainboard, no lidar, cable straight into an Ubuntu 24.04 laptop (shared Ethernet, Docker Engine 29, Semaphore from `server/compose.yaml`) | "1. Setup Ubuntu" from Semaphore with the IP (tasks 1 to 4) | 1: red before SSH, the container could not reach the shared interface (docs/08 issue 9); 2: red at `Wait for the host to come back`, the lease moved `.238` to `.239` in the handover (issue 2); 3: red at the Docker install, dpkg lock held by `unattended-upgrade` (issue 8, `lock_timeout: 600` added); 4: **green**, `ok=30 changed=5`, Docker 29.9.3 and Compose 5.7.0, peko in `docker`, enrolment written from the container with `ansible_host: 10.42.0.239` |
| 2026-11-04 | robotont-123 | GHCR pull with a read-only PAT (`docker login ghcr.io` as peko, done by the user), then "2. Deploy" with `robotont_build_fallback=false` (task 5) | pull `ghcr.io/robotont/robotont-ros:2026.09-lite` 3.88 GB, id `e32b3baad4c0`, in a few minutes over the laptop's uplink; Deploy **green** `ok=26 changed=14`: `/srv/robotont`, `robotont.env`, workspace `driver`, unit and metrics timer; `robotont-driver` running, driver node and rplidar retry on the missing devices as expected, `robotont.prom` written (`device_present{mainboard} 0`) |
| 2026-11-04 | robotont-123 | B2 "3. Switch workspace" test-talker (task 6) | **green**: `robotont-talker` up in 24 s, `ros2 topic echo --once /chatter` inside the container prints `hello from robotont-123` |
| 2026-11-04 | robotont-123 (no mainboard, no lidar) | B4 "3. Switch workspace" driver (task 7), B6 reboot (`sudo reboot` by the user) | B4 **green**: `robotont-driver` back in 34 s, `NRestarts=0`; B6 **green**: boot 18:15:20 UTC, `robotont.service` active at 18:15:41, driver container up, same lease `10.42.0.239`, `systemd-networkd` inactive (NetworkManager alone), `robotont-123.local` resolves from the laptop, `robotont_container_up ... 1`. Not tested today (no hardware): B3, B5, B7, B8, odometry, lidar |
| 2026-11-04 | bench network `10.42.0.0/24` (laptop `10.42.0.1`, robotont-123) | new task "0. Find robots" (`playbooks/find_robots.yml`), from a terminal and from Semaphore (task 9) | **green** both ways: probe 2 s, report `robotont-123  at  10.42.0.239` and the laptop under "SSH open but not a robot, or the fleet key was not accepted" (its unreachable line shows red in the log but the task succeeds). First Semaphore attempt found nothing: the bench firewall rule had been lost when the robot's reboot re-activated the laptop's shared profile (documented in semaphore-setup.md with a dispatcher script) |
| 2026-11-04 | robotont-123 (no mainboard, no lidar), from Semaphore via `bootstrap run` | new task "4. Run image" (tasks 11 to 17): `traefik/whoami:v1.11.0`; `prom/node-exporter:v1.9.1`; `ghcr.io/robotont/robotont-ros:2026.09-lite` as `talker-image` with Hardware yes and a `ros2 topic pub` command; name `driver`; image `nosuch/image:1`; "3. Switch workspace" driver; "2. Deploy" re-run | **green**: each run about 30 s plus the pull, `/srv/robotont/workspaces/<name>/compose.yaml` generated, `curl http://10.42.0.239/` prints `Hostname: robotont-123`, `:9100/metrics` serves `node_uname_info{nodename="robotont-123"}`, the private image pulled through peko's login, `/chatter` carries `run-image`, 5 device cgroup rules and `/dev` mounted with Hardware yes. Reserved name refused on the controller before any change; bad image fails at the pull with the pull output in the message, the generated directory is removed and the previous workspace keeps running. Deploy re-run keeps the three generated workspaces and pulls their images ("every workspace image is present") |
| 2026-11-04 | robotont-123, scenario "robot from the ground up" (fresh card earlier today) | regression and renumbering, all from Semaphore: "1. Setup Ubuntu" re-run; Setup Ubuntu with Robot number 77, Deploy 77, Run image on 77; Setup Ubuntu 123, Deploy 123, Switch driver; `inventory/robots/robotont-77.yaml` deleted | **green**, 4 min in all. Re-run: 31 s, no handover, one change (`/etc/hosts`, rewritten by cloud-init at the last reboot: `roles/robotont_host` now sets `preserve_hostname: true` and `manage_etc_hosts: false`). Renumber: hostname `robotont-77`, `robotont.env` with `ROBOTONT_ID=77`, `ROS_DOMAIN_ID=77`, namespace `rt77`, `/rt77/battery_state` listed inside the driver container, whoami answered `Hostname: robotont-77`; `robotont-77.local` did not resolve right after the rename (avahi re-announces later; not re-checked). Back to 123 the same way |
| 2026-11-04 | robotont-123, scenario "existing robot added to the management": host ROS from Setup ROS (legacy) (see the docs/06 test log), hotspot and client Wi-Fi profiles, legacy unit in `/lib/systemd/system` | adoption from Semaphore, twice (before and after the patched legacy run): "1. Setup Ubuntu", "2. Deploy", "3. Switch workspace" host, driver, "4. Run image" whoami, driver | **green** both times, about 3 min each. Setup Ubuntu: no handover, `changed=3` to `4` (cloud-init hostname file, hotspot and client profiles rewritten from `.env`, `/etc/hosts`); Deploy: the legacy unit under `/lib/systemd/system` removed, `driver` kept, `changed=1`; workspace `host` runs the host bringup through `run.sh` (driver node from `~peko/ros2_ws`, serial errors from the missing mainboard); back to `driver`; whoami answers from the laptop; `driver` restored. The hotspot `robotont-123` is active on `wlan0` since the adoption (bench password in `.env`). Not tested: reboot survival of the adopted robot (needs a reboot by hand) |
| 2026-11-04 | robotont-123 and the laptop, N2 monitoring ([10](10-monitoring.md)) | "1. Setup Ubuntu" with the new `monitoring` role (task 40); `docker compose up -d` with Prometheus v3.15.1 and Grafana 13.2.5; targets from `scripts/prometheus_targets.py` | **green**: `prometheus-node-exporter` 1.7.0 installed and configured in one run (`changed=3`), `curl :9100/metrics` from the laptop gives 1758 `node_*` lines plus the `robotont_*` textfile; the bootstrap rendered `targets/robots.json` (`10.42.0.239:9100`, labels robot, robotont_id, generation); Prometheus target `up`; Grafana provisioned the datasource and the "Robotont fleet" dashboard (21 panels), which showed in the browser: 1 robot up, 3 alerts firing (`RobotontDeviceMissing` for mainboard, lidar, gamepad: the positive test on a bench without hardware), fleet table, per-robot CPU, memory, disk, temperature (`cpu-thermal` 47 °C), restarts, network. First render showed "Value" for workspace and release and a wrong column order; fixed in the JSON (instant queries without table format; original field names in the organize transformation) |
