#!/bin/bash
# Static checks of this repository: run locally before a commit, and by .github/workflows/checks.yml.
# Each step prints PASS, FAIL or SKIP (tool not installed); the exit status is 1 when any step failed.
#   scripts/check.sh            # from anywhere; needs: ansible-playbook, yamllint, ansible-lint,
#                               # shellcheck (or docker), python3, docker compose, docker (promtool)
set -u
cd "$(dirname "$0")/.." || exit 1
failed=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; failed=1; }
skip() { printf 'SKIP  %s (%s)\n' "$1" "$2"; }
have() { command -v "$1" > /dev/null 2>&1; }
run() {  # run <name> <command...>: PASS/FAIL on the exit status, output only on failure
  local name="$1"; shift
  local out
  if out=$("$@" 2>&1); then pass "$name"; else fail "$name"; printf '%s\n' "$out" | sed 's/^/      /'; fi
}

# 1. Playbook syntax (the extra vars each playbook asserts on; setup_ros needs the submodules)
if have ansible-playbook; then
  vars=(-e robot_address=robotont-1.local -e robotont_id=1 -e robot_type=3lite -e robotont_camera=false
        -e image=hello-world -e workspace=driver -e network=192.168.1.0/24 -e wifi_hotspot_password=12345678
        -e wifi_client_ssid=lab -e wifi_client_password=12345678 -e wifi_pass=12345678)
  for pb in playbooks/*.yml; do
    if [ "$pb" = playbooks/setup_ros.yml ] && [ ! -f external/robotont-setup-rpi/ansible/robots.yaml ]; then
      skip "syntax $pb" "submodules not checked out"; continue
    fi
    run "syntax $pb" ansible-playbook --syntax-check "$pb" "${vars[@]}"
  done
else
  skip "playbook syntax" "ansible-playbook not installed"
fi

# 2. yamllint (configuration in .yamllint)
if have yamllint; then
  run "yamllint" yamllint -s playbooks roles inventory server robot/workspaces .github .yamllint .ansible-lint
else
  skip "yamllint" "not installed"
fi

# 3. ansible-lint (configuration in .ansible-lint)
if have ansible-lint; then
  run "ansible-lint" ansible-lint --offline playbooks roles
else
  skip "ansible-lint" "not installed"
fi

# 4. shellcheck: the binary, or the koalaman/shellcheck image
shell_files=(scripts/*.sh robot/bin/robotont-workspace robot/bin/robotont-status robot/workspaces/host/run.sh)
if have shellcheck; then
  run "shellcheck" shellcheck "${shell_files[@]}"
elif have docker; then
  run "shellcheck (docker)" docker run --rm -v "$PWD:/mnt:ro" koalaman/shellcheck:stable "${shell_files[@]}"
else
  skip "shellcheck" "neither shellcheck nor docker installed"
fi

# 5. Python: compile only (the scripts are standard-library only)
run "py_compile" python3 -m py_compile server/bootstrap.py scripts/*.py robot/bin/robotont-metrics

# 6. JSON files (Semaphore templates, Grafana dashboards)
run "json" python3 -c 'import json,sys
for f in sys.argv[1:]: json.load(open(f))' server/templates.json server/grafana/dashboards/*.json

# 7. docker compose config with a throwaway .env (the real one is gitignored and may not exist)
if have docker && docker compose version > /dev/null 2>&1; then
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  : > "$tmpdir/key"
  sed "s|^ROBOT_SSH_KEY_FILE=.*|ROBOT_SSH_KEY_FILE=$tmpdir/key|" server/.env.example > "$tmpdir/.env"
  run "compose config" docker compose --env-file "$tmpdir/.env" -f server/compose.yaml config -q
  # 8. promtool from the Prometheus image pinned in the compose file
  prom_image=$(sed -n 's/^ *image: *\(prom\/prometheus:[^ ]*\).*/\1/p' server/compose.yaml | head -1)
  run "promtool config" docker run --rm -v "$PWD/server/prometheus:/etc/prometheus:ro" --entrypoint promtool \
      "$prom_image" check config /etc/prometheus/prometheus.yml
  run "promtool rules" docker run --rm -v "$PWD/server/prometheus:/etc/prometheus:ro" --entrypoint promtool \
      "$prom_image" check rules /etc/prometheus/rules.yml
else
  skip "compose config, promtool" "docker compose not available"
fi

# 9. Line endings: no CR in tracked text files (.gitattributes enforces LF)
if crlf=$(git grep -Il $'\r' -- . ':!external' 2>/dev/null) && [ -n "$crlf" ]; then
  fail "line endings"; printf '%s\n' "$crlf" | sed 's/^/      CRLF: /'
else
  pass "line endings"
fi

[ "$failed" -eq 0 ] && echo "all checks passed" || echo "some checks FAILED"
exit $failed
