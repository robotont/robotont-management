# 02. How the existing robotont-setup Ansible works

Source: `robotont-setup`, branches `jazzy-devel-veiko` (Intel NUC, Robotont 3, last commit
2025-12-03) and `jazzy-rpi` (Raspberry Pi 5, Robotont 3 Lite, last commit 2026-03-26). Both
descend from the April 2025 Jazzy port (`jazzy-devel-sygis`) and have not been merged with each
other. The default branch `noetic-devel` (ROS 1, 2024-05-25) is used here only for comparison.

## 1. Entry points

The documented way to provision a robot is to run Ansible *on the robot itself*:

```
sudo apt install ansible git
git clone https://github.com/robotont/robotont-setup
cd robotont-setup/ansible
cp hosts.example hosts && nano hosts        # jazzy-rpi; on jazzy-devel-veiko edit hosts directly
ansible-playbook robots-local.yaml -K -b    # connection: local, asks for the sudo password
```

`robots.yaml` does the same over SSH for every host in the `[robots]` group. The RPi README
recommends it for a "swarm": image one SD card, clone it, then personalise every robot with
`robots.yaml`. Both playbooks apply the single role `robots`.

| Playbook | Hosts | What it does | Verdict |
|---|---|---|---|
| `robots-local.yaml` | `local` (connection: local) | Full provisioning of the machine it runs on | The documented path |
| `robots.yaml` | `robots` | Full provisioning over SSH | Closest to what the fleet needs |
| `robots-update.yaml` | `robots` | Only hostname, `/etc/hosts`, netplan and reboot. No software update despite the name | Broken on `jazzy-devel-veiko`: it templates `Testik_netplan.j2`, which was renamed to `robot_netplan.j2` |
| `robotont_service.yaml` | `robots` | Install and enable `robotont.service` | Duplicate of two tasks in the `robots` role |
| `pair_gamepad.yaml` (RPi only) | `robots` | Unpair all gamepads, then pair the first one found in a 30 s scan | Needs a person to put the pad into pairing mode |
| `robotont_AP.yaml` | `robots` | hostapd and dnsmasq access point; masks NetworkManager and stops systemd-resolved | Legacy. Conflicts with the NetworkManager networking used everywhere else |
| `robots-netplan.yaml`, `fix_hostnames.yaml`, `map_nav_deps.yaml`, `clearbot_NetworkManager.yaml`, `testing_NetPlan_AP.yaml`, `test_connections.yaml` | various | One-off or ROS 1 era (`ros-melodic-*`, `clearbot-N` hostnames) | Legacy |
| `laptops*.yaml`, roles `laptops*` | `laptops` | Student laptops | Out of scope |

Role dependencies (`meta/main.yaml`): `robots` depends on `common` and `ros`; `common` depends
on `ros`. Ansible therefore runs the roles in the order **ros, common, robots**.

## 2. Inventory and variables

The inventory is an INI file (`ansible/hosts`) with one line per robot:

```
[all:vars]
ansible_private_key_file=~/.ssh/robotont
ansible_user=peko
wifi_pass=

[robots]
192.168.1.21 id=36
```

| Variable | Defined in | Meaning |
|---|---|---|
| `id` | host line | Robot number N. Drives the hostname `robotont-N`, `ROS_DOMAIN_ID=N`, the hotspot SSID `robotont-N` and its address `192.168.200.N/24`, and on the RPi branch the ROS namespace `rtN` |
| `ansible_user` | `[all:vars]`, `peko` | Both the SSH login for Ansible and the robot's desktop user: owner of `~/ros2_ws`, `User=` of the systemd service, member of `dialout` and `input` |
| `ansible_private_key_file` | `[all:vars]` | `~/.ssh/robotont` |
| `wifi_pass` | `[all:vars]` | Hotspot password, plain text in the inventory |
| `is_robot` | host line | Not used by the Jazzy roles |
| `apt_packages` | `roles/robots/defaults` | `openssh-server screen vim net-tools joystick` (RPi adds `python3-pip`) |
| `ros_distribution`, `ros_configuration` | `roles/ros/defaults` | `jazzy`, `desktop` |
| `ros_domain_id` | `roles/ros/defaults` | `{{ id }}` |
| `ros_ws`, `ros_ws_install_file` | `roles/ros/defaults` | `/home/<user>/ros2_ws`, `files_for_robots/.rosinstall` |
| `ros_packages` | `roles/ros/defaults` | `image-transport-plugins` (RPi adds `camera-calibration`, `navigation2`) |
| `ros_gpg_key_url`, `ros_repository_url` | `roles/ros/defaults` | rosdistro `ros.key`, `packages.ros.org/ros2/ubuntu` |
| `robotont_user`, `robotont_group`, `robotont_password` | RPi `hosts.example` | Replace `ansible_user` as the robot account; the account is created in `pre_tasks` if missing |
| `wifi_hotspot_password`, `wifi_client_ssid`, `wifi_client_password` | RPi `hosts.example` | Hotspot and client Wi-Fi profiles |
| `reset_workspace` | RPi, extra var | Delete `ros2_ws/src` before importing |

## 3. Task-by-task walk-through (`jazzy-devel-veiko`, execution order)

"Idempotent" below means: a second run on an already provisioned robot reports no change and
does no work. "Re-runs" means the task executes and reports `changed` every time.

| # | Role / file | Task | Module | Idempotent? | Notes |
|---|---|---|---|---|---|
| 1 | ros / ros-locale | install `locales`, `locale_gen en_US.UTF-8` | apt, locale_gen | yes | |
| 2 | ros / ros-locale | `update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8` | command | re-runs | harmless |
| 3 | ros / ros-install | curl, lsb-release, software-properties-common | apt | yes | |
| 4 | ros / ros-install | ROS GPG key into `/usr/share/keyrings/ros-archive-keyring.gpg` | apt_key (url) | yes | `apt_key` is deprecated; downloads the key from GitHub on every run to compare it |
| 5 | ros / ros-install | `deb [arch=... signed-by=...] packages.ros.org/ros2/ubuntu <codename> main` | apt_repository | yes | arch mapped from `ansible_architecture` |
| 6 | ros / ros-install | `ros-jazzy-desktop`, `ros-dev-tools`, `python3-rosdep`, `python3-vcstool` | apt (loop) | yes | one apt transaction per item |
| 7 | ros / ros-install | `rosdep init` if `/etc/ros/rosdep/sources.list.d/20-default.list` is missing | stat + command | yes | |
| 8 | ros / ros-install | `rosdep update` | command | re-runs | network access every run, as the login user |
| 9 | ros / ros-install | `.bashrc`: `source /opt/ros/jazzy/setup.bash`, `export ROS_DOMAIN_ID=N` | lineinfile | yes | interactive shells only |
| 10 | ros / ros-packages-install | `ros-jazzy-<pkg>` for `ros_packages` | apt (loop) | yes | |
| 11 | ros / ros-workspace-setup | delete `ros2_ws/build`, `install`, `logs` | file absent | destructive | wipes the build on every run |
| 12 | ros / ros-workspace-setup | create `ros2_ws/src`, copy `.rosinstall` | file, copy | yes | |
| 13 | ros / ros-workspace-setup | `bash -ic 'vcs import < .rosinstall'` | shell | re-runs | clones branch heads (`jazzy-devel`), so the result depends on the day it runs |
| 14 | ros / ros-workspace-setup | `rosdep update` as root | command | re-runs | second time in the same run |
| 15 | ros / ros-workspace-setup | `rosdep check` for missing keys, then `rosdep install --skip-keys` | shell | re-runs | `failed_when: false` hides real failures; the unknown-key handling itself is sensible |
| 16 | ros / ros-workspace-setup | `bash -ic 'colcon build'` | shell | re-runs | full rebuild every run (tens of minutes on a NUC, longer on a Pi) |
| 17 | ros / ros-workspace-setup | `.bashrc`: `source ros2_ws/install/setup.bash` | lineinfile | yes | |
| 18 | common | `apt upgrade`, `update_cache` | apt | re-runs | upgrades every upgradable package on every run (`upgrade: yes` and the RPi branch's `upgrade: safe` are the same mode) |
| 19 | common | git, vim, htop | apt | yes | |
| 20 | common | `wifi.powersave = 2` in the NetworkManager conf | lineinfile | yes | NetworkManager is never restarted, so it applies after reboot |
| 21 | common | `ufw disable` | command | re-runs | `community.general.ufw` exists |
| 22 | robots | purge `libreoffice*` | apt absent | yes | |
| 23 | robots | add the user to `dialout`, `input` | user | yes | RPi adds `video` |
| 24 | robots | RealSense udev rules via `wget` from GitHub master | command | re-runs | network fetch every run |
| 25 | robots | `99-robotont.rules` (USB 0483:5740 to `/dev/robotont`) | copy | yes | RPi adds 10c4:ea60 to `/dev/lidar` |
| 26 | robots | `udevadm control --reload-rules; udevadm trigger` | shell | re-runs | should be a handler |
| 27 | robots | `apt_packages` | apt (loop) | yes | |
| 28 | robots | template `robotont.service` to `/lib/systemd/system/` | template | yes | no `daemon-reload`, no restart when the unit changes |
| 29 | robots | enable and start `robotont.service` | service | yes | |
| 30 | robots | `hostnamectl set-hostname robotont-N` | command | re-runs | `hostname` module exists |
| 31 | robots | `127.0.1.1 robotont-N` in `/etc/hosts` | lineinfile | yes | |
| 32 | robots | netplan file for the hotspot on `wlp58s0`, `192.168.200.N/24` | template | yes | interface name hard-coded; hotspot only, no client profile |
| 33 | robots | `netplan apply` | command | re-runs | can drop the SSH session when provisioning over Wi-Fi |
| 34 | robots | reboot | reboot | re-runs | unconditional, `ignore_errors: true` |

Counts for the `jazzy-devel-veiko` roles: 13 `command` or `shell` tasks, no handlers, one
unconditional reboot in `robots`, one in `robots-update`, and one in the unused
`common/tasks/xbox-one.yaml`.

The `jazzy-rpi` branch keeps this structure and adds: user creation and GDM auto-login in
`pre_tasks`; `apt-mark hold` for the RPi kernel packages; disabling `cups`, `ModemManager`,
`whoopsie`, `apport`, `speech-dispatcher`, `accounts-daemon`; `vcs pull` after `vcs import`; an
optional `reset_workspace`; NetworkManager keyfiles for a hotspot *and* a client network (client
preferred via `autoconnect-priority`); tags `udev`, `camera`, `service`, `id`, `net`; and a 341
line IMX500 camera task file (custom libcamera build, needs a custom kernel).

## 4. The robot "contract" these roles establish

A provisioned Jazzy robot looks like this. A fleet role must preserve these facts so that robots
already provisioned with `robotont-setup` can be adopted without a reinstall.

| Aspect | Value |
|---|---|
| OS user | `peko` (sudo, `dialout`, `input`, `video`), home `/home/peko` |
| Hostname | `robotont-N`; `/etc/hosts` has `127.0.1.1 robotont-N` |
| ROS | `ros-jazzy-desktop` from packages.ros.org, `ros-dev-tools`, rosdep initialised, `ROS_DOMAIN_ID=N` in `~/.bashrc` |
| Workspace | `/home/peko/ros2_ws` with `src/.rosinstall`, built with `colcon build`, sourced in `~/.bashrc` |
| Packages in the stack (NUC list) | `robotont_driver`, `robotont_msgs`, `robotont_description`, `robotont_nuc_description`, `robotont_support`, `laserscan_to_ranges`, `demo_teleop` (all `jazzy-devel`) |
| Packages in the stack (RPi list) | the above minus `robotont_nuc_description`, plus `robotont_lite_description`, `robotont_navigation`, `demo_slam`, `rplidar_ros` (all `jazzy`, `rplidar_ros` at `ros2`) |
| Mainboard device | `/dev/robotont` (udev, USB 0483:5740, mode 0666); RPi also `/dev/lidar` (10c4:ea60) |
| Service | `/lib/systemd/system/robotont.service`: `ExecStart=/bin/bash -ic "ros2 launch robotont_support robotont_bringup.launch.py [args]"`, `User=peko`, `Restart=always`, `After=network-online.target` |
| Bringup arguments | NUC: none (defaults: `generation:=3`, no camera, no lidar, no RealSense). RPi: `namespace:=rtN generation:=3lite lidar:=true camera:=true slam:=false` |
| Network | Hotspot SSID `robotont-N`, `192.168.200.N/24`. NUC: netplan on `wlp58s0`, hotspot only. RPi: NetworkManager keyfiles, client network preferred, hotspot as fallback |
| System tweaks | Wi-Fi power saving off, `ufw` disabled, LibreOffice removed |

The `.bashrc` is load-bearing: both Ansible (`bash -ic`) and the systemd unit (`bash -ic`) rely
on it to find ROS, the stack and `ROS_DOMAIN_ID`.

## 5. What is good and should be kept

- The role split `ros` / `common` / `robots`, and the split of the `ros` role into locale,
  install, extra packages and stack files.
- The rosdep handling that installs what it can and reports unknown keys instead of aborting.
- The udev rule, the service unit and the bringup entry point: they define what a Robotont is at
  the OS level and are stable across generations.
- The `robotont-N` / domain id / hotspot conventions, which students and the documentation rely on.
- On the RPi branch: NetworkManager keyfiles with client-first priority, the list of desktop
  services to disable, task tags, and creating the robot user in `pre_tasks`.

## 6. Problems for fleet use

1. **Not idempotent.** Every run wipes and rebuilds the stack, upgrades all apt packages,
   runs `rosdep update` twice, fetches files from GitHub and ends with a reboot. A "Provision"
   button that takes 30 minutes and reboots the robot cannot double as a health or update action.
2. **Unconditional reboot inside the role**, with `ignore_errors: true`, so a failed reboot is
   invisible.
3. **`bash -ic` everywhere.** Ansible tasks and the systemd service depend on the content and
   order of `~/.bashrc`. A student editing `.bashrc` can break the service.
4. **Two divergent Jazzy branches** with different variable names (`ansible_user` vs
   `robotont_user`), different package lists (`jazzy-devel` vs `jazzy`), different network
   mechanisms (netplan vs NetworkManager keyfiles), and a README on the NUC branch that is still
   the ROS 1 text.
5. **Software has no version.** The stack is whatever the branch heads were on the day of
   provisioning, and `jazzy-devel` is stale in four of the repositories (see 01).
6. **Hard-coded Wi-Fi interface** `wlp58s0` on the NUC branch; the Noetic branch had a
   `wifi_interface` variable that was lost in the port.
7. **`command`/`shell` where modules exist**: `hostnamectl` (hostname), `ufw disable`
   (community.general.ufw), `udevadm` and `netplan apply` (handlers), `wget` (get_url).
8. **Deprecated `apt_key`** for the ROS key.
9. **Hidden failures**: `rosdep install` runs with `failed_when: false`; the `robots-update`
   role references a template that no longer exists.
10. **Sleep and hibernate are not disabled.** The Noetic task named "Disable Sleep and Hibernate"
    actually ran `systemctl unmask ...` (the opposite), and the Jazzy branches dropped the task.
11. **Credentials in the inventory** (`wifi_pass`, `robotont_password`, `ansible_password`), and
    one account serves students, Ansible and the service.
12. **No health check, no service restart on change, no `daemon-reload`.**
13. `include_tasks` with `tags:` in the `ros` role tags only the include statement, so
    `--tags ros-install` includes the file but skips every task inside it.

## 7. Conclusion

`robotont-setup` documents the complete list of things a Robotont needs, and its roles are the
right starting point. But they were written to run once, locally, with a person watching. They
cannot be consumed as a black box by a Semaphore "Provision" or "Update" button. The practical
route is to carry the tasks and files over into this repository role by role, fix the issues
above while doing so, keep the robot contract from section 4 unchanged, and then propose to the
maintainers that `robotont-setup` either consumes these roles or is retired for robots. The
mapping is in [03](03-provisioning-steps-mapping.md), the plan in [05](05-implementation-plan.md).
