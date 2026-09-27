# 03. Post-install steps and their mapping to fleet roles

Scope: everything that happens after a fresh Ubuntu 24.04 install is reachable over SSH. OS
installation, creating the first user in the installer and plugging in the network stay manual
(context document, section 13).

> **Update 2026-09-26.** The Semaphore tasks named below are the original plan. The current
> tasks are 1. Setup Ubuntu, 2. Setup ROS and 3. Switch preset ([semaphore-setup.md](semaphore-setup.md));
> the read-only report is `playbooks/status.yml` on the command line until Grafana exists.

## 1. Steps a maintainer performs today

Collected from the `robotont-setup` READMEs (both Jazzy branches), the Jazzy user documentation,
and the repositories' own instructions.

| # | Step | Done today by | Fleet target |
|---|---|---|---|
| 1 | Install Ubuntu 24.04 Desktop, create user `peko` with sudo, connect to the network | Person at the robot | Stays manual |
| 2 | `apt install ansible git`, clone `robotont-setup`, edit `hosts` (id, passwords, Wi-Fi) | Person on the robot | Replaced by `inventory/` and `group_vars` in this repository |
| 3 | Run `ansible-playbook robots-local.yaml -K -b` on the robot (or `robots.yaml` over SSH) | Person | Semaphore task "Provision Robotont" |
| 4 | Wait for the automatic reboot; if Wi-Fi fails, `nmcli connection up ...` | Person | Reboot becomes its own task; network profiles are not activated during provisioning |
| 5 | Install `openssh-server`, generate a key, `ssh-copy-id` to every robot | Person | One-time `bootstrap.yml` that creates the management user and installs its key |
| 6 | Pair the gamepad with `bluetoothctl` | Person at the robot | Optional later task (the RPi branch has `pair_gamepad.yaml`); needs the pad in pairing mode, so not part of provisioning |
| 7 | Flash mainboard firmware: ST-Link on the SWD header, `pio run -t upload` from a developer PC | Developer | Milestone 2, see [04](04-software-firmware-versioning.md); needs a hardware decision |
| 8 | Flash the power-management ATtiny88 via Arduino-as-ISP | Developer | Stays manual (rare, programmer on an internal header) |
| 9 | RealSense: udev rules (Ansible) and `ros-jazzy-realsense2-camera` plus `depthimage-to-laserscan` (not declared as dependencies, so installed by hand) | Ansible and person | `ros_packages` list when `robotont_realsense: true` |
| 10 | Update software: SSH in, `vcs pull`, `colcon build`, reboot or restart the service | Person | Semaphore task "Update Software" |
| 11 | Set hostname `robotont-N`, `ROS_DOMAIN_ID`, hotspot | Ansible (`id`) | `robotont` role, driven by `robotont_id` |
| 12 | Check that the robot works: `ros2 topic list`, drive it | Person | Semaphore task "Health Check" |

## 2. Mapping of existing tasks to fleet roles

Decision codes: **keep** (copy as is), **adapt** (same intent, different module or guard),
**replace** (different mechanism), **drop**, **new**.

### Role `common` (OS baseline)

| Existing task (branch) | Decision | Fleet implementation |
|---|---|---|
| `apt upgrade` on every run (both) | replace | Provisioning only runs `update_cache`. Upgrades move to a separate playbook `update_os.yml` ("Update OS packages" in Semaphore). |
| git, vim, htop (plus screen, net-tools from `apt_packages`) | keep | one `apt` task with a list |
| purge `libreoffice*` | keep | |
| disable cups, cups-browsed, ModemManager, whoopsie, apport, speech-dispatcher, accounts-daemon (RPi) | adapt | `systemd` module, tolerate units that do not exist |
| Wi-Fi power saving off | keep | plus a handler that restarts NetworkManager |
| `ufw disable` (command) | adapt | `community.general.ufw: state=disabled` |
| Disable sleep/suspend/hibernate (Noetic, buggy; missing on Jazzy) | new | `systemd: masked` for `sleep.target suspend.target hibernate.target hybrid-sleep.target` |
| locale en_US.UTF-8 (`ros` role) | keep | move into `common`; run `update-locale` only when `/etc/default/locale` differs |
| Reboot at the end | drop | `reboot.yml` playbook |

### Role `ros` (ROS 2 Jazzy from apt)

| Existing task | Decision | Fleet implementation |
|---|---|---|
| curl, lsb-release, software-properties-common | keep | |
| ROS key via `apt_key` | adapt | `get_url` of `ros.key` into `/usr/share/keyrings/ros-archive-keyring.gpg` (idempotent by checksum). Alternative: the `ros2-apt-source` package that the current ROS 2 instructions use. |
| `apt_repository` with `signed-by`, arch mapping | keep | |
| `ros-jazzy-desktop`, `ros-dev-tools`, `python3-rosdep`, `python3-vcstool` | keep | single `apt` task; `ros_configuration` stays a variable (`desktop` for compatibility with existing robots, `ros-base` possible later) |
| `rosdep init` guarded by `stat` | keep | `creates:` instead of `stat` plus `when` |
| `rosdep update` (twice, every run) | adapt | once, as the robot user, `creates: ~/.ros/rosdep/sources.cache`; forced only in the update playbook |
| `.bashrc` lines (`source /opt/ros/jazzy/setup.bash`, `ROS_DOMAIN_ID`) | keep | for interactive use only; the service gets its environment from `/etc/robotont/robotont.env` |
| extra `ros_packages` | keep | list from `group_vars`; RealSense packages added when enabled |

### Role `robotont` (identity, hardware access, service, network)

| Existing task | Decision | Fleet implementation |
|---|---|---|
| `hostnamectl set-hostname robotont-N` | adapt | `hostname` module with `robotont-{{ robotont_id }}` |
| `/etc/hosts` 127.0.1.1 line | keep | |
| user in `dialout`, `input`, `video` | keep | user name from `robotont_user` (default `peko`) |
| `99-robotont.rules` | keep | copy the RPi version verbatim (includes the lidar rule); handler `udevadm control --reload-rules && udevadm trigger` |
| RealSense udev rules via `wget` | adapt | vendor `99-realsense-libusb.rules` into the role (no network fetch on the robot); only when `robotont_realsense: true` |
| `robotont.service` template with `bash -ic` | adapt | Unit in `/etc/systemd/system/` running `/usr/local/bin/robotont-bringup`, a small wrapper that sources `/opt/ros/jazzy/setup.bash` and `<ws>/install/setup.bash`, reads `/etc/robotont/robotont.env` (`ROS_DOMAIN_ID`, optional `RMW_IMPLEMENTATION`) and launches `robotont_support robotont_bringup.launch.py` with arguments from `robotont_bringup_args`. Handlers: `daemon-reload`, `restart robotont`. Remove the old unit from `/lib/systemd/system/` if present. |
| bringup arguments hard-coded in the template (RPi) | adapt | `robotont_generation` (`3` or `3lite`), `robotont_namespace`, `robotont_lidar`, `robotont_camera`, `robotont_realsense` become launch arguments |
| netplan hotspot on `wlp58s0` (NUC) | replace | NetworkManager keyfiles from the RPi branch, generalised: no `interface-name` (applies to any Wi-Fi device) or a `wifi_interface` variable; client profile with `autoconnect-priority=100`, hotspot fallback `robotont-N` at `192.168.200.N/24`; handler `nmcli connection reload`. Never `nmcli connection up` inside a play. |
| `netplan apply`, `nmcli connection up` | drop | |
| GDM auto-login (RPi) | keep as option | `robotont_autologin: false` by default |
| hold RPi kernel packages, IMX500 camera tasks (RPi) | defer | only relevant for `3lite`; port when Lite robots join the fleet |
| unconditional reboot | drop | `reboot.yml` |

### Role `robotont_software` (workspace build and update)

| Existing task | Decision | Fleet implementation |
|---|---|---|
| `.rosinstall` with branch names | replace | `releases/<name>.repos` in this repository (vcstool YAML), every entry pinned to a tag or commit. `robotont_software_release` selects the file. |
| `vcs import` every run | adapt | `vcs import --input <release>.repos`, then `vcs export --exact`; compare with the release; only proceed when something differs or `robotont_force_rebuild` is set |
| delete `build`, `install`, `logs` every run | adapt | only on release change or forced rebuild |
| `rosdep install` with missing-key handling | keep | keep the logic and `changed_when: false`, but let real errors fail |
| `bash -ic 'colcon build'` | adapt | `bash -lc 'source /opt/ros/jazzy/setup.bash && colcon build --symlink-install'` as `robotont_user`, `changed_when` tied to the release comparison |
| `.bashrc` sources the workspace | keep | |
| (none) | new | write `/etc/robotont/release` (release name, per-repository commit, build time) |
| (none) | new | notify `restart robotont` when the build changed |

### Playbooks

| Playbook | Roles / tasks | Semaphore task |
|---|---|---|
| `bootstrap.yml` | create `fleet-admin`, install its public key, passwordless sudo, `openssh-server` | run once per robot with the `peko` password |
| `provision.yml` | `common`, `ros`, `robotont`, `robotont_software`, then the health check | Provision Robotont |
| `update_software.yml` | `robotont_software` with the selected release, restart, health check | Update Software |
| `update_firmware.yml` | `firmware` (Milestone 2) | Update Firmware |
| `update_os.yml` | apt upgrade, report whether a reboot is required | Update OS packages |
| `restart_services.yml` | restart `robotont.service` | Restart Robotont Services |
| `reboot.yml` | `reboot` module, wait for SSH, health check | Reboot |
| `healthcheck.yml` | see below | Health Check |

### Health check content (MVP)

- `robotont.service` is active and has not restarted in the last minute (`systemctl show -p NRestarts`).
- `/dev/robotont` exists (mainboard enumerated over USB).
- With the service environment: `ros2 topic list` contains `<namespace>/odom` within a timeout;
  optionally `ros2 topic echo --once battery_state` for the voltage.
- Print `/etc/robotont/release` and `/etc/robotont/firmware-version`.
- Disk usage of `/`, load and, if available, CPU temperature from Ansible facts.

## 3. Not carried over

`robotont_AP.yaml` (hostapd and dnsmasq, masks NetworkManager), `robots-netplan.yaml`,
`update_netplan.j2`, `fix_hostnames.yaml` (clearbot era), `map_nav_deps.yaml` (Melodic),
`clearbot_NetworkManager.yaml`, `testing_NetPlan_AP.yaml`, everything under `laptops*`,
`partitioning/`, `for netplan/`, `resources/.rosinstall` (unversioned list), and the ROS 1 web
application stack (Node.js, ttyd, iptables port 80 redirect) that the Noetic role installed.
