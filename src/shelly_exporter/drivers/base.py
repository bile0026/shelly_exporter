"""Base driver interface and data models."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from shelly_exporter.config import TargetConfig


@dataclass
class ChannelReading:
    """Normalized reading from a device channel (switch or light)."""

    channel_type: str  # "switch" or "light"
    channel_index: int

    # Common fields
    output: float | None = None  # 1.0 for on, 0.0 for off, None if unknown

    # Power/energy fields (may be None/NaN if not available)
    apower_w: float | None = None
    voltage_v: float | None = None
    freq_hz: float | None = None
    current_a: float | None = None
    pf: float | None = None  # power factor
    temp_c: float | None = None
    aenergy_wh: float | None = None
    ret_aenergy_wh: float | None = None

    # Light-specific fields
    brightness: float | None = None  # 0-100 percent

    def get_value_or_nan(self, value: float | None) -> float:
        """Return value or NaN if None."""
        return value if value is not None else math.nan


@dataclass
class InputReading:
    """Reading from an input channel (physical button/switch)."""

    input_index: int
    state: float | None = None  # 1.0 for on/pressed, 0.0 for off


@dataclass
class SystemReading:
    """System-level metrics from the device."""

    uptime_seconds: float | None = None
    ram_size_bytes: float | None = None
    ram_free_bytes: float | None = None
    ram_min_free_bytes: float | None = None
    fs_size_bytes: float | None = None
    fs_free_bytes: float | None = None
    restart_required: float | None = None  # 1.0 if true, 0.0 if false
    cfg_rev: float | None = None
    unixtime: float | None = None


@dataclass
class WifiReading:
    """WiFi connection metrics."""

    rssi_dbm: float | None = None
    connected: float | None = None  # 1.0 if connected, 0.0 otherwise
    sta_ip: str | None = None
    ssid: str | None = None


@dataclass
class ConnectionStatus:
    """Cloud and MQTT connection status."""

    cloud_connected: float | None = None  # 1.0 if connected, 0.0 otherwise
    mqtt_connected: float | None = None  # 1.0 if connected, 0.0 otherwise


@dataclass
class DeviceReading:
    """Per-device reading metadata."""

    device_name: str
    up: bool = True
    poll_duration_seconds: float = 0.0
    error_message: str | None = None
    channels: list[ChannelReading] = field(default_factory=list)
    inputs: list[InputReading] = field(default_factory=list)
    system: SystemReading | None = None
    wifi: WifiReading | None = None
    connection: ConnectionStatus | None = None


class DeviceDriver(ABC):
    """Base class for Shelly device drivers.

    Implement this interface to add support for new Shelly device models.
    """

    @property
    @abstractmethod
    def driver_id(self) -> str:
        """Unique identifier for this driver (e.g., 'pro4pm_gen2')."""
        ...

    @property
    @abstractmethod
    def driver_name(self) -> str:
        """Human-readable name for this driver."""
        ...

    @abstractmethod
    def score(self, device_info: dict[str, Any]) -> int:
        """Score how well this driver matches the device.

        Args:
            device_info: Result from Shelly.GetDeviceInfo RPC call

        Returns:
            Score >= 1 if supported, 0 if not supported.
            Higher score means better match.
        """
        ...

    @abstractmethod
    def supported_channels(self, device_info: dict[str, Any]) -> dict[str, set[int]]:
        """Return supported channel types and indices.

        Args:
            device_info: Result from Shelly.GetDeviceInfo RPC call

        Returns:
            Dict mapping channel type to set of indices.
            Example: {"switch": {0, 1, 2, 3}} or {"light": {0}}
        """
        ...

    @abstractmethod
    def parse_status(
        self,
        status_result: dict[str, Any],
        target_config: TargetConfig,
    ) -> list[ChannelReading]:
        """Parse device status into normalized channel readings.

        Args:
            status_result: Result from Shelly.GetStatus RPC call
            target_config: Target configuration with channel settings

        Returns:
            List of ChannelReading objects for configured channels
        """
        ...

    def parse_system(self, status_result: dict[str, Any]) -> SystemReading | None:
        """Parse system metrics from status.

        Args:
            status_result: Result from Shelly.GetStatus RPC call

        Returns:
            SystemReading with system metrics, or None if not available
        """
        sys_data = status_result.get("sys", {})
        if not sys_data:
            return None

        restart_req = sys_data.get("restart_required")
        restart_val = None
        if restart_req is not None:
            restart_val = 1.0 if restart_req else 0.0

        return SystemReading(
            uptime_seconds=self._safe_float(sys_data.get("uptime")),
            ram_size_bytes=self._safe_float(sys_data.get("ram_size")),
            ram_free_bytes=self._safe_float(sys_data.get("ram_free")),
            ram_min_free_bytes=self._safe_float(sys_data.get("ram_min_free")),
            fs_size_bytes=self._safe_float(sys_data.get("fs_size")),
            fs_free_bytes=self._safe_float(sys_data.get("fs_free")),
            restart_required=restart_val,
            cfg_rev=self._safe_float(sys_data.get("cfg_rev")),
            unixtime=self._safe_float(sys_data.get("unixtime")),
        )

    def parse_wifi(self, status_result: dict[str, Any]) -> WifiReading | None:
        """Parse WiFi metrics from status.

        Args:
            status_result: Result from Shelly.GetStatus RPC call

        Returns:
            WifiReading with WiFi metrics, or None if not available
        """
        wifi_data = status_result.get("wifi", {})
        if not wifi_data:
            return None

        # Determine connected status from sta_ip or status field
        sta_ip = wifi_data.get("sta_ip")
        status = wifi_data.get("status", "")
        connected = 1.0 if (sta_ip or status == "got ip") else 0.0

        return WifiReading(
            rssi_dbm=self._safe_float(wifi_data.get("rssi")),
            connected=connected,
            sta_ip=sta_ip,
            ssid=wifi_data.get("ssid"),
        )

    def parse_connection_status(
        self, status_result: dict[str, Any]
    ) -> ConnectionStatus | None:
        """Parse cloud and MQTT connection status.

        Args:
            status_result: Result from Shelly.GetStatus RPC call

        Returns:
            ConnectionStatus with connection info
        """
        cloud_data = status_result.get("cloud", {})
        mqtt_data = status_result.get("mqtt", {})

        cloud_connected = None
        if isinstance(cloud_data, dict) and "connected" in cloud_data:
            cloud_connected = 1.0 if cloud_data["connected"] else 0.0

        mqtt_connected = None
        if isinstance(mqtt_data, dict) and "connected" in mqtt_data:
            mqtt_connected = 1.0 if mqtt_data["connected"] else 0.0

        if cloud_connected is None and mqtt_connected is None:
            return None

        return ConnectionStatus(
            cloud_connected=cloud_connected,
            mqtt_connected=mqtt_connected,
        )

    def parse_inputs(self, status_result: dict[str, Any]) -> list[InputReading]:
        """Parse input channel states from status.

        Args:
            status_result: Result from Shelly.GetStatus RPC call

        Returns:
            List of InputReading objects for all found inputs
        """
        inputs: list[InputReading] = []

        # Look for input:0, input:1, input:2, input:3, etc.
        for key, value in status_result.items():
            if key.startswith("input:") and isinstance(value, dict):
                try:
                    idx = int(key.split(":")[1])
                    state_val = value.get("state")
                    state = None
                    if state_val is not None:
                        state = 1.0 if state_val else 0.0
                    inputs.append(InputReading(input_index=idx, state=state))
                except (ValueError, IndexError):
                    continue

        # Sort by index for consistent ordering
        inputs.sort(key=lambda x: x.input_index)
        return inputs

    def _parse_switch_channel(
        self,
        switch_data: dict[str, Any],
        channel_index: int,
    ) -> ChannelReading:
        """Helper to parse common switch channel data."""
        output_val = switch_data.get("output")
        output = 1.0 if output_val else 0.0 if output_val is not None else None

        # Extract temperature, handling null values
        temp_c = None
        temp_data = switch_data.get("temperature", {})
        if isinstance(temp_data, dict):
            tc = temp_data.get("tC")
            if tc is not None:
                temp_c = float(tc)

        # Extract energy totals
        aenergy_wh = None
        aenergy_data = switch_data.get("aenergy", {})
        if isinstance(aenergy_data, dict):
            total = aenergy_data.get("total")
            if total is not None:
                aenergy_wh = float(total)

        ret_aenergy_wh = None
        ret_aenergy_data = switch_data.get("ret_aenergy", {})
        if isinstance(ret_aenergy_data, dict):
            total = ret_aenergy_data.get("total")
            if total is not None:
                ret_aenergy_wh = float(total)

        return ChannelReading(
            channel_type="switch",
            channel_index=channel_index,
            output=output,
            apower_w=self._safe_float(switch_data.get("apower")),
            voltage_v=self._safe_float(switch_data.get("voltage")),
            freq_hz=self._safe_float(switch_data.get("freq")),
            current_a=self._safe_float(switch_data.get("current")),
            pf=self._safe_float(switch_data.get("pf")),
            temp_c=temp_c,
            aenergy_wh=aenergy_wh,
            ret_aenergy_wh=ret_aenergy_wh,
        )

    def _parse_light_channel(
        self,
        light_data: dict[str, Any],
        channel_index: int,
    ) -> ChannelReading:
        """Helper to parse common light channel data."""
        output_val = light_data.get("output")
        output = 1.0 if output_val else 0.0 if output_val is not None else None

        brightness = self._safe_float(light_data.get("brightness"))

        # Extract temperature if available
        temp_c = None
        temp_data = light_data.get("temperature", {})
        if isinstance(temp_data, dict):
            tc = temp_data.get("tC")
            if tc is not None:
                temp_c = float(tc)

        # Extract energy totals if available
        aenergy_wh = None
        aenergy_data = light_data.get("aenergy", {})
        if isinstance(aenergy_data, dict):
            total = aenergy_data.get("total")
            if total is not None:
                aenergy_wh = float(total)

        return ChannelReading(
            channel_type="light",
            channel_index=channel_index,
            output=output,
            brightness=brightness,
            apower_w=self._safe_float(light_data.get("apower")),
            voltage_v=self._safe_float(light_data.get("voltage")),
            freq_hz=self._safe_float(light_data.get("freq")),
            current_a=self._safe_float(light_data.get("current")),
            pf=self._safe_float(light_data.get("pf")),
            temp_c=temp_c,
            aenergy_wh=aenergy_wh,
            ret_aenergy_wh=None,  # Lights typically don't return energy
        )

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Safely convert value to float, returning None if not possible."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
