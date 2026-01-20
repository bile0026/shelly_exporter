"""Driver for Shelly 1PM Gen4 devices."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceDriver

logger = logging.getLogger(__name__)


class Shelly1PMGen4Driver(DeviceDriver):
    """Driver for Shelly 1PM Gen4.

    Device Info: model="S4SW-001P16EU", gen=4, app="S1PMG4"
    Channels: switch:0
    Note: May not include pf; temperature.tC/tF may be null
    """

    @property
    def driver_id(self) -> str:
        return "s1pm_gen4"

    @property
    def driver_name(self) -> str:
        return "Shelly 1PM Gen4"

    def score(self, device_info: dict[str, Any]) -> int:
        """Score this driver for the device."""
        gen = device_info.get("gen")
        app = device_info.get("app", "")

        if gen == 4 and app == "S1PMG4":
            return 100  # Exact match
        return 0

    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """1PM Gen4 has 1 switch channel."""
        return {"switch": {0}}

    def parse_status(
        self,
        status_result: dict[str, Any],
        target_config: TargetConfig,
    ) -> list[ChannelReading]:
        """Parse 1PM Gen4 status into channel readings."""
        readings: list[ChannelReading] = []
        supported = self.supported_channels({})

        for channel_cfg in target_config.channels:
            if channel_cfg.type != "switch":
                logger.warning(
                    f"Target '{target_config.name}': 1PM Gen4 only supports switch channels, "
                    f"ignoring {channel_cfg.type}:{channel_cfg.index}"
                )
                continue

            idx = channel_cfg.index
            if idx not in supported.get("switch", set()):
                logger.warning(
                    f"Target '{target_config.name}': Channel index {idx} out of range for 1PM Gen4 "
                    f"(valid: 0), skipping"
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
