# Semaphore setup

Semaphore is the operator interface for setting robots up and deploying workspaces. It is not a monitoring tool: robot
health goes to Prometheus and Grafana later ([05](05-implementation-plan.md)). The server side is
configured automatically; the only input is `server/.env` with the robot-side values (SSH key
path, sudo password, Wi-Fi). Security model: the instance runs on the maintainer's machine or
inside the UT private network, so the admin credentials are fixed (`admin` / `admin`) and the key
store is not encrypted at rest.

## Start

```
cp server/.env.example server/.env      # fill in: ROBOT_SSH_KEY_FILE, ROBOT_SUDO_PASSWORD, Wi-Fi values
docker compose -f server/compose.yaml up -d
open http://localhost:3000              # admin / admin
```

`up -d` starts Semaphore (`semaphoreui/semaphore:v2.19.14`, pinned; embedded SQLite database) and
then the one-shot service `bootstrap`, which waits for the API and creates or updates, from
`server/.env` and `server/templates.json`:

| Object | Name | Content |
|---|---|---|
| Project | Robotont fleet | |
| Key | `peko-ssh` | the private key from `ROBOT_SSH_KEY_FILE`, login `ROBOT_USER` |
| Key | `peko-sudo` | login `root` (the user to become), password `ROBOT_SUDO_PASSWORD` |
| Key | `none` | for the local repository |
| Repository | robotont-management | local path `/repositories/robotont-management` (this working tree, bind-mounted, submodules included), branch `main` |
| Inventory | robots | type File, the directory `inventory/` (groups, one file per enrolled robot, group_vars), user credentials `peko-ssh`, sudo credentials `peko-sudo` |
| Environment | robotont-secrets | extra variables `wifi_pass`, `wifi_hotspot_password`, `wifi_client_ssid`, `wifi_client_password` (those set in `.env`) |
| Templates | the tasks below | from `server/templates.json`; the Workspace dropdown from `robot/workspaces`; templates not listed there are removed |

The bootstrap also applies the patches under `patches/` to the submodule checkouts
(`scripts/apply_patches.sh`, idempotent) before it configures anything, because "Setup ROS
(legacy)" imports the upstream playbooks statically and Ansible parses them before the
patch play inside that playbook can run (a fresh clone ran unpatched once, 2026-11-04).

Re-run `docker compose -f server/compose.yaml up -d` after editing `.env` or `templates.json`:
the bootstrap is idempotent and updates in place (`docker logs robotont-semaphore-bootstrap`).

## The tasks

Numbered in the order they are needed. Each run dialog asks only for what the task needs; there
is no Limit, tag or CLI argument field.

| Task | Dialog fields | What it does | Time |
|---|---|---|---|
| 0. Find robots | Network | only when `robotont-N.local` does not resolve: probes the network for SSH hosts, logs in with the fleet key, lists every `robotont-N` with its address. Changes nothing | 30 s |
| 1. Setup Ubuntu | Robot address, Robot number, Robot type, Camera | once per robot: SSH and sudo check; on Lite robots the Ubuntu Server prerequisites (updates suite, NetworkManager, BlueZ, avahi, network handover and one reboot); hostname, udev symlinks, device groups, hotspot and lab Wi-Fi profiles; Docker Engine; writes `inventory/robots/robotont-N.yaml` | about 5 min on a fresh Lite robot; seconds when re-run |
| 2. Deploy | Robot number | the workspaces of this repository ([07](07-container-runtime.md)): `/srv/robotont`, image pulls from GHCR, `robotont.service`, metrics timer; the first deploy selects the `driver` workspace, later deploys restart it when its image changed | 1 to 6 min; 15 to 40 min when the image must be built on the robot |
| 3. Switch workspace | Robot number, Workspace | activates a workspace on one robot | 1 min |
| 4. Run image | Robot number, Image, Name, Command, Hardware access | runs any container image on one robot as a workspace: generates `/srv/robotont/workspaces/<name>/compose.yaml` on the robot (host network, ROS environment, optional `/dev` access), pulls the image as `peko`, activates it. Needs 2. Deploy on that robot. Nothing is written to the repository | 1 to 3 min plus the pull |
| Setup ROS (legacy) | Robot number | the upstream robotont-setup playbook, unchanged, for robots that keep ROS on the host (workspace `host`): apt upgrade, ROS 2 Jazzy, workspace build, reboot. Not needed for workspaces | 20 to 60 min |

Fields:

- **Network**: the robots' network as CIDR, for example `192.168.1.0/24`, at most /22. Found
  with `ip addr` (Linux), `ifconfig` (macOS) or `ipconfig` (Windows) on the host.
- **Robot address**: IP or DNS name Ansible reaches the robot at. `.local` names work when the
  Docker host resolves mDNS (Docker Desktop on macOS does); on a Linux server without mDNS use an
  IP with a DHCP reservation, a DNS name, or `extra_hosts` in `server/compose.yaml`. When the
  name does not resolve, "0. Find robots" prints the address.
- **Robot number** N (1 to 254): hostname `robotont-N`, `ROS_DOMAIN_ID` N, hotspot `192.168.200.N`.
- **Robot type**: Robotont 3 Lite (Raspberry Pi 5) or Robotont 3 (Intel NUC); selects the group
  and its variables (release, sensors).
- **Camera**: yes when the IMX500 AI camera is fitted (Lite robots); no skips the camera stack.
- **Workspace**: the directories under `robot/workspaces` (`host` only where ROS is installed on
  the host). The dropdown is filled when the bootstrap runs: after adding a workspace, run
  `docker compose -f server/compose.yaml up -d` again.

- **Image**: a reference such as `traefik/whoami:v1.11.0`, `prom/node-exporter:v1.9.1` or
  `ghcr.io/org/app:tag`. A private registry works after `docker login` as `peko` on the robot.
- **Name** (optional): the workspace name, `[a-z0-9-]`; empty takes the image name
  (`prom/node-exporter:v1.9.1` becomes `node-exporter`). Names of repository workspaces are refused.
- **Command** (optional): replaces the image's command, for example `ros2 run demo_nodes_cpp talker`.
- **Hardware access**: yes mounts `/dev` read-only and allows the mainboard, lidar and gamepad
  device majors (the `hardware` definition of `_common/services.yaml`); no gives the `ros-app` one.
  A generated workspace is re-activated by running the task again with the same name;
  "3. Switch workspace" driver brings the bringup back. Remove one on the robot with
  `sudo rm -r /srv/robotont/workspaces/<name>`.

The Wi-Fi values are the same for every robot and come from `.env` through the environment.

Every task runs on exactly the robot named in the dialog. The playbooks target the group
`robots`, which is empty on disk; each task puts the selected robot into it at run time.

## Enrolment

"1. Setup Ubuntu" writes `inventory/robots/robotont-N.yaml` (group, address, number, camera).
That file is the fleet record: commit it, delete it to remove the robot. Nothing is edited by hand.
Written from inside the container into the bind-mounted repository; on a Linux server the
repository directory must be writable by uid 1001.

## From a terminal

The same tasks without the UI, with the dialog fields as `--var` (also how the setup was verified):

```
docker compose -f server/compose.yaml run --rm -T bootstrap run "1. Setup Ubuntu" \
  --var robot_address=robotont-123.local --var robotont_id=123 --var robot_type=3lite --var robotont_camera=false
docker compose -f server/compose.yaml run --rm -T bootstrap run "0. Find robots" --var network=192.168.1.0/24
docker compose -f server/compose.yaml run --rm -T bootstrap run "2. Deploy" --var robotont_id=123
docker compose -f server/compose.yaml run --rm -T bootstrap run "3. Switch workspace" --var robotont_id=123 --var workspace=driver
docker compose -f server/compose.yaml run --rm -T bootstrap run "4. Run image" --var robotont_id=123 --var image=traefik/whoami:v1.11.0 --var hardware=no
```

`playbooks/status.yml` (read-only report of every enrolled robot) runs from the command line only:
`ansible-playbook playbooks/status.yml -K`.

## Linux host (Docker Engine, not Docker Desktop)

Verified 2026-11-04 on Ubuntu 24.04 with Docker Engine 29. Three differences from macOS:

- The `bootstrap` service runs as root (`user: "0:0"` in `server/compose.yaml`): a bind mount keeps
  the host owner and `0600` mode of the SSH key, which the image's user (uid 1001) cannot read.
- The container writes the enrolment file into the bind-mounted repository as uid 1001. Give it
  access once, from the repository root (files stay owned by you; ACLs are invisible to git):
  `setfacl -R -m u:1001:rwX . && find . -type d -exec setfacl -m d:u:1001:rwX {} +`
- `robotont-N.local` does not resolve inside the container (no mDNS in Docker's resolver). Give
  "1. Setup Ubuntu" the robot's IP address as the Robot address; the enrolment file then carries
  the IP, so keep it stable (DHCP reservation) or re-run Setup Ubuntu after it changes. The
  laptop itself still resolves `.local` through avahi (`nss-mdns`), so `ansible-playbook` from a
  terminal can use the name.

Bench setup, robot on a cable straight into the laptop (NetworkManager connection in `shared`
mode, laptop `10.42.0.1`): NetworkManager inserts `REJECT` rules for forwarded traffic to the
shared interface that does not come from its subnet, above Docker's rules, so the Semaphore
container cannot reach the robot although the laptop can ("Connection refused" in the task log).
Allow it for the session (not persistent; `enp0s31f6` is the shared interface, `br-+` matches
the bridge of every compose network, `docker0` alone is not enough):

```
sudo iptables -I FORWARD 1 -i br-+ -o enp0s31f6 -j ACCEPT
```

NetworkManager re-inserts its rules above everything each time the link comes up, so the rule
is lost whenever the robot reboots or the cable is replugged (seen 2026-11-04: the profile
re-activated six seconds after the robot's reboot and the next task got "Connection refused"
again). For a bench that is used more than once, let NetworkManager re-add it itself:

```
sudo tee /etc/NetworkManager/dispatcher.d/90-robotont-bench >/dev/null <<'EOT'
#!/bin/sh
# robotont bench: let Docker's compose bridges reach the shared Ethernet interface. NetworkManager
# inserts its shared-mode REJECT rules every time the link comes up; this puts ours above them.
[ "$1" = "enp0s31f6" ] && [ "$2" = "up" ] && iptables -I FORWARD 1 -i br-+ -o "$1" -j ACCEPT
exit 0
EOT
sudo chmod 755 /etc/NetworkManager/dispatcher.d/90-robotont-bench
```

## Notes

- Semaphore auto-installs any `requirements.yml` it finds in the repository from Ansible Galaxy
  on every task. The repository therefore keeps none; the image already ships `community.general`,
  which the upstream `ros` role needs.
- Templates are matched by name: renaming one in `templates.json` creates the new one and removes
  the old one. The bootstrap only touches the project named in `PROJECT_NAME` (default "Robotont fleet").
- Switching from the local path to a GitHub clone later: change `git_url`/`REPO_PATH` in
  `server/bootstrap.py` (or the repository in the UI), remove the bind mount, and check that the
  submodules are initialised in Semaphore's checkout. Enrolment files then need a push from the
  Semaphore side or a move of the inventory out of the repository.
- To reach the LAN instead of localhost only, set `SEMAPHORE_BIND=0.0.0.0` in `server/.env`.
- Upgrading Semaphore: change the pinned tag in `server/compose.yaml`; the API used by the
  bootstrap (`/api/projects`, keys, repositories, inventory, environment, templates with
  `survey_vars` and `task_params`, tasks) has been stable across 2.x, but re-run and read the
  bootstrap log after an upgrade.
