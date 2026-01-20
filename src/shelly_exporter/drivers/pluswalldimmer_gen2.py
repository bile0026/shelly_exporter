"""Driver for Shelly Plus Wall Dimmer US Gen2 devices."""

from __future__ import annotations

import logging
from typing import Any

from shelly_exporter.config import TargetConfig
from shelly_exporter.drivers.base import ChannelReading, DeviceDriver

logger = logging.getLogger(__name__)


class PlusWallDimmerGen2Driver(DeviceDriver):
    """Driver for Shelly Plus Wall Dimmer US Gen2.

    Device info:
    - model: SNDM-0013US
    - gen: 2
    - app: PlusWallDimmer

    Status structure:
    - light:0: {id, source, output, brightness}
    - No power metering (no apower, voltage, current, etc.)
    """

    @property
    def driver_id(self) -> str:
        return "pluswalldimmer_gen2"

    @property
    def driver_name(self) -> str:
        return "Shelly Plus Wall Dimmer US Gen2"

    def score(self, device_info: dict[str, Any]) -> int:
        """Score how well this driver matches the device."""
        gen = device_info.get("gen")
        app = device_info.get("app", "")

        # Exact match for Plus Wall Dimmer Gen2
        if gen == 2 and app == "PlusWallDimmer":
            return 100

        return 0

    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """Return supported channel types and indices."""
        return {"light": {0}}

    def parse_status(
        self, status_result: dict[str, Any], target_config: TargetConfig
    ) -> list[ChannelReading]:
        """Parse status into channel readings."""
        readings: list[ChannelReading] = []

        for channel in target_config.channels:
            if channel.type != "light":
                logger.debug(
                    f"Skipping non-light channel type '{channel.type}' for Wall Dimmer"
                )
                continue

            key = f"light:{channel.index}"
            if key not in status_result:
                logger.warning(f"Channel {key} not found in status")
                continue

            light_data = status_result[key]

            # Parse output state
            output = None
            if not channel.ignore_output:
                raw_output = light_data.get("output")
                if raw_output is not None:
                    output = 1.0 if raw_output else 0.0

            # Parse brightness
            brightness = None
            if not channel.ignore_brightness:
                brightness = light_data.get("brightness")
                if brightness is not None:
                    brightness = float(brightness)

            readings.append(
                ChannelReading(
                    channel_type="light",
                    channel_index=channel.index,
                    output=output,
                    brightness=brightness,
                    # No power metering on this device
                    apower_w=None,
                    voltage_v=None,
                    freq_hz=None,
                    current_a=None,
                    pf=None,
                    temp_c=None,
                    aenergy_wh=None,
                    ret_aenergy_wh=None,
                )
            )

        return readings
