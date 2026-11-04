#!/usr/bin/env python3
"""Print the addresses of a network that accept a TCP connection on port 22, one per line.

Used by playbooks/find_robots.yml ("0. Find robots") as the fallback when robotont-N.local does
not resolve: plain TCP works from any host and from inside the Semaphore container, where mDNS
does not. Standard library only (runs inside the Semaphore image).

    find_robots.py 192.168.1.0/24          # at most /22 (1024 addresses), about 2 s per /24
"""
import ipaddress
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

PORT = 22
TIMEOUT = 0.7       # seconds per address; a silent address costs this once
MAX_ADDRESSES = 1024
THREADS = 64


def ssh_open(address):
    try:
        with socket.create_connection((str(address), PORT), timeout=TIMEOUT):
            return True
    except OSError:
        return False


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: find_robots.py <network, for example 192.168.1.0/24>")
    try:
        network = ipaddress.ip_network(argv[1], strict=False)
    except ValueError as err:
        sys.exit(f"not a network: {argv[1]} ({err})")
    if network.num_addresses > MAX_ADDRESSES:
        sys.exit(f"{network} has {network.num_addresses} addresses; use /22 or smaller")
    hosts = list(network.hosts()) or [network.network_address]
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        for address, is_open in zip(hosts, pool.map(ssh_open, hosts)):
            if is_open:
                print(address)


if __name__ == "__main__":
    main(sys.argv)
