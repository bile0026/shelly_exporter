"""Driver for Shelly Pro 4PM Gen2 devices."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceDriver

logger = logging.getLogger(__name__)


class Pro4PMGen2Driver(DeviceDriver):
    """Driver for Shelly Pro 4PM Gen2.

    Device Info: model="SPSW-104PE16EU", gen=2, app="Pro4PM"
    Channels: switch:0, switch:1, switch:2, switch:3
    """

    @property
    def driver_id(self) -> str:
        return "pro4pm_gen2"

    @property
    def driver_name(self) -> str:
        return "Shelly Pro 4PM Gen2"

    def score(self, device_info: dict[str, Any]) -> int:
        """Score this driver for the device."""
        gen = device_info.get("gen")
        app = device_info.get("app", "")

        if gen == 2 and app == "Pro4PM":
            return 100  # Exact match
        return 0

    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """Pro 4PM has 4 switch channels."""
        return {"switch": {0, 1, 2, 3}}

    def parse_status(
        self,
        status_result: dict[str, Any],
        target_config: TargetConfig,
    ) -> list[ChannelReading]:
        """Parse Pro 4PM status into channel readings."""
        readings: list[ChannelReading] = []
        supported = self.supported_channels({})

        for channel_cfg in target_config.channels:
            if channel_cfg.type != "switch":
                logger.warning(
                    f"Target '{target_config.name}': Pro 4PM only supports switch channels, "
                    f"ignoring {channel_cfg.type}:{channel_cfg.index}"
                )
                continue

            idx = channel_cfg.index
            if idx not in supported.get("switch", set()):
                logger.warning(
                    f"Target '{target_config.name}': Channel index {idx} out of range for Pro 4PM "
                    f"(valid: 0-3), skipping"
                )
                continue

            switch_key = f"switch:{idx}"
            switch_data = status_result.get(switch_key, {})

            if not switch_data:
                logger.debug(f"Target '{target_config.name}': No data for {switch_key}")
                continue

            reading = self._parse_switch_channel(switch_data, idx)
            readings.append(reading)

        return readings
