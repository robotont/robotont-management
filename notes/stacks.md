# Stacks

A stack is what runs on a robot: one directory here, deployed to `/srv/robotont/stacks/`
by "2. Deploy", containing either `compose.yaml` (containers) or `run.sh` (a host process).
Exactly one stack is active at a time; it is recorded in `/etc/robotont/stack` and run by
`robotont.service`. "3. Switch stack" in Semaphore lists the directories found here.

| Stack | Contents | Use |
|---|---|---|
| `driver` | bringup container only | default on every robot |
| `demo-example` | bringup plus an example node | template for demo stacks (`university-celebration-day-demo-2026`) |
| `test-talker` | one `ros2 topic pub` container, upstream image only | tests on a VM or without touching hardware |
| `host` | `run.sh`: ROS installed on the host, no containers | legacy; only on robots set up by "Setup ROS (legacy)" |
| `student`, `student-hw` | Phase D3 | study room |

## Rules

- Names: `[a-z0-9-]`, up to 63 characters (compose project rules). Directories starting with `_`
  are not stacks.
- Every service `extends` one of the definitions in `_common/services.yaml`: `ros-app` (ROS, no
  hardware), `hardware` (may open devices), `driver`, `student`, `student-hw`.
- Images are referenced by name and tag (`${ROBOTONT_IMAGE_REPO}/robotont-ros:${ROBOTONT_RELEASE}`
  or any public image). CI builds the images defined in `../images/`; "2. Deploy" pulls whatever
  the stacks reference.
- Every service declares the hardware it opens in the label `robotont.devices`, comma separated,
  from the vocabulary `mainboard`, `lidar`, `gamepad`, `realsense`, `camera`. `mainboard`, `lidar`,
  `realsense` and `camera` are exclusive: `robotont-stack check` refuses a stack in which
  two services claim one of them, and `robotont-metrics` reports claims and conflicts.
- Container names are fixed (`container_name: robotont-<service>`) so that two stacks can
  never run two drivers; the compose project name is always `robotont` (set by `robotont-stack`).
- Do not add `ports:`; every ROS container uses `network_mode: host`.

## Adding one

Copy `demo-example` to `<name>`, edit the services, declare `robotont.devices`, add a `README.md`
that says what it shows and what runs on a laptop. Validate on your machine, commit, then
"2. Deploy" on the robot and "3. Switch stack":

```
docker compose -p robotont --env-file ../../test/robotont.env -f <name>/compose.yaml config
ROBOTONT_ROOT=../ ROBOTONT_ENV_FILE=../../test/robotont.env ../bin/robotont-stack check <name>
docker compose -f ../../server/compose.yaml up -d      # refreshes the dropdown in Semaphore
```

## Generated from an image

"4. Run image" in Semaphore writes a one-service stack into `/srv/robotont/stacks/<name>/`
on the robot (not here): the given image, `container_name: robotont-<name>`, extending `ros-app`
or, with hardware access, `hardware` (devices `mainboard,lidar,gamepad`), optional `command`,
label `robotont.source: "4. Run image"`. The rules above apply to it; the name may not be one of
the directories here. Deploy keeps such directories and pulls their images; remove one with
`sudo rm -r /srv/robotont/stacks/<name>`. Template:
`roles/robotont_stacks/templates/image-stack.compose.yaml.j2`.

## Commands on the robot

```
robotont-stack list             # stacks available
robotont-stack current          # the active one
robotont-stack status           # active stack, service state, containers
robotont-stack check <name>     # validate before switching
robotont-stack switch <name>    # activate and restart robotont.service (peko may do this)
robotont-stack pull [name]      # pull the images of every stack, or of one
robotont-status                     # report from robotont-metrics (also inside containers)
journalctl -u robotont -f           # logs of the active stack
```
