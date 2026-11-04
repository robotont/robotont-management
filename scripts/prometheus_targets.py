#!/usr/bin/env python3
"""Render the Prometheus scrape targets from the inventory.

Reads inventory/robots/*.yaml (one file per enrolled robot, written by "1. Setup Ubuntu") and
writes server/prometheus/targets/robots.json for Prometheus file_sd_configs, so the inventory
stays the only list of robots. Run by the Semaphore bootstrap on every `up -d` and at the end of
"1. Setup Ubuntu". Standard library only; prints "changed" or "unchanged".

    prometheus_targets.py                 # paths relative to the repository this file is in
    prometheus_targets.py --print         # also print the JSON
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROBOTS_DIR = os.path.join(ROOT, "inventory", "robots")
TARGETS_FILE = os.path.join(ROOT, "server", "prometheus", "targets", "robots.json")
PORT = 9100
GENERATION = {"robotont_rpi": "3lite", "robotont_nuc": "3"}


def parse_robot_file(path):
    """The enrolment files have a fixed shape (group, hosts, one host with its variables)."""
    group = host = None
    variables = {}
    with open(path) as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            key, _, value = line.strip().partition(":")
            value = value.strip()
            if indent == 0 and key != "hosts":
                group = key
            elif indent == 4 and value == "":
                host = key
            elif indent >= 6 and value != "":
                variables[key] = value.strip("'\"")
    if not (group and host and variables.get("ansible_host")):
        raise ValueError(f"{path}: not an enrolment file (group, host and ansible_host expected)")
    return group, host, variables


def main(argv):
    targets = []
    for path in sorted(glob.glob(os.path.join(ROBOTS_DIR, "*.yaml"))):
        group, host, variables = parse_robot_file(path)
        address = variables["ansible_host"]
        targets.append({
            "targets": [f"{address}:{PORT}"],
            "labels": {
                "robot": host,
                "robotont_id": str(variables.get("robotont_id", re.sub(r"^robotont-", "", host))),
                "generation": GENERATION.get(group, group),
            },
        })
    content = json.dumps(targets, indent=2) + "\n"
    os.makedirs(os.path.dirname(TARGETS_FILE), exist_ok=True)
    try:
        with open(TARGETS_FILE) as f:
            unchanged = f.read() == content
    except OSError:
        unchanged = False
    if not unchanged:
        tmp = TARGETS_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, TARGETS_FILE)
    print(f"prometheus targets: {len(targets)} robot(s), {'unchanged' if unchanged else 'changed'} ({TARGETS_FILE})")
    if "--print" in argv:
        print(content, end="")


if __name__ == "__main__":
    main(sys.argv[1:])
