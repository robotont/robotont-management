#!/bin/sh
# Apply the patches under patches/<submodule>/ to the submodule checkouts, idempotently.
# Run from any directory; safe to repeat. The Semaphore bootstrap runs it on every `up -d`, and
# "Setup ROS (legacy)" repeats it at run time; run it yourself after a fresh clone before using
# the legacy playbook from a terminal:  scripts/apply_patches.sh
#
# Why at bootstrap time: playbooks/setup_ros.yml imports the upstream playbooks statically, so
# their role files are parsed when the playbook loads, before any play (including the patch play)
# runs. A fresh checkout therefore ran unpatched once (seen 2026-11-04, docs/06 test log).
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
status=0
for dir in "$root"/patches/*/; do
  [ -d "$dir" ] || continue
  sub="$root/external/$(basename "$dir")"
  if [ ! -d "$sub/.git" ] && [ ! -f "$sub/.git" ]; then
    echo "apply_patches: $sub is not a git checkout (git submodule update --init?)" >&2; status=1; continue
  fi
  for patch in "$dir"*.patch; do
    [ -f "$patch" ] || continue
    if git -c safe.directory='*' -C "$sub" apply --check --reverse "$patch" >/dev/null 2>&1; then
      echo "apply_patches: $(basename "$patch") already applied"
    elif git -c safe.directory='*' -C "$sub" apply "$patch"; then
      echo "apply_patches: $(basename "$patch") applied"
    else
      echo "apply_patches: $(basename "$patch") FAILED to apply" >&2; status=1
    fi
  done
done
exit $status
