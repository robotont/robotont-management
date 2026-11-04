# Host setup: what your machine needs

The management host is any laptop or server on the same network as the robots: Windows, macOS
or Linux. Semaphore runs in Docker and brings its own Ansible, so the host needs only Docker,
git and a way to reach the robots by name or address. Written 2026-11-04 from the macOS
(2026-09), Windows/WSL (2026-11-01) and Ubuntu laptop (2026-11-04) setups.

## 1. What every host needs

| Need | Why | Check |
|---|---|---|
| Docker with Compose v2 | Semaphore and its bootstrap run as containers | `docker compose version` |
| git with submodules | the repository, including `external/` (legacy playbooks) | `git submodule status` shows no `-` prefix |
| an SSH client | `ssh-copy-id` to a fresh robot, troubleshooting | `ssh -V` |
| `.local` name resolution, or the robot's IP | "1. Setup Ubuntu" takes a name or an IP | `ping robotont-123.local` |

Nothing else. Ansible on the host is optional (only for `playbooks/status.yml` and running
playbooks from a terminal; `ansible-core` 2.16 or newer).

```
git clone --recurse-submodules https://github.com/robotont/robotont-management.git
cd robotont-management
cp server/.env.example server/.env        # key path, sudo password, Wi-Fi values
docker compose -f server/compose.yaml up -d
```

Then [semaphore-setup.md](semaphore-setup.md); the same `up -d` also starts Prometheus (`:9090`) and
Grafana (`:3001`), see [10-monitoring.md](10-monitoring.md). The SSH key named in `server/.env` is the one
whose public half goes onto every robot (Raspberry Pi Imager, or `ssh-copy-id`).

## 2. Per operating system

### Windows 10 or 11

- Docker Desktop with the WSL 2 backend. Clone the repository inside the WSL distribution
  (`~/robotont-management`, not under `/mnt/c`) and run `docker compose` from the WSL shell:
  a clone on the Windows filesystem gets CRLF line endings and slow bind mounts. Enable WSL
  integration for that distribution in Docker Desktop settings.
- SSH key: generate it inside WSL (`ssh-keygen -t ed25519`) and point `ROBOT_SSH_KEY_FILE` at the
  WSL path (`/home/<you>/.ssh/id_ed25519`).
- `.local` names: Windows resolves them natively (mDNS, since Windows 10 1803), so `ping
  robotont-123.local` works in PowerShell. Whether the Semaphore container resolves them through
  Docker Desktop is **not verified yet**; if "1. Setup Ubuntu" cannot reach the name, use
  "0. Find robots" and the IP.
- A cable straight into the laptop: Windows "Internet Connection Sharing" on the Ethernet
  adapter gives the robot an address and internet.

### macOS

- Docker Desktop. Clone anywhere in your home directory.
- `.local` names resolve on the host (Bonjour) and inside the Semaphore container, since Docker
  Desktop forwards DNS to the macOS resolver (verified 2026-09-27).
- A cable straight into the laptop: System Settings, Sharing, Internet Sharing from Wi-Fi to the
  Ethernet adapter.

### Linux (Docker Engine)

- Docker Engine with the Compose plugin from Docker's repository; your user in the `docker` group.
- The Semaphore image runs as uid 1001 and writes the enrolment files into the bind-mounted
  repository, and its bootstrap reads your `0600` SSH key: both handled by the compose file plus
  one ACL command, see "Linux host" in [semaphore-setup.md](semaphore-setup.md).
- `.local` names on the host need `avahi-daemon` and `libnss-mdns` (Ubuntu Desktop has them;
  a server install: `sudo apt install avahi-daemon libnss-mdns`). The Semaphore container
  cannot resolve them on Linux: give "1. Setup Ubuntu" the IP, found with "0. Find robots".
- A cable straight into the laptop: NetworkManager, wired connection, IPv4 method "Shared to
  other computers". The container then needs one firewall rule per session (semaphore-setup.md).

## 3. The network between host and robots

- Same network, reachable directly: the lab Wi-Fi or a router with DHCP is the normal case; a
  cable into the host with connection sharing is the bench case. Both give the robot internet,
  which "1. Setup Ubuntu" (packages) and "2. Deploy" (3.9 GB image pull) need.
- A phone hotspot does not work as the shared network: it isolates its clients from each other,
  so the host never reaches the robot although both are connected (seen 2026-11-04).
- The robot's **first boot must have internet**: Raspberry Pi Imager installs `avahi-daemon`
  through cloud-init at first boot and never retries. A card booted first without a network
  never answers `robotont-N.local` until "1. Setup Ubuntu" has run over its IP.
- When a name fails for any reason: "0. Find robots" with the network as CIDR (`ip addr`,
  `ifconfig` or `ipconfig` shows yours) lists every `robotont-N` with its address.
- Later, with Tailscale between the host and the robots, names come from MagicDNS and none of
  the mDNS points above matter.

## 4. Checklist before the first robot

```
docker compose version                       # Compose v2
git submodule status                         # two submodules, no "-" prefix
docker compose -f server/compose.yaml up -d  # Semaphore healthy, bootstrap "done"
docker logs robotont-semaphore-bootstrap     # project, keys, inventory, templates created
ping robotont-123.local                      # or "0. Find robots" from Semaphore
```
