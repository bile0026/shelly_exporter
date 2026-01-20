"""Tests for network scanner and auto-discovery."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shelly_exporter.config import (
    ChannelConfig,
    Config,
    Credentials,
    DiscoveryConfig,
    TargetConfig,
)
from shelly_exporter.drivers.registry import DriverRegistry
from shelly_exporter.scanner import (
    DiscoveredDevice,
    NetworkScanner,
    format_device_name,
    generate_ip_list,
    load_discovered_devices,
    parse_network_range,
    save_discovered_devices,
)


class TestParseNetworkRange:
    """Tests for parse_network_range function."""

    def test_parse_cidr_24(self) -> None:
        """Test parsing /24 CIDR notation."""
        ips = parse_network_range("10.0.80.0/24")
        assert len(ips) == 254  # Excludes network and broadcast
        assert "10.0.80.1" in ips
        assert "10.0.80.254" in ips
        assert "10.0.80.0" not in ips  # Network address excluded
        assert "10.0.80.255" not in ips  # Broadcast excluded

    def test_parse_cidr_30(self) -> None:
        """Test parsing /30 CIDR notation."""
        ips = parse_network_range("10.0.80.0/30")
        assert len(ips) == 2  # Only usable hosts
        assert "10.0.80.1" in ips
        assert "10.0.80.2" in ips

    def test_parse_ip_range(self) -> None:
        """Test parsing IP range notation."""
        ips = parse_network_range("192.168.1.100-192.168.1.105")
        assert len(ips) == 6
        assert ips == [
            "192.168.1.100",
            "192.168.1.101",
            "192.168.1.102",
            "192.168.1.103",
            "192.168.1.104",
            "192.168.1.105",
        ]

    def test_parse_ip_range_reversed(self) -> None:
        """Test parsing IP range with reversed order."""
        ips = parse_network_range("192.168.1.105-192.168.1.100")
        assert len(ips) == 6
        assert "192.168.1.100" in ips
        assert "192.168.1.105" in ips

    def test_parse_single_ip(self) -> None:
        """Test parsing single IP address."""
        ips = parse_network_range("10.0.80.5")
        assert ips == ["10.0.80.5"]

    def test_parse_invalid_cidr(self) -> None:
        """Test parsing invalid CIDR notation."""
        ips = parse_network_range("10.0.80.0/abc")
        assert ips == []

    def test_parse_invalid_ip(self) -> None:
        """Test parsing invalid IP address."""
        ips = parse_network_range("not.an.ip.address")
        assert ips == []


class TestGenerateIpList:
    """Tests for generate_ip_list function."""

    def test_generate_from_multiple_ranges(self) -> None:
        """Test generating IP list from multiple ranges."""
        ranges = ["10.0.80.1-10.0.80.3", "192.168.1.1-192.168.1.2"]
        ips = generate_ip_list(ranges, [])
        assert len(ips) == 5
        assert "10.0.80.1" in ips
        assert "192.168.1.2" in ips

    def test_generate_with_exclusions(self) -> None:
        """Test IP exclusion."""
        ranges = ["10.0.80.1-10.0.80.5"]
        exclude = ["10.0.80.2", "10.0.80.4"]
        ips = generate_ip_list(ranges, exclude)
        assert len(ips) == 3
        assert "10.0.80.2" not in ips
        assert "10.0.80.4" not in ips
        assert "10.0.80.1" in ips
        assert "10.0.80.3" in ips
        assert "10.0.80.5" in ips

    def test_generate_deduplicated(self) -> None:
        """Test that duplicate IPs from overlapping ranges are deduplicated."""
        ranges = ["10.0.80.1-10.0.80.3", "10.0.80.2-10.0.80.4"]
        ips = generate_ip_list(ranges, [])
        assert len(ips) == 4  # 1, 2, 3, 4 - no duplicates


class TestFormatDeviceName:
    """Tests for format_device_name function."""

    def test_format_basic(self) -> None:
        """Test basic name formatting."""
        device = DiscoveredDevice(
            ip="10.0.80.22",
            device_info={
                "model": "SPSW-104PE16EU",
                "gen": 2,
                "app": "Pro4PM",
                "mac": "A8032AB12345",
            },
        )
        name = format_device_name("shelly_{ip}_{model}", device)
        # Hyphens are preserved, other special chars become underscores
        assert name == "shelly_10_0_80_22_spsw-104pe16eu"

    def test_format_with_gen_and_app(self) -> None:
        """Test formatting with gen and app variables."""
        device = DiscoveredDevice(
            ip="192.168.1.100",
            device_info={
                "model": "PlugUS",
                "gen": 2,
                "app": "PlugUS",
                "mac": "AABBCCDDEE",
            },
        )
        name = format_device_name("{app}_gen{gen}_{ip}", device)
        assert name == "plugus_gen2_192_168_1_100"


class TestDiscoveredDevice:
    """Tests for DiscoveredDevice dataclass."""

    def test_properties(self) -> None:
        """Test property accessors."""
        device = DiscoveredDevice(
            ip="10.0.80.1",
            device_info={
                "model": "TestModel",
                "gen": 3,
                "app": "TestApp",
                "mac": "AABBCC",
            },
        )
        assert device.model == "TestModel"
        assert device.gen == 3
        assert device.app == "TestApp"
        assert device.mac == "AABBCC"

    def test_missing_properties(self) -> None:
        """Test properties with missing device info fields."""
        device = DiscoveredDevice(ip="10.0.80.1", device_info={})
        assert device.model == "unknown"
        assert device.gen == 0
        assert device.app == "unknown"
        assert device.mac == "unknown"


class TestNetworkScanner:
    """Tests for NetworkScanner class."""

    @pytest.fixture
    def mock_config(self) -> Config:
        """Create a mock configuration."""
        return Config(
            discovery=DiscoveryConfig(
                enabled=True,
                network_ranges=["10.0.80.1-10.0.80.3"],
                scan_timeout_seconds=1.0,
                scan_concurrency=5,
                auto_add_discovered=True,
                name_template="shelly_{ip}_{model}",
            ),
            default_credentials=Credentials(username="", password=""),
        )

    @pytest.fixture
    def mock_registry(self) -> DriverRegistry:
        """Create a mock driver registry."""
        registry = MagicMock(spec=DriverRegistry)

        # Create a mock driver
        mock_driver = MagicMock()
        mock_driver.supported_channels.return_value = {"switch": {0, 1}}

        registry.get_best_driver.return_value = mock_driver
        return registry

    def test_create_target_for_device(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test creating a target config from a discovered device."""
        scanner = NetworkScanner(mock_config, mock_registry)

        device = DiscoveredDevice(
            ip="10.0.80.22",
            device_info={
                "model": "SPSW-104PE16EU",
                "gen": 2,
                "app": "Pro4PM",
                "mac": "A8032AB12345",
            },
        )

        target = scanner.create_target_for_device(device)

        assert target is not None
        assert target.url == "10.0.80.22"
        assert target.discovered is True
        assert len(target.channels) == 2
        assert target.channels[0].type == "switch"
        assert target.channels[0].index == 0
        assert target.channels[1].type == "switch"
        assert target.channels[1].index == 1

    def test_create_target_no_driver(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test creating target when no driver is available."""
        mock_registry.get_best_driver.return_value = None
        scanner = NetworkScanner(mock_config, mock_registry)

        device = DiscoveredDevice(
            ip="10.0.80.22",
            device_info={"model": "Unknown", "gen": 99, "app": "Unknown"},
        )

        target = scanner.create_target_for_device(device)
        assert target is None

    @pytest.mark.asyncio
    async def test_probe_ip_success(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test successful IP probe."""
        scanner = NetworkScanner(mock_config, mock_registry)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "model": "SPSW-104PE16EU",
                "gen": 2,
                "app": "Pro4PM",
                "mac": "A8032AB12345",
            }
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        device = await scanner._probe_ip("10.0.80.22", mock_client, None)

        assert device is not None
        assert device.ip == "10.0.80.22"
        assert device.model == "SPSW-104PE16EU"

    @pytest.mark.asyncio
    async def test_probe_ip_auth_failure(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test IP probe with auth failure."""
        scanner = NetworkScanner(mock_config, mock_registry)

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        device = await scanner._probe_ip("10.0.80.22", mock_client, None)
        assert device is None

    @pytest.mark.asyncio
    async def test_probe_ip_timeout(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test IP probe with timeout."""
        import httpx

        scanner = NetworkScanner(mock_config, mock_registry)

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        device = await scanner._probe_ip("10.0.80.22", mock_client, None)
        assert device is None

    @pytest.mark.asyncio
    async def test_probe_ip_not_shelly(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test IP probe for non-Shelly device."""
        scanner = NetworkScanner(mock_config, mock_registry)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"something": "else"}}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        device = await scanner._probe_ip("10.0.80.22", mock_client, None)
        assert device is None

    def test_discovered_devices_property(
        self, mock_config: Config, mock_registry: DriverRegistry
    ) -> None:
        """Test discovered_devices property returns a copy."""
        scanner = NetworkScanner(mock_config, mock_registry)

        device = DiscoveredDevice(
            ip="10.0.80.22",
            device_info={"model": "Test", "gen": 2, "app": "Test"},
        )
        scanner._discovered_devices["10.0.80.22"] = device

        # Get copy
        devices = scanner.discovered_devices

        # Modify copy
        devices["10.0.80.99"] = device

        # Original should be unchanged
        assert "10.0.80.99" not in scanner._discovered_devices


class TestPersistence:
    """Tests for discovered devices persistence."""

    def test_save_and_load_discovered_devices(self) -> None:
        """Test saving and loading discovered devices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "discovered.yml"

            # Create targets to save
            targets = [
                TargetConfig(
                    name="device_1",
                    url="10.0.80.1",
                    discovered=True,
                    channels=[
                        ChannelConfig(type="switch", index=0),
                        ChannelConfig(type="switch", index=1),
                    ],
                ),
                TargetConfig(
                    name="device_2",
                    url="10.0.80.2",
                    discovered=True,
                    channels=[ChannelConfig(type="light", index=0)],
                ),
            ]

            # Save
            save_discovered_devices(persist_path, targets)

            # Verify file exists
            assert persist_path.exists()

            # Load
            loaded = load_discovered_devices(persist_path)

            assert len(loaded) == 2
            assert loaded[0].name == "device_1"
            assert loaded[0].url == "10.0.80.1"
            assert loaded[0].discovered is True
            assert len(loaded[0].channels) == 2
            assert loaded[1].name == "device_2"
            assert loaded[1].url == "10.0.80.2"

    def test_load_nonexistent_file(self) -> None:
        """Test loading from nonexistent file returns empty list."""
        targets = load_discovered_devices("/nonexistent/path/discovered.yml")
        assert targets == []

    def test_save_only_discovered_targets(self) -> None:
        """Test that only discovered targets are saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "discovered.yml"

            # Mix of discovered and configured targets
            targets = [
                TargetConfig(
                    name="configured_device",
                    url="10.0.80.1",
                    discovered=False,  # Not discovered
                    channels=[ChannelConfig(type="switch", index=0)],
                ),
                TargetConfig(
                    name="discovered_device",
                    url="10.0.80.2",
                    discovered=True,  # Discovered
                    channels=[ChannelConfig(type="switch", index=0)],
                ),
            ]

            save_discovered_devices(persist_path, targets)
            loaded = load_discovered_devices(persist_path)

            # Only discovered device should be saved
            assert len(loaded) == 1
            assert loaded[0].name == "discovered_device"

    def test_save_with_credentials(self) -> None:
        """Test that credentials are saved when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "discovered.yml"

            targets = [
                TargetConfig(
                    name="device_with_creds",
                    url="10.0.80.1",
                    discovered=True,
                    credentials=Credentials(username="admin", password="secret"),
                    channels=[ChannelConfig(type="switch", index=0)],
                ),
            ]

            save_discovered_devices(persist_path, targets)
            loaded = load_discovered_devices(persist_path)

            assert len(loaded) == 1
            assert loaded[0].credentials is not None
            assert loaded[0].credentials.username == "admin"
            assert loaded[0].credentials.password == "secret"

    def test_load_empty_file(self) -> None:
        """Test loading from empty/invalid file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "discovered.yml"

            # Create empty file
            persist_path.write_text("")

            targets = load_discovered_devices(persist_path)
            assert targets == []

    def test_creates_parent_directory(self) -> None:
        """Test that save creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "subdir" / "nested" / "discovered.yml"

            targets = [
                TargetConfig(
                    name="device",
                    url="10.0.80.1",
                    discovered=True,
                    channels=[ChannelConfig(type="switch", index=0)],
                ),
            ]

            save_discovered_devices(persist_path, targets)
            assert persist_path.exists()
