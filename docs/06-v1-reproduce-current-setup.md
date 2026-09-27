# 06. v1: reproduce the current setup

## Purpose

> **Legacy since 2026-09-27.** Robots are set up Docker-only ("1. Setup Ubuntu", "2. Deploy",
> [07](07-container-runtime.md)); the upstream playbooks described here remain available as the
> Semaphore task "Setup ROS (legacy)" for robots that keep ROS on the host (workspace `host`).

Automate what maintainers do by hand today, without changing it: run the existing
`robotont-setup` playbooks from Semaphore against robots that are reachable over SSH. The upstream
code is pinned as a git submodule, so every run uses a known commit, and moving to a newer commit
is a reviewed change in this repository. Improvements (idempotent roles, pinned software releases,
firmware, monitoring) come afterwards; they are listed in [05](05-implementation-plan.md) and in
the roadmap at the end of this page.

Decisions (2026-09-23): Robotont 3 on Intel NUC only, with the generation selectable in Semaphore
in the next iteration; the existing `peko` account and its sudo password; submodule created offline
from the local clone; Semaphore runs locally from `server/compose.yaml`.

## Layout

```
robotont-management/
├── .gitmodules                     external/robotont-setup (jazzy-devel-veiko), external/robotont-setup-rpi (jazzy-rpi)
├── ansible.cfg                     inventory = inventory (the directory)
├── external/robotont-setup/        the upstream playbooks and roles for NUC robots, pinned
├── external/robotont-setup-rpi/    the same repository at the Raspberry Pi branch, pinned
├── patches/robotont-setup-rpi/     applied to the checkout at run time (desktop services, camera)
├── inventory/
│   ├── groups.yaml                 robotont_nuc, robotont_rpi, and the empty run-time group robots
│   ├── robots/robotont-<N>.yaml    one file per enrolled robot, written by "1. Setup Ubuntu"
│   └── group_vars/
│       ├── all.yml                 ansible_user: peko, id: "{{ robotont_id }}", runtime defaults
│       ├── robotont_nuc.yml        robotont_generation: "3"
│       └── robotont_rpi.yml        robotont_generation: "3lite", ansible_become, jazzy-rpi variables
├── playbooks/
│   ├── setup_ubuntu.yml            1. SSH and sudo check, Ubuntu Server prerequisites, enrolment
│   ├── setup_ros.yml               legacy: preflight, patches, then the upstream robots.yaml
│   ├── deploy.yml                  2. workspaces: /srv/robotont, image pulls, unit (docs/07)
│   ├── switch_workspace.yml        3. activate a workspace (docs/07)
│   └── status.yml                  read-only report of every enrolled robot (command line, until Grafana)
├── roles/robotont_headless/        Ubuntu Server prerequisites for Lite robots
├── server/
│   ├── compose.yaml                Semaphore v2.19.14, embedded SQLite, 127.0.0.1:3000, automatic bootstrap
│   ├── bootstrap.py, templates.json
│   └── .env.example                robot-side values only
└── docs/
```

## How it works

- `playbooks/setup_ros.yml` checks the required variables, then imports the upstream
  `robots.yaml` unchanged. Roles, templates and files resolve relative to the imported playbook
  (verified with ansible-core 2.21.3), so upstream needs no edits.
- The upstream playbooks target the group `robots`. On disk that group is empty
  (`inventory/groups.yaml`); the setup playbooks put exactly the robot named by `robotont_id` into
  it with `add_host` at run time, so an upstream run can never reach the rest of the fleet. The
  host inherits its generation group's variables (verified with ansible-core 2.21.3).
- `robotont_id` maps to the upstream variable `id` in `inventory/group_vars/all.yml`.
- `robotont_generation` (group_vars, `"3"` for NUC robots, `"3lite"` for Pi robots) selects which
  upstream branch runs. The `when` on the import is inherited by every imported task, so a host
  of another generation is skipped rather than provisioned with the wrong branch.
- `playbooks/setup_ubuntu.yml` is the first contact: SSH and sudo check, the headless role on Lite
  robots, and the enrolment file `inventory/robots/robotont-N.yaml`.
- Secrets live in Semaphore: the SSH key and peko's sudo password in the key store, `wifi_pass` in
  an environment. The inventory holds no key paths or passwords.
- The upstream `ros` role needs the `community.general` collection (`locale_gen`). The Semaphore
  image ships it; on another machine run `ansible-galaxy collection install community.general`
  once. The repository keeps no `requirements.yml` on purpose: Semaphore would auto-install it
  from Galaxy on every task.

## The submodule

`external/robotont-setup` is `robotont-setup` at commit `6f40808` (head of `jazzy-devel-veiko`,
2025-12-03). `.gitmodules` records the GitHub URL and the branch.

- Fresh clone: `git clone --recurse-submodules git@github.com:robotont/robotont-management.git`.
  Existing clone: `git submodule update --init`.
- Show the pin: `git submodule status`.
- Move to the newest upstream commit: `git submodule update --remote external/robotont-setup`,
  review `git -C external/robotont-setup log`, then commit the new pointer here.
- Created offline from the local clone at `~/uni/robotont/robotont-setup` (the jazzy ref was fetched
  from that path, the recorded URL was then switched to GitHub). Online equivalent:
  `git submodule add -b jazzy-devel-veiko https://github.com/robotont/robotont-setup.git external/robotont-setup`.

## Robotont 3 Lite (Raspberry Pi 5)

Added on 2026-09-26 for the first robot at hand. Lite robots use the second submodule
`external/robotont-setup-rpi` (branch `jazzy-rpi`, commit `77a5ec5`), the inventory group
`robotont_rpi` with `robotont_generation: "3lite"`, and the same `setup_ros.yml`, which imports
the matching upstream playbook per generation.

Two things differ from a robot installed from the Ubuntu Desktop image:

- The Pi under test runs **Ubuntu Server** (no desktop). The role `robotont_headless` installs
  NetworkManager and BlueZ and lets NetworkManager manage every interface (netplan renderer,
  cloud-init network config disabled), which is what the upstream Wi-Fi setup needs, and reboots
  once after the handover so that no systemd-networkd address survives it. It is a no-op on a
  Desktop install; set `robotont_headless: false` to skip it.
- The upstream task that disables desktop services (cups, whoopsie, speech-dispatcher,
  accounts-daemon) fails on Server because the units do not exist. The first patch in
  `patches/robotont-setup-rpi/` makes it tolerate missing units; the second skips the IMX500
  camera stack unless `robotont_camera` is true (the Camera field of "1. Setup Ubuntu").
  `setup_ros.yml` applies both to the submodule checkout on the controller before the import
  (idempotent, also on Semaphore's fresh checkouts). Both are candidates for an upstream pull request.

The upstream README runs the Pi branch with `-K -b`; `inventory/group_vars/robotont_rpi.yml`
sets `ansible_become: true` for the group instead, so no extra flag is needed.

Lite robots without the IMX500 camera are enrolled with Camera = no; the camera tasks build
libcamera and need the custom kernel from `robotont_kernel/`.

Variables the Pi branch needs, provided by the Semaphore environment or `-e`: `wifi_hotspot_password`,
`wifi_client_ssid`, `wifi_client_password`. Run over Ethernet: the playbook activates the client
Wi-Fi profile and the hotspot, which drops a Wi-Fi session.

## Running from the command line

```
# NUC robot, number 1
ansible-playbook playbooks/setup_ubuntu.yml -K -e robot_address=192.168.1.21 -e robotont_id=1 -e robot_type=3 -e robotont_camera=false
ansible-playbook playbooks/setup_ros.yml -K -e robotont_id=1 -e wifi_pass=<hotspot password>
# Raspberry Pi without camera, number 123
ansible-playbook playbooks/setup_ubuntu.yml -K -e robot_address=robotont-123.local -e robotont_id=123 -e robot_type=3lite -e robotont_camera=false
ansible-playbook playbooks/setup_ros.yml -K -e robotont_id=123 \
  -e wifi_hotspot_password=<hotspot password> -e wifi_client_ssid=<lab ssid> -e wifi_client_password=<lab password>
ansible-playbook playbooks/status.yml -K        # read-only report of every enrolled robot
```

`-K` asks for peko's sudo password. `ansible.cfg` points at the directory `inventory/`.

## Running from Semaphore

See [semaphore-setup.md](semaphore-setup.md): `docker compose -f server/compose.yaml up -d` creates
the project, keys, repository, inventory, environment and the four tasks from `server/.env`. Run
"1. Setup Ubuntu", then "Setup ROS (legacy)".

## Selecting robots and the generation

- Which robot: the Robot number field of the dialog (`-e robotont_id=N` on the command line). A
  setup task always runs on one robot.
- Which generation: the Robot type field of "1. Setup Ubuntu" puts the robot into `robotont_nuc`
  or `robotont_rpi`; `robotont_generation` comes from that group's variables and `setup_ros.yml`
  imports the matching upstream playbook. No per-run choice afterwards.

## What v1 knowingly keeps

- **Not idempotent.** Every "Setup ROS (legacy)" run upgrades all apt packages, wipes and rebuilds the
  ROS workspace and fetches from GitHub. It is a reinstall, not an update. "1. Setup Ubuntu" and
  `status.yml` are safe to repeat at any time.
- **Reboot at the end** of the upstream role, with errors ignored. Follow "Setup ROS (legacy)" with `status.yml`.
- **Hotspot switch.** `netplan apply` turns the Wi-Fi interface into the hotspot `robotont-<id>`;
  provisioning over Wi-Fi cuts the session. Use Ethernet.
- **Deprecated `apt_key`** in the upstream ros role: fine with ansible-core 2.21 on Ubuntu 24.04,
  removed in ansible-core 2.25. Keep the Semaphore image pinned until the own roles replace it.
- **Unpinned workspace.** The upstream `.rosinstall` imports the `jazzy-devel` branch heads, so two
  robots provisioned on different days can differ. Fixed by pinned releases later.
- **Two branches, one per generation.** The RPi branch would fail on a NUC (`dpkg_selections hold linux-image-raspi`) and the NUC branch maps ARM to an unknown apt architecture, so the generation in the inventory must be right.

## Roadmap after v1

The container runtime ([07](07-container-runtime.md)) is planned in parallel: it keeps this
layer and adds Docker workspaces on top; `host` remains a workspace for robots set up this way.

1. Generation selectable in Semaphore: done through the inventory groups (`robotont_generation`); a survey variable override is optional.
2. Upstream hygiene with the robotont-setup maintainers: a variable around the final reboot,
   `arm64` architecture mapping, the dead `robots-update` template reference, one Jazzy branch.
3. Own idempotent roles ([03](03-provisioning-steps-mapping.md), [05](05-implementation-plan.md)),
   swapped in for the imports one at a time; `bootstrap.yml` for a `fleet-admin` account.
4. Pinned software releases ([04](04-software-firmware-versioning.md), section 2).
5. Firmware ([04](04-software-firmware-versioning.md), section 4) after the ST-Link decision.
6. Monitoring ([04](04-software-firmware-versioning.md), section 6).

## Test log

Procedure: [08-hardware-test-guide.md](08-hardware-test-guide.md), Part A.

| Date | Robot | Task | Result |
|---|---|---|---|
| 2026-09-23 | none | syntax check, inventory parse, compose config | see the verification in the commit message; not yet run against a robot |
| 2026-09-26 | robotont-123 (Pi 5, Ubuntu Server 24.04.5, Wi-Fi + Ethernet, no mainboard, no camera) | test_connection, healthcheck (report mode) | both green from the Mac: SSH key installed, sudo ok, hostname, 52 GB free |
| 2026-09-26 | robotont-123 | provision.yml `--skip-tags camera` | aborted by hand at the headless role's wait step: NetworkManager gave up on wlan0 (old wpa_supplicant held it) and eth0 got a new DHCP lease; role reordered (apply, then restart NetworkManager; avahi added; address by name). Upstream playbook not yet reached. Re-test per docs/08 |
| 2026-09-26 | robotont-123 (after reboot: NetworkManager owns eth0 and wlan0) | test_connection, then provision.yml `--skip-tags camera` | test_connection green; provision reached the upstream ros role and failed at `Install ROS (jazzy-desktop)`: apt "held broken packages", the image lacks the `noble-updates` suite. Headless role extended to add it. Re-run follows |
| 2026-09-26 | robotont-123 | provision.yml `--skip-tags camera` (re-run) | **green**: ok=68 changed=35 failed=0 in 18 min 41 s, reboot included. Afterwards: `robotont.service` active (NRestarts 0), hostname `robotont-123`, ROS graph on domain 123 with namespace `rt123` (`odom`, `battery_state`, `scan`, `joy`, `range_*`), udev rule in place, `peko` in dialout/input/video, `bluetoothctl` present, hotspot profile `robotont-123-hotspot` (priority -1) and client profile for the lab Wi-Fi (priority 100) active, 47 GB free. Health check green in report mode. Without hardware: driver retries `/dev/ttyACM0` once per second, `camera_node` respawns every 3 s ("no cameras available") because the upstream service template hard-codes `camera:=true`. Deployed commits captured in `robot/releases/2026.09-lite.repos` |
| 2026-09-26 | robotont-123 | Semaphore UI (user): Test connection, Health Check | **red**: the CLI Args field takes one argument per entry, so `--limit robotont-123` became a single token and Ansible looked for a playbook of that name. Fix: the bootstrap now enables Semaphore's own Limit, Tags, Skip Tags and Debug fields on every template (`task_params`) and adds survey dropdowns (`healthcheck_strict`, `preset`); the inventory lists real robots only so Limit may stay empty. Re-verified through the API with Limit `robotont-123` (Test connection ok=7) and the survey answer no (Health Check ok=11, 3 skipped) |
| 2026-09-26 | robotont-123 | Semaphore reduced to three dialog-driven tasks (user decision: simplicity, no status/restart/reboot tasks; Grafana later). `1. Setup Ubuntu` (address, number, type, camera), then `3. Switch preset` guard, then `Setup ROS (legacy)` (number), all through the Semaphore API | **green**: Setup Ubuntu ok=16 (headless role no-op, enrolment file written from inside the container, proven by deleting and re-enrolling); Switch preset fails as intended with "no container runtime yet"; Setup ROS ok=53 changed=16 skipped=67 in 6 min (the run-time `robots` group held only robotont-123; camera tasks skipped by patch 0002 through `robotont_camera: false` instead of `--skip-tags`; reboot done). `status.yml` from the Mac afterwards: service active, hostname `robotont-123` |
| 2026-09-27 | robotont-123, **fresh card**, mainboard and lidar fitted (user-driven, Semaphore UI, no static host mapping: the container resolves `.local` through the Docker host) | 1. Setup Ubuntu green; Setup ROS (legacy) | **red** at `Install ROS (jazzy-desktop)`: "Data could not be sent to remote host", although the package installed. Journal: the pre-handover networkd addresses (eth0 .71, wlan0 .70) expired at 13:13:44 next to NetworkManager's (.72, .73); the SSH session ran on an old one and timed out. Fixes: reboot after the handover in the headless role, `retries = 5` and `-4` in `ansible.cfg`. Re-run of Setup ROS (legacy) follows |
| 2026-09-27 | robotont-123, fresh card, mainboard and lidar fitted (user-driven, Semaphore UI) | Setup ROS (legacy) re-run | **green** in 11 min. `status.yml` from the Mac: service active, `NRestarts=0`, hostname `robotont-123`, `mainboard_present: true`, 46 GB free, workspace = the Lite release commits. On the robot: `/dev/robotont -> ttyACM0`, `/dev/lidar -> ttyUSB0`, RPLidar identified (S/N, firmware 1.02), driver opens the mainboard ("Hardware interface is ready") but no `odom`, `battery_state` or `joint_states` topics: the mainboard sends nothing (battery not connected; firmware side, left out of this test by the user). Hotspot profile `robotont-123-hotspot` present. `camera_node` respawns every 3 s (upstream unit hard-codes `camera:=true`, docs/08 issue 5); gamepad not paired yet |
| 2026-09-27 | robotont-123, fresh card | 3. Setup Docker, 4. Switch preset driver (user-driven) | green after a transient ISP outage; details in the docs/07 test log |
| 2026-09-27 | robotont-123 | Semaphore reduced to 1. Setup Ubuntu / 2. Deploy / 3. Switch workspace; this path becomes "Setup ROS (legacy)" | see the docs/07 test log |
