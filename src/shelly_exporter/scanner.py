"""Network scanner for auto-discovering Shelly devices."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from shelly_exporter.config import (
    ChannelConfig,
    Config,
    Credentials,
    DiscoveryConfig,
    TargetConfig,
)
from shelly_exporter.drivers.registry import DriverRegistry
from shelly_exporter.metrics import (
    update_discovery_device_found,
    update_discovery_scan_completed,
    update_discovery_scan_error,
    update_discovery_scan_started,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Information about a discovered Shelly device."""

    ip: str
    device_info: dict[str, Any]
    discovered_at: datetime = field(default_factory=datetime.now)

    @property
    def model(self) -> str:
        return self.device_info.get("model", "unknown")

    @property
    def gen(self) -> int:
        return self.device_info.get("gen", 0)

    @property
    def app(self) -> str:
        return self.device_info.get("app", "unknown")

    @property
    def mac(self) -> str:
        return self.device_info.get("mac", "unknown")

    @property
    def id(self) -> str:
        return self.device_info.get("id", "unknown")


def parse_network_range(range_str: str) -> list[str]:
    """Parse a network range string into a list of IP addresses.

    Supports:
    - CIDR notation: "10.0.80.0/24"
    - IP range notation: "192.168.1.100-192.168.1.200"
    - Single IP: "10.0.80.5"

    Args:
        range_str: Network range string

    Returns:
        List of IP addresses as strings
    """
    range_str = range_str.strip()

    # Check for IP range notation (e.g., "192.168.1.100-192.168.1.200")
    range_match = re.match(
        r"^(\d+\.\d+\.\d+\.\d+)-(\d+\.\d+\.\d+\.\d+)$", range_str
    )
    if range_match:
        start_ip = ipaddress.IPv4Address(range_match.group(1))
        end_ip = ipaddress.IPv4Address(range_match.group(2))
        if start_ip > end_ip:
            start_ip, end_ip = end_ip, start_ip
        return [
            str(ipaddress.IPv4Address(ip))
            for ip in range(int(start_ip), int(end_ip) + 1)
        ]

    # Check for CIDR notation
    if "/" in range_str:
        try:
            network = ipaddress.IPv4Network(range_str, strict=False)
            # Exclude network and broadcast addresses for /24 and larger
            if network.prefixlen <= 30:
                return [str(ip) for ip in network.hosts()]
            else:
                return [str(ip) for ip in network]
        except ValueError as e:
            logger.warning(f"Invalid CIDR notation '{range_str}': {e}")
            return []

    # Single IP address
    try:
        ipaddress.IPv4Address(range_str)
        return [range_str]
    except ValueError as e:
        logger.warning(f"Invalid IP address '{range_str}': {e}")
        return []


def generate_ip_list(
    network_ranges: list[str], exclude_ips: list[str]
) -> list[str]:
    """Generate list of IPs to scan from network ranges, excluding specified IPs.

    Args:
        network_ranges: List of network range strings
        exclude_ips: List of IPs to exclude

    Returns:
        List of IP addresses to scan
    """
    all_ips: set[str] = set()
    exclude_set = set(exclude_ips)

    for range_str in network_ranges:
        ips = parse_network_range(range_str)
        all_ips.update(ips)

    # Remove excluded IPs
    all_ips -= exclude_set

    return sorted(all_ips, key=lambda ip: tuple(int(x) for x in ip.split(".")))


def format_device_name(template: str, device: DiscoveredDevice) -> str:
    """Format device name using template and device info.

    Available variables:
    - {ip}: IP address (dots replaced with underscores)
    - {model}: Device model
    - {gen}: Device generation
    - {app}: Device app name
    - {mac}: MAC address
    - {id}: Device ID (e.g., "shellypro4pm-aabbccdd")

    Args:
        template: Name template string
        device: Discovered device info

    Returns:
        Formatted device name
    """
    # Sanitize values for use in names (replace special chars)
    def sanitize(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value).lower())

    return template.format(
        ip=device.ip.replace(".", "_"),
        model=sanitize(device.model),
        gen=device.gen,
        app=sanitize(device.app),
        mac=sanitize(device.mac),
        id=sanitize(device.id),
    )


def load_discovered_devices(persist_path: str | Path) -> list[TargetConfig]:
    """Load previously discovered devices from YAML file.

    Args:
        persist_path: Path to the discovered devices file

    Returns:
        List of target configs loaded from file
    """
    path = Path(persist_path)
    if not path.exists():
        logger.debug(f"No discovered devices file at {path}")
        return []

    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "discovered_targets" not in data:
            return []

        targets = []
        for target_data in data["discovered_targets"]:
            try:
                target = TargetConfig.model_validate(target_data)
                target.discovered = True  # Ensure flag is set
                targets.append(target)
            except Exception as e:
                logger.warning(f"Failed to load discovered target: {e}")

        logger.info(f"Loaded {len(targets)} discovered devices from {path}")
        return targets

    except Exception as e:
        logger.error(f"Failed to load discovered devices from {path}: {e}")
        return []


def save_discovered_devices(
    persist_path: str | Path, targets: list[TargetConfig]
) -> None:
    """Save discovered devices to YAML file.

    Args:
        persist_path: Path to save the discovered devices file
        targets: List of discovered target configs to save
    """
    path = Path(persist_path)

    # Filter to only discovered targets
    discovered = [t for t in targets if t.discovered]

    # Convert to serializable format
    data = {
        "# Auto-generated file - discovered Shelly devices": None,
        "# Do not edit manually - changes may be overwritten": None,
        "discovered_targets": [
            {
                "name": t.name,
                "url": t.url,
                "discovered": True,
                "channels": [
                    {"type": ch.type, "index": ch.index}
                    for ch in t.channels
                ],
                # Include credentials if set
                **(
                    {
                        "credentials": {
                            "username": t.credentials.username,
                            "password": t.credentials.password,
                        }
                    }
                    if t.credentials and t.credentials.has_credentials()
                    else {}
                ),
            }
            for t in discovered
        ],
    }

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            # Write header comments
            f.write("# Auto-generated file - discovered Shelly devices\n")
            f.write("# Do not edit manually - changes may be overwritten\n\n")
            yaml.dump(
                {"discovered_targets": data["discovered_targets"]},
                f,
                default_flow_style=False,
                sort_keys=False,
            )

        logger.info(f"Saved {len(discovered)} discovered devices to {path}")

    except Exception as e:
        logger.error(f"Failed to save discovered devices to {path}: {e}")


class NetworkScanner:
    """Service for scanning network ranges and discovering Shelly devices."""

    def __init__(
        self,
        config: Config,
        driver_registry: DriverRegistry,
        on_device_discovered: Any | None = None,
    ) -> None:
        """Initialize network scanner.

        Args:
            config: Application configuration
            driver_registry: Driver registry for device support detection
            on_device_discovered: Optional callback when device is discovered
        """
        self.config = config
        self.discovery_config = config.discovery
        self.driver_registry = driver_registry
        self.on_device_discovered = on_device_discovered

        # Track discovered devices (by IP)
        self._discovered_devices: dict[str, DiscoveredDevice] = {}
        # Track created targets for persistence
        self._discovered_targets: list[TargetConfig] = []
        self._running = False
        self._scan_task: asyncio.Task[None] | None = None

        # Build set of already-configured target IPs/URLs for deduplication
        self._configured_urls: set[str] = self._get_configured_urls()

    def _get_configured_urls(self) -> set[str]:
        """Get set of URLs/IPs from all targets in the config file.

        All targets in config.yml are considered "configured" for deduplication,
        regardless of whether they were originally discovered or manually added.
        """
        urls = set()
        for target in self.config.targets:
            # Normalize URL to just the IP/hostname
            url = target.url.replace("http://", "").replace("https://", "").rstrip("/")
            urls.add(url)
        return urls

    def _is_already_configured(self, ip: str) -> bool:
        """Check if an IP is already in the configured targets."""
        return ip in self._configured_urls

    @property
    def discovered_devices(self) -> dict[str, DiscoveredDevice]:
        """Return dictionary of discovered devices by IP."""
        return self._discovered_devices.copy()

    async def _probe_ip(
        self,
        ip: str,
        client: httpx.AsyncClient,
        credentials: Credentials | None,
    ) -> DiscoveredDevice | None:
        """Probe a single IP address for a Shelly device.

        Args:
            ip: IP address to probe
            client: HTTP client
            credentials: Optional credentials

        Returns:
            DiscoveredDevice if found, None otherwise
        """
        url = f"http://{ip}/rpc"
        payload = {"id": 1, "method": "Shelly.GetDeviceInfo"}

        auth = None
        if credentials and credentials.has_credentials():
            auth = httpx.BasicAuth(
                username=credentials.username,
                password=credentials.password,
            )

        try:
            response = await client.post(url, json=payload, auth=auth)

            if response.status_code in (401, 403):
                logger.debug(f"Auth required for {ip}")
                return None

            if response.status_code != 200:
                return None

            data = response.json()
            if "result" not in data:
                return None

            device_info = data["result"]

            # Verify it looks like a Shelly device
            if "model" not in device_info and "gen" not in device_info:
                return None

            logger.info(
                f"Discovered Shelly device at {ip}: "
                f"model={device_info.get('model')}, "
                f"gen={device_info.get('gen')}, "
                f"app={device_info.get('app')}"
            )

            return DiscoveredDevice(ip=ip, device_info=device_info)

        except httpx.TimeoutException:
            logger.debug(f"Timeout probing {ip}")
            return None
        except httpx.RequestError as e:
            logger.debug(f"Error probing {ip}: {e}")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error probing {ip}: {e}")
            return None

    async def _scan_network(self) -> list[DiscoveredDevice]:
        """Scan configured network ranges for Shelly devices.

        Returns:
            List of newly discovered devices
        """
        if not self.discovery_config.network_ranges:
            logger.warning("No network ranges configured for discovery")
            return []

        update_discovery_scan_started()
        start_time = time.time()

        # Generate list of IPs to scan
        ips_to_scan = generate_ip_list(
            self.discovery_config.network_ranges,
            self.discovery_config.exclude_ips,
        )

        logger.info(f"Starting network scan of {len(ips_to_scan)} IP addresses")

        credentials = self.config.get_discovery_credentials()
        semaphore = asyncio.Semaphore(self.discovery_config.scan_concurrency)
        new_devices: list[DiscoveredDevice] = []

        async with httpx.AsyncClient(
            timeout=self.discovery_config.scan_timeout_seconds
        ) as client:

            async def probe_with_semaphore(ip: str) -> DiscoveredDevice | None:
                async with semaphore:
                    return await self._probe_ip(ip, client, credentials)

            tasks = [probe_with_semaphore(ip) for ip in ips_to_scan]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    update_discovery_scan_error()
                    continue
                if result is not None:
                    device = result
                    # Skip if already in configured targets or already discovered
                    if self._is_already_configured(device.ip):
                        logger.debug(f"Skipping {device.ip} - already in configured targets")
                        continue
                    if device.ip not in self._discovered_devices:
                        new_devices.append(device)
                        self._discovered_devices[device.ip] = device

                        # Update metrics
                        update_discovery_device_found(
                            ip=device.ip,
                            model=device.model,
                            gen=device.gen,
                            app=device.app,
                            mac=device.mac,
                            discovered_at=device.discovered_at.isoformat(),
                        )

        duration = time.time() - start_time
        update_discovery_scan_completed(duration)

        logger.info(
            f"Network scan completed in {duration:.2f}s, "
            f"found {len(new_devices)} new devices"
        )

        return new_devices

    def create_target_for_device(
        self, device: DiscoveredDevice
    ) -> TargetConfig | None:
        """Create a target configuration for a discovered device.

        Args:
            device: Discovered device

        Returns:
            TargetConfig if device is supported, None otherwise
        """
        # Find best driver for this device
        driver = self.driver_registry.get_best_driver(device.device_info)
        if driver is None:
            logger.warning(
                f"No driver found for device at {device.ip}: "
                f"model={device.model}, gen={device.gen}, app={device.app}"
            )
            return None

        # Get supported channels from driver
        supported = driver.supported_channels(device.device_info)

        # Build channel configs
        channels: list[ChannelConfig] = []
        for channel_type, indices in supported.items():
            for index in sorted(indices):
                channels.append(
                    ChannelConfig(type=channel_type, index=index)
                )

        # Note: Gateway devices (BluGw, etc.) may have no channels but are still
        # valid targets for system/wifi/connection metrics

        # Generate device name
        name = format_device_name(
            self.discovery_config.name_template, device
        )

        # Get credentials
        credentials = self.config.get_discovery_credentials()

        return TargetConfig(
            name=name,
            url=device.ip,
            credentials=credentials,
            channels=channels,
            discovered=True,
        )

    async def run_scan(self) -> list[TargetConfig]:
        """Run a single network scan and return new targets.

        Returns:
            List of new target configs for discovered devices
        """
        new_devices = await self._scan_network()
        new_targets: list[TargetConfig] = []

        if self.discovery_config.auto_add_discovered:
            for device in new_devices:
                target = self.create_target_for_device(device)
                if target:
                    new_targets.append(target)
                    self._discovered_targets.append(target)
                    logger.info(
                        f"Created target '{target.name}' for device at {device.ip}"
                    )

                    # Call discovery callback if set
                    if self.on_device_discovered:
                        await self.on_device_discovered(target)

            # Persist newly discovered targets
            if new_targets and self.discovery_config.persist_path:
                save_discovered_devices(
                    self.discovery_config.persist_path,
                    self._discovered_targets,
                )

        return new_targets

    async def start(self) -> None:
        """Start the periodic scanning service."""
        if self._running:
            logger.warning("Scanner is already running")
            return

        if not self.discovery_config.enabled:
            logger.info("Discovery is disabled, scanner not starting")
            return

        # Load previously discovered devices from persist file
        if self.discovery_config.persist_path:
            await self._load_persisted_devices()

        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info(
            f"Started network scanner, interval={self.discovery_config.scan_interval_seconds}s"
        )

    async def _load_persisted_devices(self) -> None:
        """Load previously discovered devices from persist file."""
        if not self.discovery_config.persist_path:
            return

        targets = load_discovered_devices(self.discovery_config.persist_path)
        for target in targets:
            # Track as already discovered (by URL/IP)
            ip = target.url
            if ip not in self._discovered_devices:
                # Create a minimal DiscoveredDevice entry
                self._discovered_devices[ip] = DiscoveredDevice(
                    ip=ip,
                    device_info={"model": "persisted", "gen": 0, "app": "unknown"},
                )

                # Track target for future persistence
                self._discovered_targets.append(target)

                # Add to polling via callback
                if self.on_device_discovered:
                    await self.on_device_discovered(target)
                    logger.info(f"Restored persisted device: {target.name} ({ip})")

    async def stop(self) -> None:
        """Stop the periodic scanning service."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
        logger.info("Stopped network scanner")

    async def _scan_loop(self) -> None:
        """Background loop that runs periodic scans."""
        # Run initial scan immediately
        try:
            await self.run_scan()
        except Exception as e:
            logger.error(f"Error during initial scan: {e}")

        while self._running:
            try:
                await asyncio.sleep(self.discovery_config.scan_interval_seconds)
                if self._running:
                    await self.run_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during periodic scan: {e}")
