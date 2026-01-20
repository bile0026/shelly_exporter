"""Driver registry for automatic driver discovery and selection."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.drivers.base import DeviceDriver
from shelly_exporter.drivers.dimmer_0110vpm_g3 import Dimmer0110VPMG3Driver
from shelly_exporter.drivers.plugus_gen2 import PlugUSGen2Driver
from shelly_exporter.drivers.pro4pm_gen2 import Pro4PMGen2Driver
from shelly_exporter.drivers.s1pm_gen4 import Shelly1PMGen4Driver

logger = logging.getLogger(__name__)


class DriverRegistry:
    """Registry for device drivers.

    Supports automatic driver selection based on device info scoring.
    """

    def __init__(self) -> None:
        self._drivers: list[DeviceDriver] = []

    def register(self, driver: DeviceDriver) -> None:
        """Register a driver instance."""
        self._drivers.append(driver)
        logger.debug(f"Registered driver: {driver.driver_id} ({driver.driver_name})")

    def get_best_driver(self, device_info: dict[str, Any]) -> DeviceDriver | None:
        """Find the best matching driver for a device.

        Args:
            device_info: Result from Shelly.GetDeviceInfo RPC call

        Returns:
            Best matching driver, or None if no driver supports this device
        """
        best_driver: DeviceDriver | None = None
        best_score = 0

        for driver in self._drivers:
            try:
                score = driver.score(device_info)
                if score > best_score:
                    best_score = score
                    best_driver = driver
            except Exception as e:
                logger.warning(f"Error scoring driver {driver.driver_id}: {e}")

        if best_driver:
            logger.debug(
                f"Selected driver {best_driver.driver_id} (score={best_score}) "
                f"for device: gen={device_info.get('gen')}, app={device_info.get('app')}"
            )
        else:
            logger.warning(
                f"No driver found for device: gen={device_info.get('gen')}, "
                f"app={device_info.get('app')}, model={device_info.get('model')}"
            )

        return best_driver

    def list_drivers(self) -> list[DeviceDriver]:
        """Return list of all registered drivers."""
        return list(self._drivers)


# Global registry instance
_registry: DriverRegistry | None = None


def get_registry() -> DriverRegistry:
    """Get the global driver registry, creating it if needed."""
    global _registry
    if _registry is None:
        _registry = DriverRegistry()
        # Register all built-in drivers
        _registry.register(Pro4PMGen2Driver())
        _registry.register(Shelly1PMGen4Driver())
        _registry.register(PlugUSGen2Driver())
        _registry.register(Dimmer0110VPMG3Driver())
        logger.info(f"Initialized driver registry with {len(_registry._drivers)} drivers")
    return _registry
