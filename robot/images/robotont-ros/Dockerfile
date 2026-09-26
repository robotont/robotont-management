# Robotont ROS 2 runtime image: ROS 2 Jazzy (ros-base) plus the Robotont packages of one release.
# Build context: this directory. The release file comes from the named build context "releases"
# (robot/releases in the repository, /opt/robotont/releases on a robot); see compose.build.yaml.
#
# Single stage on purpose: one maintainer, one file. A builder/runtime split is a later size
# optimisation.
ARG BASE_IMAGE=ros:jazzy-ros-base
FROM ${BASE_IMAGE}

ARG RELEASE
ARG ROSDEP_SKIP_KEYS="rviz2 camera_ros"
ENV ROBOTONT_RELEASE=${RELEASE} \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/robotont/ws
COPY --from=releases ${RELEASE}.repos /opt/robotont/release.repos

# 1. sources of the release, 2. their dependencies via rosdep (GUI and RPi-only keys skipped),
# 3. packages the bringup launches but nobody declares (RealSense, depth to laserscan, joystick),
# 4. build into a merged install space outside the workspace.
RUN mkdir -p src \
 && vcs import --input /opt/robotont/release.repos src \
 && apt-get update \
 && rosdep update --rosdistro "${ROS_DISTRO}" \
 && rosdep install --from-paths src --ignore-src -y --rosdistro "${ROS_DISTRO}" \
      --skip-keys "${ROSDEP_SKIP_KEYS}" \
 && apt-get install -y --no-install-recommends \
      ros-${ROS_DISTRO}-realsense2-camera \
      ros-${ROS_DISTRO}-depthimage-to-laserscan \
      ros-${ROS_DISTRO}-joy \
      ros-${ROS_DISTRO}-teleop-twist-joy \
      ros-${ROS_DISTRO}-demo-nodes-cpp \
 && . /opt/ros/${ROS_DISTRO}/setup.sh \
 && colcon build --merge-install --install-base /opt/robotont/install \
      --cmake-args -DCMAKE_BUILD_TYPE=Release \
 && rm -rf build log /var/lib/apt/lists/*

COPY entrypoint.sh /robotont_entrypoint.sh
RUN chmod 0755 /robotont_entrypoint.sh

LABEL robotont.release=${RELEASE} \
      org.opencontainers.image.source=https://github.com/robotont/robotont-management \
      org.opencontainers.image.description="Robotont ROS 2 runtime (release ${RELEASE})"

ENTRYPOINT ["/robotont_entrypoint.sh"]
CMD ["bash"]
