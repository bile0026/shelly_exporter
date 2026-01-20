"""Tests for Shelly Plug US Gen2 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.plugus_gen2 import PlugUSGen2Driver


class TestPlugUSParsing:
    """Tests for parsing Plug US status data."""

    @pytest.fixture
    def driver(self) -> PlugUSGen2Driver:
        """Create driver instance."""
        return PlugUSGen2Driver()

    @pytest.fixture
    def target(self) -> TargetConfig:
        """Target config for Plug US."""
        return TargetConfig(
            name="test_plugus",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=0)],
        )

    def test_parse_channel(
        self,
        driver: PlugUSGen2Driver,
        plugus_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test parsing Plug US status."""
        readings = driver.parse_status(plugus_status, target)

        assert len(readings) == 1
        ch = readings[0]

        assert ch.channel_type == "switch"
        assert ch.channel_index == 0
        assert ch.output == 1.0
        assert ch.apower_w == 45.2
        assert ch.voltage_v == 119.5
        assert ch.current_a == 0.38
        assert ch.temp_c == 35.5
        assert ch.aenergy_wh == 3456.78

    def test_missing_freq_and_pf(
        self,
        driver: PlugUSGen2Driver,
        plugus_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test handling missing freq and pf (Plug US doesn't report these)."""
        readings = driver.parse_status(plugus_status, target)

        # freq and pf not in fixture data
        assert readings[0].freq_hz is None
        assert readings[0].pf is None

    def test_missing_ret_aenergy(
        self,
        driver: PlugUSGen2Driver,
        plugus_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test handling missing ret_aenergy (Plug US doesn't return energy)."""
        readings = driver.parse_status(plugus_status, target)
        assert readings[0].ret_aenergy_wh is None

    def test_skip_invalid_channel(
        self,
        driver: PlugUSGen2Driver,
        plugus_status: dict[str, Any],
    ) -> None:
        """Test that invalid channel index is skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=1)],  # Only 0 is valid
        )
        readings = driver.parse_status(plugus_status, target)
        assert len(readings) == 0

    def test_driver_properties(self, driver: PlugUSGen2Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "plugus_gen2"
        assert driver.driver_name == "Shelly Plug US Gen2"

    def test_handle_empty_status(
        self,
        driver: PlugUSGen2Driver,
        target: TargetConfig,
    ) -> None:
        """Test handling empty status response."""
        readings = driver.parse_status({}, target)
        assert len(readings) == 0
