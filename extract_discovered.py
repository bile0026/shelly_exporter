#!/usr/bin/env python3
"""Extract discovered devices from metrics and generate config entries."""

import re
import sys
from urllib.request import urlopen

METRICS_URL = "http://localhost:10037/metrics"
CONFIG_FILE = "/apps/shelly_exporter/config/config.yml"


def parse_metrics():
    """Parse discovered devices from metrics endpoint."""
    try:
        with urlopen(METRICS_URL) as f:
            metrics = f.read().decode("utf-8")
    except Exception as e:
        print(f"Error fetching metrics: {e}", file=sys.stderr)
        sys.exit(1)

    devices = []
    for line in metrics.split("\n"):
        if not line.startswith("shelly_discovered_device_info{"):
            continue

        # Extract labels: app="Pro4PM",discovered_at="...",gen="2",ip="10.0.80.53",mac="...",model="..."
        match = re.search(r"\{([^}]+)\}", line)
        if not match:
            continue

        labels = {}
        for part in match.group(1).split(","):
            key, value = part.split("=", 1)
            labels[key] = value.strip('"')

        devices.append(labels)

    return devices


def get_existing_ips():
    """Get IPs already in config file."""
    try:
        with open(CONFIG_FILE) as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading config: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract URLs from config
    ips = set()
    for match in re.finditer(r'url:\s*([0-9.]+)', content):
        ips.add(match.group(1))

    return ips


def get_channels_for_device(app: str, gen: int) -> list[dict]:
    """Get channel configuration based on device type."""
    # Pro2PM Gen2: 2 switch channels
    if gen == 2 and app == "Pro2PM":
        return [
            {"type": "switch", "index": 0},
            {"type": "switch", "index": 1},
        ]

    # Pro4PM Gen2: 4 switch channels
    if gen == 2 and app == "Pro4PM":
        return [
            {"type": "switch", "index": 0},
            {"type": "switch", "index": 1},
            {"type": "switch", "index": 2},
            {"type": "switch", "index": 3},
        ]

    # PlusWallDimmer Gen2: 1 light channel
    if gen == 2 and app == "PlusWallDimmer":
        return [{"type": "light", "index": 0}]

    # Plus10V Gen2: likely 1 light channel (similar to PlusWallDimmer)
    if gen == 2 and app == "Plus10V":
        return [{"type": "light", "index": 0}]

    # Default: empty channels (gateway devices, etc.)
    return []


def generate_name(ip: str, model: str, mac: str) -> str:
    """Generate a device name from IP, model, and MAC."""
    # Use IP and MAC for uniqueness (some devices share MACs)
    mac_short = mac[-4:].lower() if mac else "unknown"
    model_clean = model.lower().replace("-", "_")
    ip_clean = ip.replace(".", "_")
    return f"shelly_{ip_clean}_{mac_short}_{model_clean}"


def generate_yaml(devices: list[dict], existing_ips: set[str]) -> str:
    """Generate YAML config entries for discovered devices."""
    entries = []
    missing = []

    for device in devices:
        ip = device.get("ip", "")
        if not ip or ip in existing_ips:
            continue

        app = device.get("app", "unknown")
        gen = int(device.get("gen", "0"))
        model = device.get("model", "unknown")
        mac = device.get("mac", "")

        channels = get_channels_for_device(app, gen)
        name = generate_name(ip, model, mac)

        entry = {
            "name": name,
            "url": ip,
            "discovered": True,
            "channels": channels,
        }

        entries.append(entry)
        missing.append(ip)

    if not entries:
        return "# No new discovered devices to add (all already in config)\n"

    yaml_lines = ["# Discovered devices (extracted from metrics)", ""]
    for entry in entries:
        yaml_lines.append(f"  - name: {entry['name']}")
        yaml_lines.append(f"    url: {entry['url']}")
        yaml_lines.append(f"    discovered: true")
        if entry["channels"]:
            yaml_lines.append("    channels:")
            for ch in entry["channels"]:
                yaml_lines.append(f"    - type: {ch['type']}")
                yaml_lines.append(f"      index: {ch['index']}")
        else:
            yaml_lines.append("    channels: []")
        yaml_lines.append("")

    return "\n".join(yaml_lines)


def main():
    """Main entry point."""
    print("Fetching discovered devices from metrics...", file=sys.stderr)
    devices = parse_metrics()
    print(f"Found {len(devices)} discovered devices in metrics", file=sys.stderr)

    print("Reading existing config...", file=sys.stderr)
    existing_ips = get_existing_ips()
    print(f"Found {len(existing_ips)} devices already in config", file=sys.stderr)

    yaml_output = generate_yaml(devices, existing_ips)
    print(yaml_output)


if __name__ == "__main__":
    main()
