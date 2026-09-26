# Semaphore setup (v1, local)

Semaphore is the operator interface: it runs the playbooks of this repository over SSH. In v1 it
runs on the maintainer's machine with Docker Compose. UI labels below are those of Semaphore 2.19;
other versions name things slightly differently.

## 1. Start Semaphore

```
cp server/.env.example server/.env
# edit server/.env: admin password, SEMAPHORE_ACCESS_KEY_ENCRYPTION (head -c32 /dev/urandom | base64)
docker compose -f server/compose.yaml --env-file server/.env up -d
open http://localhost:3000
```

The image `semaphoreui/semaphore:v2.19.14` is pinned in `server/compose.yaml`. If it is not cached
locally, `docker compose up` pulls it from Docker Hub (network access).

## 2. Project

Create a project, for example "Robotont fleet". Everything below lives inside this project.

## 3. Key Store

| Name | Type | Content | Used for |
|---|---|---|---|
| `peko-ssh` | SSH key | the private key whose public half is in `~peko/.ssh/authorized_keys` on the robots (robotont-setup convention: `~/.ssh/robotont`) | inventory "user credentials" |
| `peko-sudo` | Login with password | login `peko`, peko's password | inventory "sudo credentials" (become) |
| `github` | SSH key, or none | only if `robotont/robotont-management` is private | repository access |

With `SEMAPHORE_ACCESS_KEY_ENCRYPTION` set, these are stored encrypted in the BoltDB volume.

## 4. Repository

- URL `https://github.com/robotont/robotont-management.git`, branch `main`, access key none (public repository) or `github`.
- Semaphore clones the repository on this machine: network access to GitHub.
- Local alternative without network: uncomment the bind mount in `server/compose.yaml`, restart
  the container, and use the path `/repositories/robotont-management` as the repository URL.

## 5. Inventory

- Type File, path `inventory/hosts.yaml`.
- User credentials `peko-ssh`, sudo credentials `peko-sudo`.
- `inventory/group_vars/` next to the file is picked up automatically.

## 6. Environment

Create the environment `robotont-secrets` with the extra variables the upstream playbooks need,
all kept out of git: `wifi_pass` (NUC hotspot password, 8 or more characters),
`wifi_hotspot_password`, `wifi_client_ssid`, `wifi_client_password` (Raspberry Pi: hotspot and
lab Wi-Fi).

## 7. Task templates

All templates use the repository, inventory and environment above. Enable "allow CLI args
override" (or the equivalent) on every template so a run can be limited to one robot with
`--limit robotont-1`.

| Template | Playbook | Notes |
|---|---|---|
| Test connection | `playbooks/test_connection.yml` | Run first. Verifies the submodule checkout, `community.general`, SSH login and sudo. |
| Health Check | `playbooks/healthcheck.yml` | Read-only, safe to repeat. |
| Provision Robotont | `playbooks/provision.yml` | 30 to 60 minutes, ends with a reboot. Run over Ethernet, first with `--limit`. Lite robots without camera: add `--skip-tags camera`. |
| Set up service | `playbooks/setup_service.yml` | Re-templates and enables `robotont.service`. |
| Restart services | `playbooks/restart_services.yml` | |
| Reboot | `playbooks/reboot.yml` | |

## 8. Submodules

The playbooks run the upstream code from the git submodule `external/robotont-setup`. Whether
Semaphore initialises submodules when it clones a repository has not been verified for v2.19.14.
"Test connection" fails with a clear message when the submodule is missing. Fallbacks:

- A. Add a first play that runs `git submodule update --init` in the checkout before the import
  (needs git in the image and GitHub access from the container).
- B. Use the bind-mounted local repository from section 4; the working tree already contains the submodule.

## 9. Checks after the first run

- The task log shows the repository's `ansible.cfg` being used. If not, add
  `ANSIBLE_CONFIG=ansible.cfg` to the environment.
- `community.general` is present in the image ("Test connection" checks it). If not, Semaphore
  installs `collections/requirements.yml` from Ansible Galaxy (network access).
