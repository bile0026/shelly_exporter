"""Tests for Shelly Dimmer 0/1-10V PM Gen3 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.dimmer_0110vpm_g3 import Dimmer0110VPMG3Driver


class TestDimmerParsing:
    """Tests for parsing Dimmer status data."""

    @pytest.fixture
    def driver(self) -> Dimmer0110VPMG3Driver:
        """Create driver instance."""
        return Dimmer0110VPMG3Driver()

    @pytest.fixture
    def target(self) -> TargetConfig:
        """Target config for Dimmer."""
        return TargetConfig(
            name="test_dimmer",
            url="10.0.0.1",
            channels=[ChannelConfig(type="light", index=0)],
        )

    def test_parse_light_channel(
        self,
        driver: Dimmer0110VPMG3Driver,
        dimmer_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test parsing Dimmer light channel."""
        readings = driver.parse_status(dimmer_status, target)

        assert len(readings) == 1
        ch = readings[0]

        assert ch.channel_type == "light"
        assert ch.channel_index == 0
        assert ch.output == 1.0  # True -> 1.0
        assert ch.brightness == 75.0
        assert ch.apower_w == 18.5
        assert ch.voltage_v == 120.2
        assert ch.current_a == 0.16
        assert ch.aenergy_wh == 567.89

    def test_no_switch_key_in_dimmer(
        self,
        driver: Dimmer0110VPMG3Driver,
        dimmer_status: dict[str, Any],
    ) -> None:
        """Test that dimmer has light:0, not switch:0."""
        assert "switch:0" not in dimmer_status
        assert "light:0" in dimmer_status

    def test_skip_switch_channel_type(
        self,
        driver: Dimmer0110VPMG3Driver,
        dimmer_status: dict[str, Any],
    ) -> None:
        """Test that switch channel type is skipped for dimmer."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),  # Wrong type for dimmer
            ],
        )
        readings = driver.parse_status(dimmer_status, target)
        assert len(readings) == 0

    def test_skip_invalid_light_index(
        self,
        driver: Dimmer0110VPMG3Driver,
        dimmer_status: dict[str, Any],
    ) -> None:
        """Test that invalid light index is skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[ChannelConfig(type="light", index=1)],  # Only 0 is valid
        )
        readings = driver.parse_status(dimmer_status, target)
        assert len(readings) == 0

    def test_driver_properties(self, driver: Dimmer0110VPMG3Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "dimmer_0110vpm_g3"
        assert driver.driver_name == "Shelly Dimmer 0/1-10V PM Gen3"

    def test_light_channel_no_ret_aenergy(
        self,
        driver: Dimmer0110VPMG3Driver,
        dimmer_status: dict[str, Any],
        target: TargetConfig,
    ) -> None:
        """Test that light channels don't have ret_aenergy."""
        readings = driver.parse_status(dimmer_status, target)
        assert readings[0].ret_aenergy_wh is None

    def test_light_off_state(
        self,
        driver: Dimmer0110VPMG3Driver,
        target: TargetConfig,
    ) -> None:
        """Test parsing light in off state."""
        status = {
            "light:0": {
                "id": 0,
                "output": False,
                "brightness": 0,
                "apower": 0.0,
            }
        }
        readings = driver.parse_status(status, target)

        assert len(readings) == 1
        ch = readings[0]
        assert ch.output == 0.0
        assert ch.brightness == 0.0
        assert ch.apower_w == 0.0

    def test_partial_light_data(
        self,
        driver: Dimmer0110VPMG3Driver,
        target: TargetConfig,
    ) -> None:
        """Test handling partial light data."""
        status = {
            "light:0": {
                "id": 0,
                "output": True,
                "brightness": 50,
                # Missing: apower, voltage, current, aenergy
            }
        }
        readings = driver.parse_status(status, target)

        assert len(readings) == 1
        ch = readings[0]
        assert ch.output == 1.0
        assert ch.brightness == 50.0
        assert ch.apower_w is None
        assert ch.voltage_v is None
        assert ch.aenergy_wh is None
