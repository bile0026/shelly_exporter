"""Tests for Shelly 1PM Gen4 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.s1pm_gen4 import Shelly1PMGen4Driver


class TestS1PMParsing:
    """Tests for parsing 1PM Gen4 status data."""

    @pytest.fixture
    def driver(self) -> Shelly1PMGen4Driver:
        """Create driver instance."""
        return Shelly1PMGen4Driver()

    @pytest.fixture
    def target(self) -> TargetConfig:
        """Target config for 1PM."""
        return TargetConfig(
            name="test_s1pm",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=0)],
        )

    def test_parse_channel(
        self,
        driver: Shelly1PMGen4Driver,
        s1pm_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test parsing 1PM status."""
        readings = driver.parse_status(s1pm_status, target)

        assert len(readings) == 1
        ch = readings[0]

        assert ch.channel_type == "switch"
        assert ch.channel_index == 0
        assert ch.output == 1.0
        assert ch.apower_w == 60.5
        assert ch.voltage_v == 120.8
        assert ch.freq_hz == 60.0
        assert ch.current_a == 0.51
        assert ch.aenergy_wh == 789.12

    def test_null_temperature(
        self,
        driver: Shelly1PMGen4Driver,
        s1pm_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test handling null temperature values (Gen4 may have null temps)."""
        readings = driver.parse_status(s1pm_status, target)

        # Temperature should be None when tC is null
        assert readings[0].temp_c is None

    def test_missing_power_factor(
        self,
        driver: Shelly1PMGen4Driver,
        s1pm_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test handling missing power factor (1PM Gen4 may not include pf)."""
        readings = driver.parse_status(s1pm_status, target)

        # pf not in fixture data
        assert readings[0].pf is None

    def test_skip_invalid_channel(
        self,
        driver: Shelly1PMGen4Driver,
        s1pm_status: dict[str, Any],
    ) -> None:
        """Test that invalid channel index is skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=1)],  # Only 0 is valid
        )
        readings = driver.parse_status(s1pm_status, target)
        assert len(readings) == 0

    def test_driver_properties(self, driver: Shelly1PMGen4Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "s1pm_gen4"
        assert driver.driver_name == "Shelly 1PM Gen4"
