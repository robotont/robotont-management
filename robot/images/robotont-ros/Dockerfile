# Robotont ROS 2 runtime image: ROS 2 Jazzy (ros-base) plus the Robotont packages of one release.
# Build context: this directory. The release file comes from the named build context "releases"
# (robot/releases in the repository, /srv/robotont/releases on a robot); see compose.build.yaml.
#
# Two layers on purpose. The apt dependencies of the release (large, change rarely) are installed
# from a list the "sources" stage derives with rosdep, so the layer is cached across releases as
# long as the list is unchanged. The sources and the built install space (small, change with
# every release) come last. A release bump therefore pushes and pulls only the last layer.
ARG BASE_IMAGE=ros:jazzy-ros-base

# --- stage 1: sources of the release and the apt packages they need -------------------------
FROM ${BASE_IMAGE} AS sources
ARG RELEASE
ARG ROSDEP_SKIP_KEYS="rviz2 camera_ros"
WORKDIR /opt/robotont/ws
COPY --from=releases ${RELEASE}.repos /opt/robotont/release.repos
RUN mkdir -p src \
 && vcs import --input /opt/robotont/release.repos src \
 && apt-get update \
 && rosdep update --rosdistro "${ROS_DISTRO}" \
 && rosdep install --from-paths src --ignore-src --rosdistro "${ROS_DISTRO}" \
      --skip-keys "${ROSDEP_SKIP_KEYS}" --simulate \
    | grep -E 'apt-get install' | awk '{print $NF}' | sort -u > /opt/robotont/deps.txt \
 && rm -rf /var/lib/apt/lists/*

# --- stage 2: the runtime image ---------------------------------------------------------------
FROM ${BASE_IMAGE}
ARG RELEASE
ENV ROBOTONT_RELEASE=${RELEASE} \
    DEBIAN_FRONTEND=noninteractive

# Dependencies of the release (from stage 1) plus packages the bringup launches but nobody
# declares (RealSense, depth to laserscan, joystick, demo nodes).
COPY --from=sources /opt/robotont/deps.txt /opt/robotont/deps.txt
RUN apt-get update \
 && xargs -a /opt/robotont/deps.txt apt-get install -y --no-install-recommends \
      ros-${ROS_DISTRO}-realsense2-camera \
      ros-${ROS_DISTRO}-depthimage-to-laserscan \
      ros-${ROS_DISTRO}-joy \
      ros-${ROS_DISTRO}-teleop-twist-joy \
      ros-${ROS_DISTRO}-demo-nodes-cpp \
 && rm -rf /var/lib/apt/lists/*

# The release itself: sources and a merged install space outside the workspace.
WORKDIR /opt/robotont/ws
COPY --from=sources /opt/robotont/release.repos /opt/robotont/release.repos
COPY --from=sources /opt/robotont/ws/src src
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
 && colcon build --merge-install --install-base /opt/robotont/install \
      --cmake-args -DCMAKE_BUILD_TYPE=Release \
 && rm -rf build log

COPY entrypoint.sh /robotont_entrypoint.sh
RUN chmod 0755 /robotont_entrypoint.sh

LABEL robotont.release=${RELEASE} \
      org.opencontainers.image.source=https://github.com/robotont/robotont-management \
      org.opencontainers.image.description="Robotont ROS 2 runtime (release ${RELEASE})"

ENTRYPOINT ["/robotont_entrypoint.sh"]
CMD ["bash"]
