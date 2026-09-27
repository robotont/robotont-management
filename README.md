# Robotont Management

# Overview

Centralized management and monitoring for Robotont robots.

Initial scope:
- Provision Robotont computers using Ansible
- Update Robotont ROS software
- Update Robotont firmware
- Provide a simple management interface using Semaphore
- Monitor Robotont health using Prometheus and Grafana

Planned architecture:
- Ansible for configuration and deployment
- Semaphore as the management UI
- Prometheus for metrics collection
- Grafana for monitoring
- Docker Compose for management-server services

Future work may include:
- Automated Ubuntu installation
- Containerized Robotont runtime
- More advanced inventory management
- VPN / overlay networking
- Centralized logging

## Architecture

<img src=".images/architecture.png" width="500" title="Architecture">

---

<img src=".images/architecture_detailed.png" width="1000" title="Architecture">
## Status (2026-09-26)

v1 "reproduce the current setup": the existing `robotont-setup` playbooks run unchanged from
Semaphore, pinned as git submodules: `external/robotont-setup` (branch `jazzy-devel-veiko`) for
Robotont 3 on Intel NUC and `external/robotont-setup-rpi` (branch `jazzy-rpi`, with a headless
role for Ubuntu Server) for Robotont 3 Lite on Raspberry Pi 5. Verified live on a Pi 5
(test log in [docs/06](docs/06-v1-reproduce-current-setup.md)). Semaphore has three numbered
tasks: 1. Setup Ubuntu, 2. Setup ROS, 3. Switch preset ([docs/semaphore-setup.md](docs/semaphore-setup.md)).

Container runtime (Docker on the robots, [docs/07](docs/07-container-runtime.md)): roles, presets,
scripts and playbooks written and checked statically; first deploy keeps the host runtime (preset
`host`), the first live test waits for a robot with hardware.

## Quick start

```
git clone --recurse-submodules git@github.com:robotont/robotont-management.git
cd robotont-management
ansible-galaxy collection install community.general   # once per machine; the upstream ros role needs it
ansible-playbook playbooks/setup_ubuntu.yml -K -e robot_address=192.168.1.21 -e robotont_id=1 -e robot_type=3 -e robotont_camera=false
ansible-playbook playbooks/setup_ros.yml -K -e robotont_id=1 -e wifi_pass=<hotspot password>
```

Semaphore: `cp server/.env.example server/.env`, fill in the robot-side values, then
`docker compose -f server/compose.yaml up -d`. The project, keys, inventory, environment and the
three tasks are created automatically ([docs/semaphore-setup.md](docs/semaphore-setup.md)); log in as
`admin` / `admin` at http://localhost:3000 and run "1. Setup Ubuntu".

## Repository layout

```
external/robotont-setup/   upstream playbooks and roles for NUC robots (git submodule, pinned)
external/robotont-setup-rpi/  the same repository at the Raspberry Pi branch (git submodule, pinned)
patches/                   local patches applied to the submodule checkouts at run time
inventory/                 groups.yaml, robots/ (one file per enrolled robot, written by Setup Ubuntu), group_vars
playbooks/                 setup_ubuntu, setup_ros, switch_preset (Semaphore tasks 1 to 3);
                           setup_docker (container runtime, command line until hardware-tested);
                           status (command-line report until Grafana)
roles/                     robotont_headless (Ubuntu Server prerequisites), docker, robotont_presets
robot/                     what is deployed to /opt/robotont: presets, image definitions, releases, scripts
server/                    Docker Compose for Semaphore
test/                      sample environment for static checks
docs/                      analysis, mapping, plans, runbooks
```

## Documentation

| Document | Content |
|---|---|
| [docs/01-repository-map.md](docs/01-repository-map.md) | Which repositories and branches matter, ROS 1 vs ROS 2, versioning conventions found |
| [docs/02-existing-ansible-analysis.md](docs/02-existing-ansible-analysis.md) | How `robotont-setup` provisions a robot today, task by task, and what blocks fleet use |
| [docs/03-provisioning-steps-mapping.md](docs/03-provisioning-steps-mapping.md) | Every post-install step and where it lands in the fleet roles and playbooks |
| [docs/04-software-firmware-versioning.md](docs/04-software-firmware-versioning.md) | Software deployment and versioning, firmware flashing options, monitoring signals |
| [docs/05-implementation-plan.md](docs/05-implementation-plan.md) | Decisions, target layout, steps with tests, upstream fixes, open questions (later phases) |
| [docs/06-v1-reproduce-current-setup.md](docs/06-v1-reproduce-current-setup.md) | v1: how the upstream playbooks run from here, the submodule, what v1 keeps, roadmap |
| [docs/07-container-runtime.md](docs/07-container-runtime.md) | Container runtime: presets, switching, images, devices, monitoring hooks, runbook, phases |
| [docs/semaphore-setup.md](docs/semaphore-setup.md) | The local Semaphore: automatic setup, the three tasks and their dialog fields |
| [docs/08-hardware-test-guide.md](docs/08-hardware-test-guide.md) | Step-by-step manual verification of v1 and the container runtime once a robot is available |
