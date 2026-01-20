"""Tests for Prometheus metrics updates."""

from __future__ import annotations

import math

import pytest
from prometheus_client import REGISTRY

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceReading
from shelly_exporter.metrics import (
    shelly_light_aenergy,
    shelly_light_apower,
    shelly_light_brightness,
    shelly_light_output,
    shelly_poll_duration,
    shelly_poll_errors,
    shelly_switch_aenergy,
    shelly_switch_apower,
    shelly_switch_current,
    shelly_switch_frequency,
    shelly_switch_output,
    shelly_switch_power_factor,
    shelly_switch_ret_aenergy,
    shelly_switch_temperature,
    shelly_switch_voltage,
    shelly_up,
    update_channel_metrics,
    update_device_metrics,
    update_metrics_from_reading,
)


class TestDeviceMetrics:
    """Tests for per-device metrics updates."""

    def test_update_device_up(self) -> None:
        """Test updating device up metric."""
        reading = DeviceReading(
            device_name="test_device",
            up=True,
            poll_duration_seconds=0.5,
        )
        update_device_metrics(reading)

        assert shelly_up.labels(device="test_device")._value.get() == 1.0

    def test_update_device_down(self) -> None:
        """Test updating device down metric."""
        reading = DeviceReading(
            device_name="test_device_down",
            up=False,
            poll_duration_seconds=0.0,
            error_message="Connection timeout",
        )
        update_device_metrics(reading)

        assert shelly_up.labels(device="test_device_down")._value.get() == 0.0

    def test_update_poll_duration(self) -> None:
        """Test updating poll duration metric."""
        reading = DeviceReading(
            device_name="duration_test",
            up=True,
            poll_duration_seconds=1.234,
        )
        update_device_metrics(reading)

        assert shelly_poll_duration.labels(device="duration_test")._value.get() == 1.234


class TestSwitchMetrics:
    """Tests for switch channel metrics updates."""

    def test_update_switch_metrics(self) -> None:
        """Test updating all switch metrics."""
        reading = ChannelReading(
            channel_type="switch",
            channel_index=0,
            output=1.0,
            apower_w=125.5,
            voltage_v=121.3,
            freq_hz=60.0,
            current_a=1.05,
            pf=0.98,
            temp_c=42.5,
            aenergy_wh=12345.67,
            ret_aenergy_wh=100.5,
        )

        channel_config = ChannelConfig(type="switch", index=0)
        update_channel_metrics("switch_test", reading, channel_config)

        labels = {"device": "switch_test", "meter": "0"}
        assert shelly_switch_output.labels(**labels)._value.get() == 1.0
        assert shelly_switch_apower.labels(**labels)._value.get() == 125.5
        assert shelly_switch_voltage.labels(**labels)._value.get() == 121.3
        assert shelly_switch_frequency.labels(**labels)._value.get() == 60.0
        assert shelly_switch_current.labels(**labels)._value.get() == 1.05
        assert shelly_switch_power_factor.labels(**labels)._value.get() == 0.98
        assert shelly_switch_temperature.labels(**labels)._value.get() == 42.5
        assert shelly_switch_aenergy.labels(**labels)._value.get() == 12345.67
        assert shelly_switch_ret_aenergy.labels(**labels)._value.get() == 100.5

    def test_switch_metrics_with_none_values(self) -> None:
        """Test that None values are set as NaN."""
        reading = ChannelReading(
            channel_type="switch",
            channel_index=1,
            output=0.0,
            apower_w=None,
            voltage_v=None,
            freq_hz=None,
            current_a=None,
            pf=None,
            temp_c=None,
            aenergy_wh=None,
            ret_aenergy_wh=None,
        )

        update_channel_metrics("nan_test", reading, None)

        labels = {"device": "nan_test", "meter": "1"}
        assert math.isnan(shelly_switch_apower.labels(**labels)._value.get())
        assert math.isnan(shelly_switch_voltage.labels(**labels)._value.get())
        assert math.isnan(shelly_switch_temperature.labels(**labels)._value.get())

    def test_switch_metrics_ignore_flags(self) -> None:
        """Test that ignore flags prevent metric updates."""
        reading = ChannelReading(
            channel_type="switch",
            channel_index=2,
            output=1.0,
            voltage_v=120.0,
            temp_c=40.0,
        )

        channel_config = ChannelConfig(
            type="switch",
            index=2,
            ignore_voltage=True,
            ignore_temperature=True,
        )

        # Get initial values
        labels = {"device": "ignore_test", "meter": "2"}

        # Update should skip ignored metrics
        update_channel_metrics("ignore_test", reading, channel_config)

        # Output should be updated (not ignored)
        assert shelly_switch_output.labels(**labels)._value.get() == 1.0


class TestLightMetrics:
    """Tests for light channel metrics updates."""

    def test_update_light_metrics(self) -> None:
        """Test updating light metrics."""
        reading = ChannelReading(
            channel_type="light",
            channel_index=0,
            output=1.0,
            brightness=75.0,
            apower_w=18.5,
            aenergy_wh=567.89,
        )

        channel_config = ChannelConfig(type="light", index=0)
        update_channel_metrics("light_test", reading, channel_config)

        labels = {"device": "light_test", "channel": "0"}
        assert shelly_light_output.labels(**labels)._value.get() == 1.0
        assert shelly_light_brightness.labels(**labels)._value.get() == 75.0
        assert shelly_light_apower.labels(**labels)._value.get() == 18.5
        assert shelly_light_aenergy.labels(**labels)._value.get() == 567.89

    def test_light_metrics_with_none_values(self) -> None:
        """Test that None values are set as NaN for light metrics."""
        reading = ChannelReading(
            channel_type="light",
            channel_index=1,
            output=0.0,
            brightness=None,
            apower_w=None,
            aenergy_wh=None,
        )

        update_channel_metrics("light_nan_test", reading, None)

        labels = {"device": "light_nan_test", "channel": "1"}
        assert shelly_light_output.labels(**labels)._value.get() == 0.0
        assert math.isnan(shelly_light_brightness.labels(**labels)._value.get())
        assert math.isnan(shelly_light_apower.labels(**labels)._value.get())


class TestCombinedMetricsUpdate:
    """Tests for complete metrics update from DeviceReading."""

    def test_update_from_device_reading(self) -> None:
        """Test updating all metrics from a DeviceReading."""
        switch_reading = ChannelReading(
            channel_type="switch",
            channel_index=0,
            output=1.0,
            apower_w=100.0,
            voltage_v=120.0,
        )
        light_reading = ChannelReading(
            channel_type="light",
            channel_index=0,
            output=1.0,
            brightness=50.0,
        )

        device_reading = DeviceReading(
            device_name="combined_test",
            up=True,
            poll_duration_seconds=0.25,
            channels=[switch_reading, light_reading],
        )

        target_config = TargetConfig(
            name="combined_test",
            url="10.0.0.1",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="light", index=0),
            ],
        )

        update_metrics_from_reading(device_reading, target_config)

        # Check device metrics
        assert shelly_up.labels(device="combined_test")._value.get() == 1.0
        assert shelly_poll_duration.labels(device="combined_test")._value.get() == 0.25

        # Check switch metrics
        assert shelly_switch_output.labels(device="combined_test", meter="0")._value.get() == 1.0
        assert shelly_switch_apower.labels(device="combined_test", meter="0")._value.get() == 100.0

        # Check light metrics
        assert shelly_light_output.labels(device="combined_test", channel="0")._value.get() == 1.0
        assert (
            shelly_light_brightness.labels(device="combined_test", channel="0")._value.get()
            == 50.0
        )
