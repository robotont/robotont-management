#!/bin/bash
# Preset "host": the host-installed ROS 2 workspace, no containers. Migration bridge that keeps a
# robot provisioned by robotont-setup running as before, without the `bash -ic` dependency.
# Environment comes from /etc/robotont/robotont.env through robotont.service.
# No -u: the ROS setup scripts reference variables that may be unset (AMENT_TRACE_SETUP_FILES).
set -eo pipefail
# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
WS="${ROBOTONT_HOST_WS:-$HOME/ros2_ws}"
if [ -f "$WS/install/setup.bash" ]; then
  # shellcheck disable=SC1091
  source "$WS/install/setup.bash"
else
  echo "robotont-preset host: workspace $WS is not built (no install/setup.bash)" >&2
  exit 1
fi
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
# shellcheck disable=SC2086
exec ros2 launch robotont_support robotont_bringup.launch.py ${ROBOTONT_BRINGUP_ARGS:-}
