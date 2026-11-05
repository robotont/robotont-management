# Building an image for a Robotont

This is for the maintainer of a ROS 2 package that should run on the Robotont robots, for
example [robotont_web_bridge](https://github.com/t6niskoppel/robotont_web_bridge). The robots
run containers, not packages: your repository publishes a container image, and the robot pulls
it. Nothing is pushed to your repository from our side.

You add four files to your repository, once. GitHub builds the image on every push and publishes
it to the GitHub Container Registry. We then run it on a robot with the job "4. Run image".

## 1. `Dockerfile` in the repository root

Builds your package on top of ROS 2 Jazzy. `robotont_msgs` is not an apt package, so it is built
from source next to yours. Change the branch if your package needs another one.

```dockerfile
FROM ros:jazzy-ros-base
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /ws

# robotont_msgs is not released as an apt package: build it from source next to this package.
RUN git clone --depth 1 --branch jazzy https://github.com/robotont/robotont_msgs.git src/robotont_msgs
COPY . src/robotont_web_bridge

# Everything package.xml declares, plus ttyd (the browser terminal, not a ROS package).
RUN apt-get update \
 && rosdep update --rosdistro "$ROS_DISTRO" \
 && rosdep install --from-paths src --ignore-src -y --rosdistro "$ROS_DISTRO" --skip-keys ament_python \
 && apt-get install -y --no-install-recommends ttyd \
 && rm -rf /var/lib/apt/lists/*

RUN . /opt/ros/$ROS_DISTRO/setup.sh \
 && colcon build --merge-install \
 && rm -rf build log

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "robotont_web_bridge", "web.launch.py"]
```

The last line is what the container runs by default. Keep it a launch file or a node that stays
in the foreground; when it exits, the container stops.

## 2. `docker/entrypoint.sh`

Sources ROS 2 and your workspace before every command, so `ros2 launch` and `ros2 run` work
without a shell.

```bash
#!/bin/bash
# Source ROS 2 and this workspace, then run the command.
set -e
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source /ws/install/setup.bash
exec "$@"
```

## 3. `.dockerignore`

Keeps a local build out of the image.

```
build
install
log
```

## 4. `.github/workflows/image.yml`

Builds the image for the Intel robots (amd64) and the Raspberry Pi robots (arm64) and publishes
it as `ghcr.io/<your user>/robotont_web_bridge:jazzy`. No secret to configure: the workflow
uses the token GitHub gives it.

```yaml
name: image

on:
  push:
    branches: [jazzy]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  image:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/robotont_web_bridge:jazzy
            ghcr.io/${{ github.repository_owner }}/robotont_web_bridge:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          labels: |
            org.opencontainers.image.source=https://github.com/${{ github.repository }}
```

## After the first run

1. On GitHub, open your profile, Packages, `robotont_web_bridge`, Package settings, and change
   the visibility to public. Without this the robots cannot pull the image. Once is enough.
2. Tell us the image name, for example `ghcr.io/t6niskoppel/robotont_web_bridge:jazzy`.

Every later push to `jazzy` updates the image. The robot takes the new version the next time
the image is run.

## Try it on your computer

```bash
docker build -t robotont_web_bridge .
docker run --rm --network host robotont_web_bridge
```

The second command starts the launch file; rosbridge answers on port 9090.

## How it runs on a robot

"4. Run image" starts the image on one robot with the robot's settings: host network, so DDS
discovery and your ports (9090, 8080, 7681) work as on the host; `ROS_DOMAIN_ID` of that robot;
UDP-only DDS transport. The Command field can replace the default command, for example
`ros2 launch robotont_web_bridge web.launch.py namespace:=rt54`. Hardware access is off unless
asked for; the bridge does not need it, the driver container owns the devices.
