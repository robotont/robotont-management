# 05. Implementation plan

> **Update 2026-09-23.** v1 ([06](06-v1-reproduce-current-setup.md)) runs the upstream
> `robotont-setup` playbooks unchanged from the git submodule `external/robotont-setup`, which
> replaces decision 3 below for now. The milestones of this document become the later phases of
> the roadmap in 06, and `group_vars/robotonts.yml` is `group_vars/robots.yml` (the upstream
> group name).

## 1. Decisions and assumptions

Taken from the context document and the findings in 01 to 04. Items marked *(confirm)* are open
questions listed in section 6.

1. Target robots: Robotont 3 with Intel NUC, Ubuntu 24.04, ROS 2 Jazzy. Robotont 3 Lite (RPi 5)
   stays possible through `robotont_generation: "3lite"`, but its RPi-specific tasks (camera,
   kernel hold) are ported later *(confirm)*.
2. Base for porting: `robotont-setup` branch `jazzy-devel-veiko`, plus the NetworkManager
   keyfiles, the service-disable list, tags and user handling from `jazzy-rpi`. The public Jazzy
   documentation already points Lite builders to `jazzy-rpi`, so where the two branches differ
   the `jazzy-rpi` conventions (`robotont_user`, keyfile networking, `jazzy` package branches)
   are preferred.
3. The roles live in this repository and copy task logic and files from `robotont-setup`; there
   is no git dependency on `robotont-setup`. The robot contract from 02 section 4 is preserved, so
   robots provisioned the old way are adopted by running "Provision" once. Consolidation with
   `robotont-setup` is proposed to the maintainers afterwards *(confirm)*.
4. Accounts: the robot user stays `peko` (students, service, workspace). A dedicated
   `fleet-admin` account with SSH key and passwordless sudo is created by a one-time bootstrap
   playbook and used by Semaphore *(confirm)*.
5. Reachability: robots are on the lab network (Wi-Fi client profile or Ethernet) and resolvable
   as `robotont-N.local` (mDNS) or by DHCP reservation *(confirm)*. No VPN.
6. No reboot inside provisioning or update. Reboot is its own task.
7. Software is deployed from a pinned release file; the first release pins the current `jazzy`
   heads (not `jazzy-devel`).
8. Firmware update follows option A in 04 section 4 (ST-Link attached to the NUC), pending the
   hardware decision *(confirm)*. Milestone 1 does not depend on it.
9. Docker Compose only on the management server: Semaphore first, Prometheus and Grafana in
   Milestone 3.

## 2. Target layout of this repository

```
robotont-management/
├── README.md
├── ansible.cfg                   inventory path, roles path, pipelining, no host key prompt
├── requirements.yml              community.general (ufw, ini_file)
├── inventory/
│   ├── hosts.yaml                who the robots are and how to reach them (stub exists)
│   └── group_vars/
│       └── robotonts.yml         robotont_user, ros_distribution, release names, bringup defaults
├── playbooks/
│   ├── bootstrap.yml             one-time: fleet-admin user and key
│   ├── provision.yml
│   ├── update_software.yml
│   ├── update_firmware.yml       Milestone 2
│   ├── update_os.yml
│   ├── restart_services.yml
│   ├── reboot.yml
│   └── healthcheck.yml
├── roles/
│   ├── common/
│   ├── ros/
│   ├── robotont/                 identity, udev, service wrapper, network profiles
│   ├── robotont_software/        pinned workspace
│   ├── firmware/                 Milestone 2
│   └── monitoring/               Milestone 3
├── releases/
│   ├── 2026.09.repos             pinned software release
│   └── firmware/                 .bin and .sha256 files (Milestone 2)
├── server/
│   └── compose.yaml              Semaphore (Prometheus and Grafana later)
├── prometheus/                   Milestone 3
├── grafana/                      Milestone 3
└── docs/
```

## 3. Milestone 1: centralized provisioning

Each step names the existing code it builds on, the smallest change, and how to test it. Steps
are meant to be separate commits.

### Step 1. Skeleton, inventory, configuration

- Builds on: `robotont-setup/ansible/ansible.cfg` and `hosts`.
- Change: `ansible.cfg`, `requirements.yml`, `inventory/hosts.yaml` (written in this pass with
  two example hosts), `inventory/group_vars/robotonts.yml` with the variables listed in 03.
- Test: `ansible-inventory -i inventory/hosts.yaml --graph`;
  `ansible-playbook --syntax-check` for every playbook; `ansible robotonts -m ping` once a robot
  is reachable.

### Step 2. `bootstrap.yml`

- Builds on: the RPi branch `pre_tasks` that create the robot user.
- Change: a play that connects as `peko` with password (`-k -K`), creates `fleet-admin`, installs
  the fleet public key, adds a `sudoers.d` file with `NOPASSWD`, ensures `openssh-server`.
- Test: `ansible robotonts -m ping -u fleet-admin` without a password; `sudo -n true` succeeds.

### Step 3. Role `common`

- Builds on: `roles/common/tasks/main.yaml` (both branches), the Noetic sleep task, the
  `libreoffice` purge and the service list from the RPi `robots` role.
- Change: tasks per 03 section 2, a handler for the NetworkManager restart, no `apt upgrade`.
- Test: run `provision.yml --tags common` twice; the second run reports `changed=0`.
  `systemctl is-enabled sleep.target` prints `masked`; `ufw status` prints `inactive`.

### Step 4. Role `ros`

- Builds on: `roles/ros/tasks/ros-locale.yaml`, `ros-install.yaml`, `ros-packages-install.yaml`.
- Change: `get_url` for the key, a single `apt` task, `rosdep init` and `rosdep update` with
  `creates:`, `.bashrc` lines kept.
- Test: `dpkg -l ros-jazzy-desktop ros-dev-tools`; `rosdep --version`; second run `changed=0`.

### Step 5. Role `robotont`

- Builds on: `roles/robots/tasks/main.yaml`, `resources/99-robotont.rules` (RPi version),
  `templates/robotont.service.j2`, `robotont-ap.nmconnection.j2`,
  `robotont-client.nmconnection.j2`.
- Change: hostname and `/etc/hosts`, groups, udev rules with a handler,
  `/etc/robotont/robotont.env`, the `/usr/local/bin/robotont-bringup` wrapper, the unit in
  `/etc/systemd/system/` with `daemon-reload` and restart handlers, removal of the old unit in
  `/lib/systemd/system/`, NetworkManager keyfiles (optional, `robotont_manage_wifi: false` by
  default so that a first run over Wi-Fi cannot cut itself off).
- Test: `hostnamectl hostname` prints `robotont-N`; `ls -l /dev/robotont`;
  `systemctl status robotont`; `journalctl -u robotont -n 50` shows the driver opening
  `/dev/robotont`; with `ROS_DOMAIN_ID=N`, `ros2 topic list` shows `odom` and `battery_state`.

### Step 6. Role `robotont_software` and the first release

- Builds on: `roles/ros/tasks/ros-workspace-setup.yaml`, `files_for_robots/.rosinstall`.
- Change: `releases/2026.09.repos` pinned to the current `jazzy` heads of `robotont_driver`,
  `robotont_msgs`, `robotont_description`, `robotont_nuc_description`, `robotont_support`,
  `laserscan_to_ranges`, `demo_teleop` (the last two need their current commits looked up on
  GitHub, which needs network access); import, compare, build, `/etc/robotont/release`, restart
  handler.
- Test: `vcs export --exact` in `~/ros2_ws/src` matches the release; the service restarted once;
  a second run reports `changed=0` and does not build.

### Step 7. Playbooks

- `provision.yml` (all roles plus the health check), `healthcheck.yml`, `restart_services.yml`,
  `reboot.yml`, `update_software.yml`, `update_os.yml`.
- Test order: first on a fresh Ubuntu 24.04 VM without a mainboard (the health check must report
  the missing `/dev/robotont` clearly while the service keeps retrying), then on one robot, then
  on a robot that was provisioned with `robotont-setup` (adoption case).

### Step 8. Semaphore on the management server

- `server/compose.yaml` with `semaphoreui/semaphore` and the BoltDB backend (a single file, no
  database container), volumes for data and for the fleet SSH key.
- `docs/semaphore.md`: how to register the repository, the inventory file, the `fleet-admin`
  key, and one task template per playbook (Provision Robotont, Update Software, Update OS
  packages, Restart Robotont Services, Reboot, Health Check).
- Test: run "Health Check" from the UI against one robot; run "Provision" against a fresh VM.

### Definition of done

A fresh Ubuntu 24.04 install with user `peko` and SSH reachable becomes a working Robotont
(service active, `odom` publishing, hostname and domain id set) through "Bootstrap" once and
"Provision Robotont" once in Semaphore, and a second "Provision" run reports no changes.

## 4. Upstream fixes and requests discovered

To raise with the maintainers (Veiko). None of them blocks Milestone 1, but items 1 and 2 decide
whether a freshly provisioned NUC robot starts at all.

1. `robotont_support` (`jazzy`): the default bringup path (generation 3, `realsense:=false`)
   includes `robotont_description/launch/description.launch.py`, which does not exist on
   `jazzy` or `jazzy-devel` (they ship `upload_description.launch.py` with arguments `prefix`
   and `generation`). The launch fails on a NUC robot without RealSense unless another branch is
   used. The argument names also differ (`frame_prefix` vs `prefix`).
2. `robotont_support` `package.xml` lacks exec dependencies for `realsense2_camera`,
   `depthimage_to_laserscan`, `rplidar_ros`, `demo_teleop`, `demo_slam`,
   `robotont_nuc_description` and `robotont_lite_description`, so `rosdep` cannot install the
   apt ones, and the workspace list has to carry the git ones.
3. `robotont-setup`: `jazzy-devel` in the NUC `.rosinstall` is stale; the `robots-update` role
   references a missing template; unconditional reboot; hard-coded `wlp58s0`; sleep and
   hibernate not disabled; deprecated `apt_key`. Alternatively, adopt the roles from this
   repository.
4. Tags on the `jazzy` branches and a bumped `package.xml` version whenever something ships.
5. `robotont-firmware`: a `VER` command (version and git hash from a build flag), tags, and a CI
   workflow that publishes `.bin` artifacts. Update the OLED info screen from the same define.
6. Documentation: the Jazzy docs point Robotont 3 Lite builders to `robotont-setup` `jazzy-rpi`
   and say nothing about provisioning a NUC-based Robotont 3 or updating firmware; this
   repository's docs can fill that role once the playbooks exist.
7. Container runtime asks ([07](07-container-runtime.md)): the bringup should load
   `robotont_driver/config/parameters.yaml` (or expose `device_name`) so the driver opens
   `/dev/robotont` rather than the code default `/dev/ttyACM0`; merge `v3.0-devel-jyrgen` or,
   cleaner, add a second USB CDC interface in the firmware for the OLED menu channel so no serial
   demultiplexer is needed on the host.

## 5. Milestones 2 and 3 in brief

**Milestone 2**: `update_software.yml` with release selection (Step 6 already provides the
mechanism); `roles/firmware` per 04 section 4 option A once an ST-Link is attached to a test
robot; a compatibility table of software release against firmware version; the health check
extended with `/etc/robotont/firmware-version`.

**Milestone 3**: `roles/monitoring` installs `prometheus-node-exporter` and a systemd timer that
writes the `robotont_*` textfile metrics (04 section 6); Prometheus and Grafana join
`server/compose.yaml`; Prometheus targets are rendered by Ansible from `inventory/hosts.yaml` so
that the inventory stays the only list of robots; one Grafana dashboard with the fleet table
from context section 20.

## 6. Open questions

1. Fleet composition: how many Robotont 3 (NUC) units, and are there Robotont 3 Lite (RPi 5)
   units to manage now?
2. Is porting into this repository (rather than depending on `robotont-setup`) acceptable to the
   `robotont-setup` maintainers, and who talks to Veiko about consolidation?
3. Account model: keep `peko` for students and add `fleet-admin` for Semaphore?
4. Network: can the management server reach the robots on the lab network today (Wi-Fi client
   profile or Ethernet), and should hosts be addressed by `.local` names or fixed DHCP leases?
5. Firmware: permanently attach an ST-Link to each NUC (option A), or invest in a firmware
   bootloader command (option B)?
6. Is RealSense still part of the standard Robotont 3, that is, should `robotont_realsense`
   default to true?
7. Permission to fetch `demo_teleop`, `demo_slam` and `laserscan_to_ranges` from GitHub for
   inspection and to pin their commits in the first release file.

Default if no answers arrive: proceed with Steps 1 to 5 under the assumptions above; they do not
depend on the answers. Step 6 needs question 7 and Step 8 needs question 3.
