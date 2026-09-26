# robotont-student image (Phase D3, not built yet)

Planned content (docs/07-container-runtime.md, section "Student environment"): `FROM
robotont-ros:<release>`, `ros-dev-tools`, git, vim, nano, tmux, htop, gdb, `openssh-server` on
port 2222 (`AllowUsers peko`, `PermitRootLogin no`), user `peko` with uid 1000 (the image's
`ubuntu` uid-1000 user removed first) and passwordless sudo inside the container, rosdep cache in
`/etc/skel/.ros`, colcon defaults limiting parallel workers, prompt marker `(student)` via
`/etc/debian_chroot`, ROS sourced from `/etc/profile.d` and `/etc/bash.bashrc`, an entrypoint that
seeds the home from `/etc/skel`, sets the password from `STUDENT_PASSWORD` and exports
`ROS_DOMAIN_ID` into `/etc/robotont/env.sh` for sshd sessions.
