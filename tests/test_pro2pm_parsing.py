"""Tests for Pro 2PM Gen2 driver parsing."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.pro2pm_gen2 import Pro2PMGen2Driver


class TestPro2PMParsing:
    """Tests for parsing Pro 2PM status data."""

    @pytest.fixture
    def driver(self) -> Pro2PMGen2Driver:
        """Create driver instance."""
        return Pro2PMGen2Driver()

    @pytest.fixture
    def target_both_channels(self) -> TargetConfig:
        """Target config with both channels."""
        return TargetConfig(
            name="test_pro2pm",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="switch", index=1),
            ],
        )

    @pytest.fixture
    def target_single_channel(self) -> TargetConfig:
        """Target config with single channel."""
        return TargetConfig(
            name="test_pro2pm",
            url="10.0.0.1",
            channels=[ChannelConfig(type="switch", index=0)],
        )

    def test_parse_both_channels(
        self,
        driver: Pro2PMGen2Driver,
        pro2pm_status: dict[str, Any],
        target_both_channels: TargetConfig,
    ) -> None:
        """Test parsing both switch channels."""
        readings = driver.parse_status(pro2pm_status, target_both_channels)

        assert len(readings) == 2

        ch0 = readings[0]
        assert ch0.channel_type == "switch"
        assert ch0.channel_index == 0
        assert ch0.output == 1.0
        assert ch0.apower_w == 85.2
        assert ch0.voltage_v == 230.1
        assert ch0.freq_hz == 50.0
        assert ch0.current_a == 0.38
        assert ch0.pf == 0.97
        assert ch0.temp_c == 41.2
        assert ch0.aenergy_wh == 5432.1
        assert ch0.ret_aenergy_wh == 0.0

        ch1 = readings[1]
        assert ch1.channel_index == 1
        assert ch1.output == 0.0
        assert ch1.apower_w == 0.0
        assert ch1.ret_aenergy_wh == 50.2

    def test_parse_single_channel(
        self,
        driver: Pro2PMGen2Driver,
        pro2pm_status: dict[str, Any],
        target_single_channel: TargetConfig,
    ) -> None:
        """Test parsing only configured channel."""
        readings = driver.parse_status(pro2pm_status, target_single_channel)

        assert len(readings) == 1
        assert readings[0].channel_index == 0

    def test_driver_properties(self, driver: Pro2PMGen2Driver) -> None:
        """Test driver identification properties."""
        assert driver.driver_id == "pro2pm_gen2"
        assert driver.driver_name == "Shelly Pro 2PM Gen2"

    def test_score_pro2pm(self, driver: Pro2PMGen2Driver, pro2pm_deviceinfo: dict[str, Any]) -> None:
        """Test driver scoring for Pro 2PM."""
        score = driver.score(pro2pm_deviceinfo)
        assert score == 100

    def test_score_non_match(self, driver: Pro2PMGen2Driver) -> None:
        """Test driver does not match other devices."""
        assert driver.score({"gen": 2, "app": "Pro4PM"}) == 0
        assert driver.score({"gen": 1, "app": "Pro2PM"}) == 0

    def test_supported_channels(self, driver: Pro2PMGen2Driver, pro2pm_deviceinfo: dict[str, Any]) -> None:
        """Test supported channels for Pro 2PM."""
        channels = driver.supported_channels(pro2pm_deviceinfo)
        assert channels == {"switch": {0, 1}}

    def test_skip_invalid_channel_index(
        self,
        driver: Pro2PMGen2Driver,
        pro2pm_status: dict[str, Any],
    ) -> None:
        """Test that invalid channel indices are skipped."""
        target = TargetConfig(
            name="test",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="switch", index=3),  # Invalid for Pro 2PM
            ],
        )
        readings = driver.parse_status(pro2pm_status, target)

        assert len(readings) == 1
        assert readings[0].channel_index == 0
