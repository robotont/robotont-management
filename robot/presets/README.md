# Presets

A preset is what runs on a robot: one directory here, deployed to `/opt/robotont/presets/`,
containing either `compose.yaml` (containers) or `run.sh` (a host process). Exactly one preset is
active at a time; it is recorded in `/etc/robotont/preset` and run by `robotont.service`.

| Preset | Contents | Use |
|---|---|---|
| `host` | `run.sh`: the host-installed ROS 2 workspace, no containers | migration bridge; default on adopted robots |
| `driver` | bringup container only | production default for the container runtime |
| `demo-example` | bringup plus an example node | template for `demo-<name>` presets |
| `test-talker` | one `ros2 topic pub` container, upstream image only | tests on a VM or without touching hardware |
| `student`, `student-hw` | Phase D3 | study room |

## Rules

- Names: `[a-z0-9-]`, at most 31 characters, at most 10 presets. These are the limits of the
  firmware's OLED menu (branch `v3.0-devel-jyrgen`), kept so that an OLED bridge can list them later.
- Every service `extends` one of the definitions in `_common/services.yaml`: `ros-app` (ROS, no
  hardware), `hardware` (may open devices), `driver`, `student`, `student-hw`.
- Every service declares the hardware it opens in the label `robotont.devices`, comma separated,
  from the vocabulary `mainboard`, `lidar`, `gamepad`, `realsense`, `camera`. `mainboard`, `lidar`,
  `realsense` and `camera` are exclusive: `robotont-preset check` refuses a preset in which two
  services claim one of them, and `robotont-metrics` reports claims and conflicts.
- Container names are fixed (`container_name: robotont-<service>`) so that two presets can never
  run two drivers; the compose project name is always `robotont` (set by `robotont-preset`).
- Do not add `ports:`; every ROS container uses `network_mode: host`.

## Commands on the robot

```
robotont-preset list             # presets available
robotont-preset current          # the active one
robotont-preset status           # active preset, service state, containers
robotont-preset check <name>     # validate before switching
robotont-preset switch <name>    # activate and restart robotont.service (peko may do this)
robotont-status                  # report from robotont-metrics (also inside containers)
journalctl -u robotont -f        # logs of the active preset
```

From Semaphore: task "Switch preset" with the survey variable `preset`, limited to one robot with
`--limit robotont-N`.
