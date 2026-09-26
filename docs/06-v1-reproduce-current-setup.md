# 06. v1: reproduce the current setup

## Purpose

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
├── .gitmodules                     external/robotont-setup -> robotont-setup, branch jazzy-devel-veiko
├── ansible.cfg
├── collections/requirements.yml    community.general (needed by the upstream ros role)
├── external/robotont-setup/        the upstream playbooks and roles, pinned
├── inventory/
│   ├── hosts.yaml                  group robots, child group robotont_nuc
│   └── group_vars/
│       ├── robots.yml              ansible_user: peko, id: "{{ robotont_id }}"
│       └── robotont_nuc.yml        robotont_generation: "3"
├── playbooks/
│   ├── provision.yml               preflight, then the upstream robots.yaml
│   ├── setup_service.yml           the upstream robotont_service.yaml
│   ├── test_connection.yml         submodule and collection check, upstream ping, sudo check
│   ├── healthcheck.yml             read-only report and assert
│   ├── reboot.yml
│   └── restart_services.yml
├── server/
│   ├── compose.yaml                Semaphore v2.19.14, BoltDB, 127.0.0.1:3000
│   └── .env.example                admin credentials, key-store encryption
└── docs/
```

## How it works

- `playbooks/provision.yml` checks the required variables, then imports
  `external/robotont-setup/ansible/robots.yaml` unchanged. Roles, templates and files resolve
  relative to the imported playbook (verified with ansible-core 2.21.3), so upstream needs no edits.
- The inventory keeps the upstream group name `robots` and maps this repository's `robotont_id` to
  the upstream variable `id` in `inventory/group_vars/robots.yml`.
- `robotont_generation` (group_vars, `"3"` for NUC robots) selects which upstream branch runs. The
  `when` on the import is inherited by every imported task, so a host of another generation is
  skipped rather than provisioned with the wrong branch.
- Secrets live in Semaphore: the SSH key and peko's sudo password in the key store, `wifi_pass` in
  an environment. The inventory holds no key paths or passwords.

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
`robotont_rpi` with `robotont_generation: "3lite"`, and the same `provision.yml`, which imports
the matching upstream playbook per generation.

Two things differ from a robot installed from the Ubuntu Desktop image:

- The Pi under test runs **Ubuntu Server** (no desktop). The role `robotont_headless` installs
  NetworkManager and BlueZ and lets NetworkManager manage every interface (netplan renderer,
  cloud-init network config disabled), which is what the upstream Wi-Fi setup needs. It is a
  no-op on a Desktop install; set `robotont_headless: false` to skip it.
- The upstream task that disables desktop services (cups, whoopsie, speech-dispatcher,
  accounts-daemon) fails on Server because the units do not exist. The patch in
  `patches/robotont-setup-rpi/` makes it tolerate missing units; `provision.yml` applies it to
  the submodule checkout on the controller before the import (idempotent, also on Semaphore's
  fresh checkouts). It is the first candidate for an upstream pull request.

The upstream README runs the Pi branch with `-K -b`; `inventory/group_vars/robotont_rpi.yml`
sets `ansible_become: true` for the group instead, so no extra flag is needed.

Lite robots without the IMX500 camera run Provision with `--skip-tags camera`; the camera tasks
build libcamera and need the custom kernel from `robotont_kernel/`.

Variables the Pi branch needs, provided by the Semaphore environment or `-e`: `wifi_hotspot_password`,
`wifi_client_ssid`, `wifi_client_password`. Run over Ethernet: the playbook activates the client
Wi-Fi profile and the hotspot, which drops a Wi-Fi session.

## Running from the command line

```
ansible-playbook playbooks/test_connection.yml -K
ansible-playbook playbooks/healthcheck.yml -K
ansible-playbook playbooks/provision.yml -K -e wifi_pass=<hotspot password> --limit robotont-1
# Raspberry Pi without camera:
ansible-playbook playbooks/provision.yml -K --limit robotont-123 --skip-tags camera \
  -e wifi_hotspot_password=<hotspot password> -e wifi_client_ssid=<lab ssid> -e wifi_client_password=<lab password>
```

`-K` asks for peko's sudo password. `ansible.cfg` points at `inventory/hosts.yaml`.

## Running from Semaphore

See [semaphore-setup.md](semaphore-setup.md): start the container, register the repository, the
inventory file, the two credentials and the environment, then run "Test connection" before anything else.

## Selecting robots and the generation

- Which robots: `--limit robotont-1` (allowed as a CLI argument override on the Semaphore template).
- Which generation: `robotont_generation` per inventory group. The next iteration adds
  `external/robotont-setup-rpi` (branch `jazzy-rpi`), the group `robotont_rpi` with
  `robotont_generation: "3lite"`, a second import in `provision.yml`, and a Semaphore survey
  variable so the value can be chosen when a task is started.

## What v1 knowingly keeps

- **Not idempotent.** Every Provision run upgrades all apt packages, wipes and rebuilds the ROS
  workspace and fetches from GitHub. Provision is a reinstall, not an update. Health Check is the
  only task that is safe to repeat at any time.
- **Reboot at the end** of the upstream role, with errors ignored. Follow a Provision with a Health Check.
- **Hotspot switch.** `netplan apply` turns the Wi-Fi interface into the hotspot `robotont-<id>`;
  provisioning over Wi-Fi cuts the session. Use Ethernet.
- **Deprecated `apt_key`** in the upstream ros role: fine with ansible-core 2.21 on Ubuntu 24.04,
  removed in ansible-core 2.25. Keep the Semaphore image pinned until the own roles replace it.
- **Unpinned workspace.** The upstream `.rosinstall` imports the `jazzy-devel` branch heads, so two
  robots provisioned on different days can differ. Fixed by pinned releases later.
- **Two branches, one per generation.** The RPi branch would fail on a NUC (`dpkg_selections hold linux-image-raspi`) and the NUC branch maps ARM to an unknown apt architecture, so the generation in the inventory must be right.

## Roadmap after v1

The container runtime ([07](07-container-runtime.md)) is planned in parallel: it keeps this
layer and adds Docker presets on top, starting with preset `host` (no behaviour change).

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
