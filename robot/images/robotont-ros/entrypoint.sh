#!/bin/bash
# Source ROS 2 and the Robotont install space, then run the command.
set -e
# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f /opt/robotont/install/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/robotont/install/setup.bash
fi
exec "$@"
