# Monitoring: node_exporter, Prometheus, Grafana

Milestone 3 of [05](05-implementation-plan.md), implemented 2026-11-04. Every robot runs
node_exporter; the Prometheus and Grafana next to Semaphore in `server/compose.yaml` scrape the
enrolled robots and show one dashboard. Nothing is sent anywhere: alerts are visible, not
delivered (later step). `playbooks/status.yml` stays the command-line report.

## What runs where

| Where | What | Installed by |
|---|---|---|
| robot | `prometheus-node-exporter` (Ubuntu package, `:9100`, all interfaces; the firewall is off for DDS anyway) with the textfile collector on `/var/lib/prometheus/node-exporter` | `roles/monitoring`, part of "1. Setup Ubuntu" (re-run it on robots set up before 2026-11-04) |
| robot | `robotont-metrics.timer` writes `robotont.prom` (workspace, release, service, containers, devices) every 15 s into that directory | "2. Deploy" ([07](07-container-runtime.md), Monitoring hooks) |
| server | Prometheus `prom/prometheus:v3.15.1`, port `9090`, 30 days retention, config `server/prometheus/prometheus.yml`, rules `server/prometheus/rules.yml` | `docker compose -f server/compose.yaml up -d` |
| server | Grafana `grafana/grafana:13.2.5`, port `3001`, `admin` / `admin`, anonymous viewers allowed; datasource and dashboard provisioned from `server/grafana/` | same |

All three servers bind to `SEMAPHORE_BIND` (`127.0.0.1` by default; `0.0.0.0` in `server/.env`
to serve the lab network).

## The robots Prometheus scrapes come from the inventory

`scripts/prometheus_targets.py` reads `inventory/robots/*.yaml` (one file per enrolled robot) and
writes `server/prometheus/targets/robots.json` (gitignored) for Prometheus `file_sd_configs`,
with the labels `robot` (`robotont-N`), `robotont_id` and `generation` (`3` or `3lite`). It
runs at the end of "1. Setup Ubuntu" (inside the Semaphore container, repository mounted) and
in the bootstrap on every `up -d`; Prometheus re-reads the file within 30 s. So:

- a new robot is scraped a minute after its enrolment, no restart needed;
- a robot removed by deleting its enrolment file disappears at the next `up -d` (or run the
  script by hand: `python3 scripts/prometheus_targets.py`);
- the address is the enrolment address (`ansible_host`), so the same `.local` versus IP rule as
  for Semaphore applies: on a Linux host the container cannot resolve `.local`, enrol with the IP.

## The dashboard "Robotont fleet"

`server/grafana/dashboards/robotont-fleet.json`, the Grafana home page. Top: robots up and down,
alerts firing, devices claimed but absent, containers running. Then the fleet table, one row per
robot: up, workspace, release, service active, containers, devices present and missing,
container restarts, uptime, CPU temperature. Then the alerts firing. Below, one row per robot
(variable `Robot`, all by default): workspace, release, service, uptime, mainboard and lidar
present, CPU, memory, root disk, temperature, container restarts, network. Everything comes from
`up`, `node_*` and the `robotont_*` metrics of [07](07-container-runtime.md); no new metric was
added. Edit it in Grafana as admin, then export the JSON back into the repository (provisioned
dashboards are not saved from the UI).

## Alerts (`server/prometheus/rules.yml`)

| Alert | Fires when | Severity |
|---|---|---|
| `RobotDown` | `up{job="robots"} == 0` for 2 min (off, no network, node_exporter stopped) | warning |
| `RobotontServiceInactive` | `robotont_service_active == 0` for 2 min | warning |
| `RobotontDeviceMissing` | a container of the active workspace claims a device (`robotont_container_device`) that is not enumerated (`robotont_device_present == 0`) for 1 min | info |
| `RobotontDeviceConflict` | two running containers claim an exclusive device | warning |

Seen in Prometheus (`/alerts`) and in the dashboard's alert table. Alertmanager and
notifications are a later step. On a bench robot without mainboard and lidar,
`RobotontDeviceMissing` fires for the `driver` workspace, which is the intended signal.

## Checks

```
curl -s http://<robot>:9100/metrics | grep robotont_        # node_exporter and the textfile
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {robot: .labels.robot, health}'
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {alertname: .labels.alertname, state}'
open http://localhost:3001                                   # the dashboard (anonymous viewer)
```

Bench note (Linux laptop with the robot on a shared Ethernet port): Prometheus scrapes from the
compose network, so the same firewall rule as for Semaphore applies ("Linux host" in
[semaphore-setup.md](semaphore-setup.md)); a target `down` with "connection refused" right after
a robot reboot is that rule, not the robot.

## Not done

Alert delivery (Alertmanager), Docker daemon metrics (`127.0.0.1:9323` on the robots, not
scraped), retention beyond 30 days or remote storage, Grafana users beyond admin and anonymous
viewer, verification on a NUC (same role, different temperature sensor names: the table shows
`node_thermal_zone_temp` and falls back to `node_hwmon_temp_celsius`).
