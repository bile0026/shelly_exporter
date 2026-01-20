"""Driver for Shelly BLU Gateway Gen2 devices."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceDriver

logger = logging.getLogger(__name__)


class BluGwGen2Driver(DeviceDriver):
    """Driver for Shelly BLU Gateway Gen2.

    Device info:
    - model: SNGW-BT01
    - gen: 2
    - app: BluGw

    This is a Bluetooth gateway device with no switch/light channels.
    It can run scripts and provides system/wifi/connection metrics.

    Status structure:
    - blugw: {} (gateway status, typically empty)
    - script:N: {id, running, mem_used, mem_peak, mem_free, cpu}
    - Standard sys, wifi, cloud, mqtt sections
    """

    @property
    def driver_id(self) -> str:
        return "blugw_gen2"

    @property
    def driver_name(self) -> str:
        return "Shelly BLU Gateway Gen2"

    def score(self, device_info: dict[str, Any]) -> int:
        """Score how well this driver matches the device."""
        gen = device_info.get("gen")
        app = device_info.get("app", "")

        # Exact match for BLU Gateway Gen2
        if gen == 2 and app == "BluGw":
            return 100

        return 0

    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """Return supported channel types and indices.

        BLU Gateway has no switch/light channels - it's a gateway device.
        Returns empty dict but device can still be monitored for system metrics.
        """
        return {}

    def parse_status(
        self, status_result: dict[str, Any], target_config: TargetConfig
    ) -> list[ChannelReading]:
        """Parse status into channel readings.

        BLU Gateway has no channels, returns empty list.
        System/wifi/connection metrics are handled by base class.
        """
        return []
