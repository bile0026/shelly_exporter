"""Tests for Pro 4PM Gen2 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.pro4pm_gen2 import Pro4PMGen2Driver


class TestPro4PMParsing:
    """Tests for parsing Pro 4PM status data."""

    @pytest.fixture
    def driver(self) -> Pro4PMGen2Driver:
        """Create driver instance."""
        return Pro4PMGen2Driver()

    @pytest.fixture
    def target_all_channels(self) -> TargetConfig:
        """Target config with all 4 channels."""
        return TargetConfig(
            name="test_pro4pm",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="switch", index=1),
                ChannelConfig(type="switch", index=2),
                ChannelConfig(type="switch", index=3),
            ],
        )

    @pytest.fixture
    def target_single_channel(self) -> TargetConfig:
        """Target config with single channel."""
        return TargetConfig(
            name="test_pro4pm",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=0)],
        )

    def test_parse_all_channels(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
        target_all_channels: TargetConfig,
    ) -> None:
        """Test parsing all 4 switch channels."""
        readings = driver.parse_status(pro4pm_status, target_all_channels)

        assert len(readings) == 4

        # Check channel 0
        ch0 = readings[0]
        assert ch0.channel_type == "switch"
        assert ch0.channel_index == 0
        assert ch0.output == 1.0  # True -> 1.0
        assert ch0.apower_w == 125.5
        assert ch0.voltage_v == 121.3
        assert ch0.freq_hz == 60.0
        assert ch0.current_a == 1.05
        assert ch0.pf == 0.98
        assert ch0.temp_c == 42.5
        assert ch0.aenergy_wh == 12345.67
        assert ch0.ret_aenergy_wh == 0.0

        # Check channel 1 (output is off)
        ch1 = readings[1]
        assert ch1.channel_index == 1
        assert ch1.output == 0.0  # False -> 0.0
        assert ch1.apower_w == 0.0
        assert ch1.ret_aenergy_wh == 100.5

    def test_parse_single_channel(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
        target_single_channel: TargetConfig,
    ) -> None:
        """Test parsing only configured channel."""
        readings = driver.parse_status(pro4pm_status, target_single_channel)

        assert len(readings) == 1
        assert readings[0].channel_index == 0

    def test_skip_invalid_channel_index(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test that invalid channel indices are skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="switch", index=5),  # Invalid
            ],
        )
        readings = driver.parse_status(pro4pm_status, target)

        assert len(readings) == 1
        assert readings[0].channel_index == 0

    def test_skip_light_channel_type(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test that light channel type is skipped for switch device."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="light", index=0),  # Wrong type
            ],
        )
        readings = driver.parse_status(pro4pm_status, target)

        assert len(readings) == 1
        assert readings[0].channel_type == "switch"

    def test_handle_missing_channel_data(
        self,
        driver: Pro4PMGen2Driver,
        target_all_channels: TargetConfig,
    ) -> None:
        """Test handling of missing channel data."""
        status = {
            "switch:0": {"output": True, "apower": 100.0},
            # switch:1, switch:2, switch:3 missing
        }
        readings = driver.parse_status(status, target_all_channels)

        # Only channel 0 should have reading
        assert len(readings) == 1
        assert readings[0].channel_index == 0

    def test_handle_partial_data(
        self,
        driver: Pro4PMGen2Driver,
        target_single_channel: TargetConfig,
    ) -> None:
        """Test handling of partial channel data (missing fields)."""
        status = {
            "switch:0": {
                "output": False,
                "apower": 0.0,
                # Missing: voltage, freq, current, pf, temperature, aenergy, ret_aenergy
            }
        }
        readings = driver.parse_status(status, target_single_channel)

        assert len(readings) == 1
        ch = readings[0]
        assert ch.output == 0.0
        assert ch.apower_w == 0.0
        assert ch.voltage_v is None
        assert ch.freq_hz is None
        assert ch.current_a is None
        assert ch.pf is None
        assert ch.temp_c is None
        assert ch.aenergy_wh is None
        assert ch.ret_aenergy_wh is None
