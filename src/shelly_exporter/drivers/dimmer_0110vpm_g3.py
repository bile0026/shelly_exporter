"""Driver for Shelly Dimmer 0/1-10V PM Gen3 devices."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceDriver

logger = logging.getLogger(__name__)


class Dimmer0110VPMG3Driver(DeviceDriver):
    """Driver for Shelly Dimmer 0/1-10V PM Gen3.

    Device Info: model="S3DM-0010WW", gen=3, app="Dimmer0110VPMG3"
    Channels: light:0 (NOT switch!)
    """

    @property
    def driver_id(self) -> str:
        return "dimmer_0110vpm_g3"

    @property
    def driver_name(self) -> str:
        return "Shelly Dimmer 0/1-10V PM Gen3"

    def score(self, device_info: dict[str, Any]) -> int:
        """Score this driver for the device."""
        gen = device_info.get("gen")
        app = device_info.get("app", "")

        if gen == 3 and app == "Dimmer0110VPMG3":
            return 100  # Exact match
        return 0

    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """Dimmer has 1 light channel."""
        return {"light": {0}}

    def parse_status(
        self,
        status_result: dict[str, Any],
        target_config: TargetConfig,
    ) -> list[ChannelReading]:
        """Parse Dimmer status into channel readings."""
        readings: list[ChannelReading] = []
        supported = self.supported_channels({})

        for channel_cfg in target_config.channels:
            if channel_cfg.type != "light":
                logger.warning(
                    f"Target '{target_config.name}': Dimmer only supports light channels, "
                    f"ignoring {channel_cfg.type}:{channel_cfg.index}"
                )
                continue

            idx = channel_cfg.index
            if idx not in supported.get("light", set()):
                logger.warning(
                    f"Target '{target_config.name}': Channel index {idx} out of range for Dimmer "
                    f"(valid: 0), skipping"
                )
                continue

            light_key = f"light:{idx}"
            light_data = status_result.get(light_key, {})

            if not light_data:
                logger.debug(f"Target '{target_config.name}': No data for {light_key}")
                continue

            reading = self._parse_light_channel(light_data, idx)
            readings.append(reading)

        return readings
