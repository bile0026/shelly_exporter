"""Tests for driver selection and registry."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.drivers.base import DeviceDriver
from shelly_exporter.drivers.dimmer_0110vpm_g3 import Dimmer0110VPMG3Driver
from shelly_exporter.drivers.plugus_gen2 import PlugUSGen2Driver
from shelly_exporter.drivers.pro2pm_gen2 import Pro2PMGen2Driver
from shelly_exporter.drivers.pro4pm_gen2 import Pro4PMGen2Driver
from shelly_exporter.drivers.registry import DriverRegistry, get_registry
from shelly_exporter.drivers.s1pm_gen4 import Shelly1PMGen4Driver


class TestDriverRegistry:
    """Tests for the driver registry."""

    def test_registry_initialization(self) -> None:
        """Test that global registry is initialized with all drivers."""
        registry = get_registry()
        drivers = registry.list_drivers()

        # Should have 4 built-in drivers
        assert len(drivers) >= 4

        driver_ids = [d.driver_id for d in drivers]
        assert "pro2pm_gen2" in driver_ids
        assert "pro4pm_gen2" in driver_ids
        assert "s1pm_gen4" in driver_ids
        assert "plugus_gen2" in driver_ids
        assert "dimmer_0110vpm_g3" in driver_ids

    def test_custom_registry(self) -> None:
        """Test creating a custom registry."""
        registry = DriverRegistry()
        assert len(registry.list_drivers()) == 0

        registry.register(Pro4PMGen2Driver())
        assert len(registry.list_drivers()) == 1


class TestDriverSelection:
    """Tests for selecting the best driver for a device."""

    def test_select_pro2pm_driver(self, pro2pm_deviceinfo: dict[str, Any]) -> None:
        """Test Pro 2PM driver selection."""
        registry = get_registry()
        driver = registry.get_best_driver(pro2pm_deviceinfo)

        assert driver is not None
        assert driver.driver_id == "pro2pm_gen2"
        assert isinstance(driver, Pro2PMGen2Driver)

    def test_select_pro4pm_driver(self, pro4pm_deviceinfo: dict[str, Any]) -> None:
        """Test Pro 4PM driver selection."""
        registry = get_registry()
        driver = registry.get_best_driver(pro4pm_deviceinfo)

        assert driver is not None
        assert driver.driver_id == "pro4pm_gen2"
        assert isinstance(driver, Pro4PMGen2Driver)

    def test_select_s1pm_driver(self, s1pm_deviceinfo: dict[str, Any]) -> None:
        """Test 1PM Gen4 driver selection."""
        registry = get_registry()
        driver = registry.get_best_driver(s1pm_deviceinfo)

        assert driver is not None
        assert driver.driver_id == "s1pm_gen4"
        assert isinstance(driver, Shelly1PMGen4Driver)

    def test_select_plugus_driver(self, plugus_deviceinfo: dict[str, Any]) -> None:
        """Test Plug US driver selection."""
        registry = get_registry()
        driver = registry.get_best_driver(plugus_deviceinfo)

        assert driver is not None
        assert driver.driver_id == "plugus_gen2"
        assert isinstance(driver, PlugUSGen2Driver)

    def test_select_dimmer_driver(self, dimmer_deviceinfo: dict[str, Any]) -> None:
        """Test Dimmer driver selection."""
        registry = get_registry()
        driver = registry.get_best_driver(dimmer_deviceinfo)

        assert driver is not None
        assert driver.driver_id == "dimmer_0110vpm_g3"
        assert isinstance(driver, Dimmer0110VPMG3Driver)

    def test_no_driver_for_unknown_device(self) -> None:
        """Test that unknown devices return no driver."""
        registry = get_registry()
        unknown_device = {"gen": 99, "app": "UnknownApp", "model": "XXX-000000"}
        driver = registry.get_best_driver(unknown_device)
        assert driver is None


class TestDriverScoring:
    """Tests for driver scoring logic."""

    def test_pro4pm_scoring(self) -> None:
        """Test Pro 4PM driver scoring."""
        driver = Pro4PMGen2Driver()

        # Exact match
        assert driver.score({"gen": 2, "app": "Pro4PM"}) == 100

        # Wrong gen
        assert driver.score({"gen": 3, "app": "Pro4PM"}) == 0

        # Wrong app
        assert driver.score({"gen": 2, "app": "PlugUS"}) == 0

    def test_s1pm_scoring(self) -> None:
        """Test 1PM Gen4 driver scoring."""
        driver = Shelly1PMGen4Driver()

        assert driver.score({"gen": 4, "app": "S1PMG4"}) == 100
        assert driver.score({"gen": 2, "app": "S1PMG4"}) == 0

    def test_plugus_scoring(self) -> None:
        """Test Plug US driver scoring."""
        driver = PlugUSGen2Driver()

        assert driver.score({"gen": 2, "app": "PlugUS"}) == 100
        assert driver.score({"gen": 2, "app": "Pro4PM"}) == 0

    def test_dimmer_scoring(self) -> None:
        """Test Dimmer driver scoring."""
        driver = Dimmer0110VPMG3Driver()

        assert driver.score({"gen": 3, "app": "Dimmer0110VPMG3"}) == 100
        assert driver.score({"gen": 2, "app": "Dimmer0110VPMG3"}) == 0


class TestSupportedChannels:
    """Tests for supported channel detection."""

    def test_pro2pm_channels(self) -> None:
        """Test Pro 2PM supported channels."""
        driver = Pro2PMGen2Driver()
        channels = driver.supported_channels({})

        assert "switch" in channels
        assert channels["switch"] == {0, 1}
        assert "light" not in channels

    def test_pro4pm_channels(self) -> None:
        """Test Pro 4PM supported channels."""
        driver = Pro4PMGen2Driver()
        channels = driver.supported_channels({})

        assert "switch" in channels
        assert channels["switch"] == {0, 1, 2, 3}
        assert "light" not in channels

    def test_s1pm_channels(self) -> None:
        """Test 1PM Gen4 supported channels."""
        driver = Shelly1PMGen4Driver()
        channels = driver.supported_channels({})

        assert "switch" in channels
        assert channels["switch"] == {0}

    def test_plugus_channels(self) -> None:
        """Test Plug US supported channels."""
        driver = PlugUSGen2Driver()
        channels = driver.supported_channels({})

        assert "switch" in channels
        assert channels["switch"] == {0}

    def test_dimmer_channels(self) -> None:
        """Test Dimmer supported channels."""
        driver = Dimmer0110VPMG3Driver()
        channels = driver.supported_channels({})

        assert "light" in channels
        assert channels["light"] == {0}
        assert "switch" not in channels
