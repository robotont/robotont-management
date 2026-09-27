#!/usr/bin/env python3
"""Semaphore bootstrap for the Robotont (standard library only).

Creates or updates, idempotently, from environment variables: the project, the key store
(robot SSH key, robot sudo password, a "none" key for the local repository), the repository,
the inventory, the environment with the Wi-Fi variables, and the task templates listed in
templates.json (templates not listed there are removed). Runs automatically from docker compose
(service "bootstrap") once Semaphore is healthy. It can also run a template and print its
output, for scripted tests:

  bootstrap.py                                   apply the configuration
  bootstrap.py run "3. Status"
  bootstrap.py run "1. Setup Ubuntu" --var robot_address=robotont-123.local --var robotont_id=123 \
                                     --var robot_type=3lite --var robotont_camera=false
  (--var key=value answers a dialog field or sets an extra variable)

templates.json entries: name, playbook, description, optional survey_vars in Semaphore's format
(name, title, description, type "" | int | enum | secret, required, default_value, values
[{name, value}]). The run dialog shows the survey fields only: no Limit, tags or CLI arguments.

Environment: SEMAPHORE_URL, SEMAPHORE_ADMIN, SEMAPHORE_ADMIN_PASSWORD, PROJECT_NAME, ROBOT_USER,
ROBOT_SSH_KEY_FILE (path inside the container), ROBOT_SUDO_PASSWORD, REPO_PATH, REPO_BRANCH,
INVENTORY_PATH, TEMPLATES_FILE, WIFI_PASS, WIFI_HOTSPOT_PASSWORD, WIFI_CLIENT_SSID,
WIFI_CLIENT_PASSWORD.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("SEMAPHORE_URL", "http://semaphore:3000").rstrip("/")
ADMIN = os.environ.get("SEMAPHORE_ADMIN", "admin")
ADMIN_PW = os.environ.get("SEMAPHORE_ADMIN_PASSWORD", "admin")
PROJECT = os.environ.get("PROJECT_NAME", "Robotont fleet")
ROBOT_USER = os.environ.get("ROBOT_USER", "peko")
SSH_KEY_FILE = os.environ.get("ROBOT_SSH_KEY_FILE_IN_CONTAINER", "/run/secrets/robot_ssh_key")
SUDO_PW = os.environ.get("ROBOT_SUDO_PASSWORD", "")
REPO_PATH = os.environ.get("REPO_PATH", "/repositories/robotont-management")
REPO_BRANCH = os.environ.get("REPO_BRANCH", "main")
INVENTORY_PATH = os.environ.get("INVENTORY_PATH", "inventory")
TEMPLATES_FILE = os.environ.get("TEMPLATES_FILE", os.path.join(os.path.dirname(__file__), "templates.json"))
EXTRA_VARS = {
    name: os.environ[var]
    for name, var in (("wifi_pass", "WIFI_PASS"), ("wifi_hotspot_password", "WIFI_HOTSPOT_PASSWORD"),
                      ("wifi_client_ssid", "WIFI_CLIENT_SSID"), ("wifi_client_password", "WIFI_CLIENT_PASSWORD"))
    if os.environ.get(var)
}

KEY_SSH, KEY_SUDO, KEY_NONE = f"{ROBOT_USER}-ssh", f"{ROBOT_USER}-sudo", "none"
REPO_NAME, INVENTORY_NAME, ENV_NAME = "robotont-management", "robots", "robotont-secrets"


class Api:
    def __init__(self, url):
        self.url = url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read().decode()
                try:
                    return r.status, (json.loads(raw) if raw.strip() else None)
                except json.JSONDecodeError:
                    return r.status, raw          # e.g. /api/ping answers plain "pong"
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")

    def must(self, method, path, body=None, ok=(200, 201, 204)):
        status, result = self.call(method, path, body)
        if status not in ok:
            sys.exit(f"bootstrap: {method} {path} -> HTTP {status}: {result}")
        return result


def wait_for_api(api, seconds=120):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if api.call("GET", "/api/ping")[0] == 200:
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    sys.exit(f"bootstrap: Semaphore at {URL} did not answer within {seconds} s")


def login(api):
    api.must("POST", "/api/auth/login", {"auth": ADMIN, "password": ADMIN_PW})


def by_name(items, name):
    return next((i for i in (items or []) if i.get("name") == name), None)


def ensure(api, kind, list_path, name, body, create_path=None, item_path=None):
    """Create or update the object called `name`. Returns its id."""
    existing = by_name(api.must("GET", list_path), name)
    if existing:
        path = (item_path or list_path) + f"/{existing['id']}"
        api.must("PUT", path, {**body, "id": existing["id"]})
        print(f"  {kind:<12} {name!r}: updated (id {existing['id']})")
        return existing["id"]
    created = api.must("POST", create_path or list_path, body)
    if not isinstance(created, dict) or "id" not in created:
        created = by_name(api.must("GET", list_path), name)
    print(f"  {kind:<12} {name!r}: created (id {created['id']})")
    return created["id"]


def configure(api):
    print(f"bootstrap: configuring {URL} as {ADMIN}")
    pid = ensure(api, "project", "/api/projects", PROJECT, {"name": PROJECT, "alert": False},
                 item_path="/api/project")
    keys = f"/api/project/{pid}/keys"

    ensure(api, "key", keys, KEY_NONE, {"name": KEY_NONE, "type": "none", "project_id": pid})
    ssh_key = None
    if os.path.exists(SSH_KEY_FILE):
        with open(SSH_KEY_FILE) as f:
            ssh_key = f.read()
        ssh_id = ensure(api, "key", keys, KEY_SSH, {
            "name": KEY_SSH, "type": "ssh", "project_id": pid, "override_secret": True,
            "ssh": {"login": ROBOT_USER, "passphrase": "", "private_key": ssh_key}})
    else:
        print(f"  key          {KEY_SSH!r}: skipped, {SSH_KEY_FILE} not mounted")
        ssh_id = None
    sudo_id = None
    if SUDO_PW:
        sudo_id = ensure(api, "key", keys, KEY_SUDO, {
            "name": KEY_SUDO, "type": "login_password", "project_id": pid, "override_secret": True,
            "login_password": {"login": "root", "password": SUDO_PW}})   # login = user to become
    else:
        print(f"  key          {KEY_SUDO!r}: skipped, ROBOT_SUDO_PASSWORD empty")
    none_id = by_name(api.must("GET", keys), KEY_NONE)["id"]

    repo_id = ensure(api, "repository", f"/api/project/{pid}/repositories", REPO_NAME, {
        "name": REPO_NAME, "project_id": pid, "git_url": REPO_PATH, "git_branch": REPO_BRANCH,
        "ssh_key_id": none_id})

    inv_body = {"name": INVENTORY_NAME, "project_id": pid, "type": "file", "inventory": INVENTORY_PATH,
                "repository_id": repo_id, "ssh_key_id": ssh_id or none_id}
    if sudo_id:
        inv_body["become_key_id"] = sudo_id
    inv_id = ensure(api, "inventory", f"/api/project/{pid}/inventory", INVENTORY_NAME, inv_body)

    env_id = ensure(api, "environment", f"/api/project/{pid}/environment", ENV_NAME, {
        "name": ENV_NAME, "project_id": pid, "json": json.dumps(EXTRA_VARS), "env": "{}"})
    print(f"  environment  variables: {', '.join(EXTRA_VARS) or 'none set'}")

    with open(TEMPLATES_FILE) as f:
        templates = json.load(f)
    for t in templates:
        ensure(api, "template", f"/api/project/{pid}/templates", t["name"], {
            "project_id": pid, "name": t["name"], "app": "ansible", "playbook": t["playbook"],
            "inventory_id": inv_id, "repository_id": repo_id, "environment_id": env_id,
            "arguments": "[]", "allow_override_args_in_task": False,
            "description": t.get("description", ""), "type": "",
            "survey_vars": t.get("survey_vars", []),
            "task_params": {
                "allow_debug": False, "allow_override_limit": False, "allow_override_tags": False,
                "allow_override_skip_tags": False, "allow_override_inventory": False,
                "allow_override_skip_galaxy_install": False, "limit": [], "tags": [], "skip_tags": []}})
    wanted = {t["name"] for t in templates}
    for existing in api.must("GET", f"/api/project/{pid}/templates"):
        if existing["name"] not in wanted:
            api.must("DELETE", f"/api/project/{pid}/templates/{existing['id']}")
            print(f"  template     {existing['name']!r}: removed (not in templates.json)")
    print("bootstrap: done")


def run_template(api, name, variables):
    """Start a template the way the run dialog does: the dialog answers go to `environment`."""
    pid = by_name(api.must("GET", "/api/projects"), PROJECT)["id"]
    template = by_name(api.must("GET", f"/api/project/{pid}/templates"), name)
    if not template:
        sys.exit(f"bootstrap: no template called {name!r}")
    body = {"template_id": template["id"], "environment": json.dumps(variables),
            "params": {"limit": [], "tags": [], "skip_tags": [], "debug": False, "dry_run": False, "diff": False}}
    task = api.must("POST", f"/api/project/{pid}/tasks", body)
    tid = task["id"]
    print(f"task {tid} ({name}) started")
    status = None
    while status not in ("success", "error", "stopped"):
        time.sleep(3)
        status = api.must("GET", f"/api/project/{pid}/tasks/{tid}")["status"]
    for line in api.must("GET", f"/api/project/{pid}/tasks/{tid}/output") or []:
        print(line.get("output", ""))
    print(f"task {tid} finished: {status}")
    sys.exit(0 if status == "success" else 1)


def main(argv):
    api = Api(URL)
    wait_for_api(api)
    login(api)
    if argv[:1] == ["run"]:
        usage = "usage: bootstrap.py run <template> [--var key=value ...]"
        name = argv[1] if len(argv) > 1 else sys.exit(usage)
        rest, variables = argv[2:], {}
        while rest:
            if rest[0] != "--var" or len(rest) < 2 or "=" not in rest[1]:
                sys.exit(usage)
            key, value = rest[1].split("=", 1)
            variables[key] = value
            rest = rest[2:]
        run_template(api, name, variables)
    else:
        configure(api)


if __name__ == "__main__":
    main(sys.argv[1:])
