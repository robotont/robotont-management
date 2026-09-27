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

Re-run `docker compose -f server/compose.yaml up -d` after editing `.env` or `templates.json`:
the bootstrap is idempotent and updates in place (`docker logs robotont-semaphore-bootstrap`).

## The tasks

Numbered in the order they are needed. Each run dialog asks only for what the task needs; there
is no Limit, tag or CLI argument field.

| Task | Dialog fields | What it does | Time |
|---|---|---|---|
| 1. Setup Ubuntu | Robot address, Robot number, Robot type, Camera | once per robot: SSH and sudo check; on Lite robots the Ubuntu Server prerequisites (updates suite, NetworkManager, BlueZ, avahi, network handover and one reboot); hostname, udev symlinks, device groups, hotspot and lab Wi-Fi profiles; Docker Engine; writes `inventory/robots/robotont-N.yaml` | about 5 min on a fresh Lite robot; seconds when re-run |
| 2. Deploy | Robot number | the workspaces of this repository ([07](07-container-runtime.md)): `/srv/robotont`, image pulls from GHCR, `robotont.service`, metrics timer; the first deploy selects the `driver` workspace, later deploys restart it when its image changed | 1 to 6 min; 15 to 40 min when the image must be built on the robot |
| 3. Switch workspace | Robot number, Workspace | activates a workspace on one robot | 1 min |
| Setup ROS (legacy) | Robot number | the upstream robotont-setup playbook, unchanged, for robots that keep ROS on the host (workspace `host`): apt upgrade, ROS 2 Jazzy, workspace build, reboot. Not needed for workspaces | 20 to 60 min |

Fields:

- **Robot address**: IP or DNS name Ansible reaches the robot at. `.local` names work when the
  Docker host resolves mDNS (Docker Desktop on macOS does); on a Linux server without mDNS use an
  IP with a DHCP reservation, a DNS name, or `extra_hosts` in `server/compose.yaml`.
- **Robot number** N (1 to 254): hostname `robotont-N`, `ROS_DOMAIN_ID` N, hotspot `192.168.200.N`.
- **Robot type**: Robotont 3 Lite (Raspberry Pi 5) or Robotont 3 (Intel NUC); selects the group
  and its variables (release, sensors).
- **Camera**: yes when the IMX500 AI camera is fitted (Lite robots); no skips the camera stack.
- **Workspace**: the directories under `robot/workspaces` (`host` only where ROS is installed on
  the host). The dropdown is filled when the bootstrap runs: after adding a workspace, run
  `docker compose -f server/compose.yaml up -d` again.

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
docker compose -f server/compose.yaml run --rm -T bootstrap run "2. Deploy" --var robotont_id=123
docker compose -f server/compose.yaml run --rm -T bootstrap run "3. Switch workspace" --var robotont_id=123 --var workspace=driver
```

`playbooks/status.yml` (read-only report of every enrolled robot) runs from the command line only:
`ansible-playbook playbooks/status.yml -K`.

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
