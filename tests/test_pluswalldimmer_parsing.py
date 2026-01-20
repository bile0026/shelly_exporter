"""Tests for Plus Wall Dimmer Gen2 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.pluswalldimmer_gen2 import PlusWallDimmerGen2Driver


class TestPlusWallDimmerParsing:
    """Tests for Plus Wall Dimmer Gen2 status parsing."""

    @pytest.fixture
    def driver(self) -> PlusWallDimmerGen2Driver:
        """Create driver instance."""
        return PlusWallDimmerGen2Driver()

    @pytest.fixture
    def target_config(self) -> TargetConfig:
        """Create target config with light channel."""
        return TargetConfig(
            name="test_walldimmer",
            url="10.0.80.42",
            channels=[ChannelConfig(type="light", index=0)],
        )

    def test_parse_light_channel(
        self,
        driver: PlusWallDimmerGen2Driver,
        pluswalldimmer_status: dict[str, Any],
        target_config: TargetConfig,
    ) -> None:
        """Test parsing light channel from status."""
        readings = driver.parse_status(pluswalldimmer_status, target_config)

        assert len(readings) == 1
        reading = readings[0]

        assert reading.channel_type == "light"
        assert reading.channel_index == 0
        assert reading.output == 0.0  # output: false
        assert reading.brightness == 100.0
        # No power metering on this device
        assert reading.apower_w is None
        assert reading.voltage_v is None
        assert reading.current_a is None

    def test_driver_properties(self, driver: PlusWallDimmerGen2Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "pluswalldimmer_gen2"
        assert driver.driver_name == "Shelly Plus Wall Dimmer US Gen2"

    def test_scoring(
        self,
        driver: PlusWallDimmerGen2Driver,
        pluswalldimmer_deviceinfo: dict[str, Any],
    ) -> None:
        """Test driver scoring for Plus Wall Dimmer."""
        score = driver.score(pluswalldimmer_deviceinfo)
        assert score == 100

    def test_scoring_non_match(self, driver: PlusWallDimmerGen2Driver) -> None:
        """Test driver scoring for non-matching device."""
        score = driver.score({"gen": 2, "app": "Pro4PM"})
        assert score == 0

    def test_supported_channels(
        self,
        driver: PlusWallDimmerGen2Driver,
        pluswalldimmer_deviceinfo: dict[str, Any],
    ) -> None:
        """Test supported channels detection."""
        channels = driver.supported_channels(pluswalldimmer_deviceinfo)
        assert channels == {"light": {0}}

    def test_skip_switch_channel_type(
        self,
        driver: PlusWallDimmerGen2Driver,
        pluswalldimmer_status: dict[str, Any],
    ) -> None:
        """Test that switch channel type is skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.80.42",
            channels=[ChannelConfig(type="switch", index=0)],
        )
        readings = driver.parse_status(pluswalldimmer_status, target)
        assert len(readings) == 0

    def test_light_on_state(
        self,
        driver: PlusWallDimmerGen2Driver,
        target_config: TargetConfig,
    ) -> None:
        """Test parsing when light is on."""
        status = {
            "light:0": {
                "id": 0,
                "output": True,
                "brightness": 75,
            }
        }
        readings = driver.parse_status(status, target_config)

        assert len(readings) == 1
        assert readings[0].output == 1.0
        assert readings[0].brightness == 75.0
