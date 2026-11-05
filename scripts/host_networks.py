#!/usr/bin/env python3
"""List the IPv4 networks of this machine's interfaces, for the Network dropdown of "0. Find robots".

Run by the compose service "host-networks" with host networking on every `up -d` (Linux: the
real interfaces; Docker Desktop: the VM's, which are filtered out). Standard library only.

    host_networks.py            # JSON to stdout
    host_networks.py FILE       # write FILE atomically
"""
import array
import fcntl
import json
import ipaddress
import os
import socket
import struct
import sys

SIOCGIFCONF, SIOCGIFNETMASK = 0x8912, 0x891B
SKIP_PREFIXES = ("lo", "docker", "br-", "veth", "tailscale", "virbr", "vmnet", "tun", "wg")
SKIP_NETWORKS = (ipaddress.ip_network("192.168.65.0/24"),)      # Docker Desktop's VM network
LARGEST_PREFIX = 22      # find_robots.py scans at most 1024 addresses; shrink to the /24 of the address


def interfaces():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    size = 4096
    buf = array.array("B", b"\0" * size)
    packed = struct.pack("iL", size, buf.buffer_info()[0])
    returned = struct.unpack("iL", fcntl.ioctl(sock.fileno(), SIOCGIFCONF, packed))[0]
    data = buf.tobytes()[:returned]
    for offset in range(0, len(data), 40):
        name = data[offset:offset + 16].split(b"\0", 1)[0].decode()
        address = socket.inet_ntoa(data[offset + 20:offset + 24])
        try:
            raw = fcntl.ioctl(sock.fileno(), SIOCGIFNETMASK, struct.pack("256s", name.encode()))
            netmask = socket.inet_ntoa(raw[20:24])
        except OSError:
            continue
        yield name, address, netmask
    sock.close()


def networks():
    result, seen = [], set()
    for name, address, netmask in interfaces():
        if name.startswith(SKIP_PREFIXES):
            continue
        iface = ipaddress.ip_interface(f"{address}/{netmask}")
        network = iface.network
        if any(network.subnet_of(s) or s.subnet_of(network) for s in SKIP_NETWORKS):
            continue
        if network.prefixlen < LARGEST_PREFIX:
            network = ipaddress.ip_interface(f"{address}/24").network
        key = str(network)
        if key in seen:
            continue
        seen.add(key)
        result.append({"interface": name, "address": address, "network": key})
    return result


def main(argv):
    content = json.dumps(networks(), indent=2) + "\n"
    if len(argv) > 1:
        tmp = argv[1] + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, argv[1])
        try:  # written as root from the compose service: give the file to the repository owner
            owner = os.stat(os.path.dirname(os.path.abspath(argv[1])))
            os.chown(argv[1], owner.st_uid, owner.st_gid)
        except OSError:
            pass
    else:
        print(content, end="")


if __name__ == "__main__":
    main(sys.argv)
