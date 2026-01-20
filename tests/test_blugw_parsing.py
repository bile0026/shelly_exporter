"""Tests for BLU Gateway drivers parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.blugw_gen2 import BluGwGen2Driver
from shelly_exporter.drivers.blugw_gen3 import BluGwGen3Driver


class TestBluGwGen2Parsing:
    """Tests for BLU Gateway Gen2 status parsing."""

    @pytest.fixture
    def driver(self) -> BluGwGen2Driver:
        """Create driver instance."""
        return BluGwGen2Driver()

    @pytest.fixture
    def target_config(self) -> TargetConfig:
        """Create target config (gateway has no channels)."""
        return TargetConfig(
            name="test_blugw",
            url="10.0.80.48",
            channels=[],
        )

    def test_parse_status_returns_empty(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_status: dict[str, Any],
        target_config: TargetConfig,
    ) -> None:
        """Test that parse_status returns empty list for gateway."""
        readings = driver.parse_status(blugw_gen2_status, target_config)
        assert len(readings) == 0

    def test_driver_properties(self, driver: BluGwGen2Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "blugw_gen2"
        assert driver.driver_name == "Shelly BLU Gateway Gen2"

    def test_scoring(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_deviceinfo: dict[str, Any],
    ) -> None:
        """Test driver scoring for BLU Gateway Gen2."""
        score = driver.score(blugw_gen2_deviceinfo)
        assert score == 100

    def test_scoring_non_match(self, driver: BluGwGen2Driver) -> None:
        """Test driver scoring for non-matching device."""
        score = driver.score({"gen": 2, "app": "Pro4PM"})
        assert score == 0

    def test_supported_channels_empty(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_deviceinfo: dict[str, Any],
    ) -> None:
        """Test supported channels returns empty dict for gateway."""
        channels = driver.supported_channels(blugw_gen2_deviceinfo)
        assert channels == {}

    def test_parse_system_data(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_status: dict[str, Any],
    ) -> None:
        """Test parsing system data from gateway status."""
        system = driver.parse_system(blugw_gen2_status)

        assert system is not None
        assert system.uptime_seconds == 8061490
        assert system.ram_size_bytes == 266864
        assert system.ram_free_bytes == 118572

    def test_parse_wifi_data(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_status: dict[str, Any],
    ) -> None:
        """Test parsing WiFi data from gateway status."""
        wifi = driver.parse_wifi(blugw_gen2_status)

        assert wifi is not None
        assert wifi.rssi_dbm == -36
        assert wifi.connected == 1.0

    def test_parse_connection_status(
        self,
        driver: BluGwGen2Driver,
        blugw_gen2_status: dict[str, Any],
    ) -> None:
        """Test parsing connection status from gateway."""
        conn = driver.parse_connection_status(blugw_gen2_status)

        assert conn is not None
        assert conn.cloud_connected == 1.0
        assert conn.mqtt_connected == 1.0


class TestBluGwGen3Parsing:
    """Tests for BLU Gateway Gen3 status parsing."""

    @pytest.fixture
    def driver(self) -> BluGwGen3Driver:
        """Create driver instance."""
        return BluGwGen3Driver()

    @pytest.fixture
    def target_config(self) -> TargetConfig:
        """Create target config (gateway has no channels)."""
        return TargetConfig(
            name="test_blugw_g3",
            url="10.0.80.45",
            channels=[],
        )

    def test_parse_status_returns_empty(
        self,
        driver: BluGwGen3Driver,
        blugw_gen3_status: dict[str, Any],
        target_config: TargetConfig,
    ) -> None:
        """Test that parse_status returns empty list for gateway."""
        readings = driver.parse_status(blugw_gen3_status, target_config)
        assert len(readings) == 0

    def test_driver_properties(self, driver: BluGwGen3Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "blugw_gen3"
        assert driver.driver_name == "Shelly BLU Gateway Gen3"

    def test_scoring(
        self,
        driver: BluGwGen3Driver,
        blugw_gen3_deviceinfo: dict[str, Any],
    ) -> None:
        """Test driver scoring for BLU Gateway Gen3."""
        score = driver.score(blugw_gen3_deviceinfo)
        assert score == 100

    def test_scoring_non_match(self, driver: BluGwGen3Driver) -> None:
        """Test driver scoring for non-matching device."""
        score = driver.score({"gen": 3, "app": "Dimmer0110VPMG3"})
        assert score == 0

    def test_supported_channels_empty(
        self,
        driver: BluGwGen3Driver,
        blugw_gen3_deviceinfo: dict[str, Any],
    ) -> None:
        """Test supported channels returns empty dict for gateway."""
        channels = driver.supported_channels(blugw_gen3_deviceinfo)
        assert channels == {}

    def test_parse_system_data(
        self,
        driver: BluGwGen3Driver,
        blugw_gen3_status: dict[str, Any],
    ) -> None:
        """Test parsing system data from gateway status."""
        system = driver.parse_system(blugw_gen3_status)

        assert system is not None
        assert system.uptime_seconds == 1396815
        assert system.ram_size_bytes == 268884

    def test_parse_wifi_data(
        self,
        driver: BluGwGen3Driver,
        blugw_gen3_status: dict[str, Any],
    ) -> None:
        """Test parsing WiFi data from gateway status."""
        wifi = driver.parse_wifi(blugw_gen3_status)

        assert wifi is not None
        assert wifi.rssi_dbm == -47
        assert wifi.connected == 1.0
