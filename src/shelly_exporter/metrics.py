"""Prometheus metrics definitions and update logic."""

from __future__ import annotations

import logging
import math
import time

from prometheus_client import Counter, Gauge

from shelly_exporter.config import ChannelConfig, TargetConfig
from shelly_exporter.drivers.base import (
    ChannelReading,
    ConnectionStatus,
    DeviceReading,
    InputReading,
    SystemReading,
    WifiReading,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Per-device metrics
# =============================================================================
shelly_up = Gauge(
    "shelly_up",
    "Whether the Shelly device is up (1) or down (0)",
    ["device"],
)

shelly_last_poll_timestamp = Gauge(
    "shelly_last_poll_timestamp_seconds",
    "Unix timestamp of last successful poll",
    ["device"],
)

shelly_poll_duration = Gauge(
    "shelly_poll_duration_seconds",
    "Duration of last poll in seconds",
    ["device"],
)

shelly_poll_errors = Counter(
    "shelly_poll_errors_total",
    "Total number of poll errors",
    ["device"],
)

# =============================================================================
# System metrics
# =============================================================================
shelly_sys_uptime = Gauge(
    "shelly_sys_uptime_seconds",
    "Device uptime in seconds",
    ["device"],
)

shelly_sys_ram_size = Gauge(
    "shelly_sys_ram_size_bytes",
    "Total RAM size in bytes",
    ["device"],
)

shelly_sys_ram_free = Gauge(
    "shelly_sys_ram_free_bytes",
    "Free RAM in bytes",
    ["device"],
)

shelly_sys_ram_min_free = Gauge(
    "shelly_sys_ram_min_free_bytes",
    "Minimum free RAM since boot in bytes",
    ["device"],
)

shelly_sys_fs_size = Gauge(
    "shelly_sys_fs_size_bytes",
    "Total filesystem size in bytes",
    ["device"],
)

shelly_sys_fs_free = Gauge(
    "shelly_sys_fs_free_bytes",
    "Free filesystem space in bytes",
    ["device"],
)

shelly_sys_restart_required = Gauge(
    "shelly_sys_restart_required",
    "Whether a restart is required (1=yes, 0=no)",
    ["device"],
)

shelly_sys_cfg_rev = Gauge(
    "shelly_sys_cfg_rev",
    "Configuration revision number",
    ["device"],
)

# =============================================================================
# WiFi metrics
# =============================================================================
shelly_wifi_rssi = Gauge(
    "shelly_wifi_rssi_dbm",
    "WiFi signal strength in dBm",
    ["device"],
)

shelly_wifi_connected = Gauge(
    "shelly_wifi_connected",
    "WiFi connection status (1=connected, 0=disconnected)",
    ["device"],
)

# =============================================================================
# Connection status metrics
# =============================================================================
shelly_cloud_connected = Gauge(
    "shelly_cloud_connected",
    "Cloud connection status (1=connected, 0=disconnected)",
    ["device"],
)

shelly_mqtt_connected = Gauge(
    "shelly_mqtt_connected",
    "MQTT connection status (1=connected, 0=disconnected)",
    ["device"],
)

# =============================================================================
# Input channel metrics
# =============================================================================
shelly_input_state = Gauge(
    "shelly_input_state",
    "Input channel state (1=on/pressed, 0=off)",
    ["device", "input"],
)

# =============================================================================
# Switch channel metrics
# =============================================================================
shelly_switch_output = Gauge(
    "shelly_switch_output",
    "Switch output state (1=on, 0=off)",
    ["device", "meter"],
)

shelly_switch_apower = Gauge(
    "shelly_switch_apower_watts",
    "Active power in watts",
    ["device", "meter"],
)

shelly_switch_voltage = Gauge(
    "shelly_switch_voltage_volts",
    "Voltage in volts",
    ["device", "meter"],
)

shelly_switch_frequency = Gauge(
    "shelly_switch_frequency_hz",
    "Frequency in Hz",
    ["device", "meter"],
)

shelly_switch_current = Gauge(
    "shelly_switch_current_amps",
    "Current in amps",
    ["device", "meter"],
)

shelly_switch_power_factor = Gauge(
    "shelly_switch_power_factor",
    "Power factor (0-1)",
    ["device", "meter"],
)

shelly_switch_temperature = Gauge(
    "shelly_switch_temperature_c",
    "Temperature in Celsius",
    ["device", "meter"],
)

shelly_switch_aenergy = Gauge(
    "shelly_switch_aenergy_wh_total",
    "Total active energy in Wh",
    ["device", "meter"],
)

shelly_switch_ret_aenergy = Gauge(
    "shelly_switch_ret_aenergy_wh_total",
    "Total returned active energy in Wh",
    ["device", "meter"],
)

# =============================================================================
# Discovery/scanning metrics
# =============================================================================
shelly_discovery_scans_total = Counter(
    "shelly_discovery_scans_total",
    "Total number of network scans performed",
)

shelly_discovery_devices_found_total = Counter(
    "shelly_discovery_devices_found_total",
    "Total devices discovered across all scans",
)

shelly_discovery_scan_duration = Gauge(
    "shelly_discovery_scan_duration_seconds",
    "Duration of last scan in seconds",
)

shelly_discovery_last_scan_timestamp = Gauge(
    "shelly_discovery_last_scan_timestamp_seconds",
    "Unix timestamp of last scan",
)

shelly_discovery_scan_errors = Counter(
    "shelly_discovery_scan_errors_total",
    "Total scan errors",
)

shelly_discovered_device_info = Gauge(
    "shelly_discovered_device_info",
    "Info about discovered devices (value=1)",
    ["ip", "model", "gen", "app", "mac", "discovered_at"],
)

# =============================================================================
# Configuration reload metrics
# =============================================================================
shelly_config_reloads_total = Counter(
    "shelly_config_reloads_total",
    "Total number of successful config reloads",
)

shelly_config_reload_errors_total = Counter(
    "shelly_config_reload_errors_total",
    "Total number of failed config reload attempts",
)

shelly_config_last_reload_timestamp = Gauge(
    "shelly_config_last_reload_timestamp_seconds",
    "Unix timestamp of last successful config reload",
)

shelly_config_last_reload_status = Gauge(
    "shelly_config_last_reload_status",
    "Status of last reload attempt (1=success, 0=failure)",
)

# =============================================================================
# Light channel metrics
# =============================================================================
shelly_light_output = Gauge(
    "shelly_light_output",
    "Light output state (1=on, 0=off)",
    ["device", "channel"],
)

shelly_light_brightness = Gauge(
    "shelly_light_brightness_percent",
    "Light brightness percentage (0-100)",
    ["device", "channel"],
)

shelly_light_apower = Gauge(
    "shelly_light_apower_watts",
    "Light active power in watts",
    ["device", "channel"],
)

shelly_light_aenergy = Gauge(
    "shelly_light_aenergy_wh_total",
    "Light total active energy in Wh",
    ["device", "channel"],
)

shelly_light_voltage = Gauge(
    "shelly_light_voltage_volts",
    "Light voltage in volts",
    ["device", "channel"],
)

shelly_light_current = Gauge(
    "shelly_light_current_amps",
    "Light current in amps",
    ["device", "channel"],
)

shelly_light_temperature = Gauge(
    "shelly_light_temperature_c",
    "Light temperature in Celsius",
    ["device", "channel"],
)


# =============================================================================
# Helper functions
# =============================================================================
def _get_channel_config(
    target_config: TargetConfig,
    channel_type: str,
    channel_index: int,
) -> ChannelConfig | None:
    """Find channel config matching type and index."""
    for ch in target_config.channels:
        if ch.type == channel_type and ch.index == channel_index:
            return ch
    return None


def _set_gauge_value(
    gauge: Gauge, labels: dict[str, str], value: float | None
) -> None:
    """Set gauge value, using NaN for None values."""
    if value is None:
        gauge.labels(**labels).set(math.nan)
    else:
        gauge.labels(**labels).set(value)


# =============================================================================
# Update functions
# =============================================================================
def update_device_metrics(reading: DeviceReading) -> None:
    """Update per-device metrics from a reading."""
    device = reading.device_name

    # Update device-level metrics
    shelly_up.labels(device=device).set(1.0 if reading.up else 0.0)
    shelly_poll_duration.labels(device=device).set(reading.poll_duration_seconds)

    if reading.up:
        shelly_last_poll_timestamp.labels(device=device).set(time.time())

    if not reading.up and reading.error_message:
        shelly_poll_errors.labels(device=device).inc()
        logger.warning(f"Device '{device}' poll failed: {reading.error_message}")


def update_system_metrics(device_name: str, system: SystemReading) -> None:
    """Update system metrics from a SystemReading."""
    labels = {"device": device_name}

    _set_gauge_value(shelly_sys_uptime, labels, system.uptime_seconds)
    _set_gauge_value(shelly_sys_ram_size, labels, system.ram_size_bytes)
    _set_gauge_value(shelly_sys_ram_free, labels, system.ram_free_bytes)
    _set_gauge_value(shelly_sys_ram_min_free, labels, system.ram_min_free_bytes)
    _set_gauge_value(shelly_sys_fs_size, labels, system.fs_size_bytes)
    _set_gauge_value(shelly_sys_fs_free, labels, system.fs_free_bytes)
    _set_gauge_value(shelly_sys_restart_required, labels, system.restart_required)
    _set_gauge_value(shelly_sys_cfg_rev, labels, system.cfg_rev)


def update_wifi_metrics(device_name: str, wifi: WifiReading) -> None:
    """Update WiFi metrics from a WifiReading."""
    labels = {"device": device_name}

    _set_gauge_value(shelly_wifi_rssi, labels, wifi.rssi_dbm)
    _set_gauge_value(shelly_wifi_connected, labels, wifi.connected)


def update_connection_metrics(
    device_name: str, connection: ConnectionStatus
) -> None:
    """Update connection status metrics."""
    labels = {"device": device_name}

    _set_gauge_value(shelly_cloud_connected, labels, connection.cloud_connected)
    _set_gauge_value(shelly_mqtt_connected, labels, connection.mqtt_connected)


def update_input_metrics(device_name: str, inputs: list[InputReading]) -> None:
    """Update input channel metrics."""
    for inp in inputs:
        labels = {"device": device_name, "input": str(inp.input_index)}
        _set_gauge_value(shelly_input_state, labels, inp.state)


def update_channel_metrics(
    device_name: str,
    reading: ChannelReading,
    channel_config: ChannelConfig | None,
) -> None:
    """Update channel-specific metrics from a reading.

    Args:
        device_name: Device identifier
        reading: Channel reading data
        channel_config: Optional channel config for ignore flags
    """
    if reading.channel_type == "switch":
        _update_switch_metrics(device_name, reading, channel_config)
    elif reading.channel_type == "light":
        _update_light_metrics(device_name, reading, channel_config)
    else:
        logger.warning(f"Unknown channel type: {reading.channel_type}")


def _update_switch_metrics(
    device_name: str,
    reading: ChannelReading,
    channel_config: ChannelConfig | None,
) -> None:
    """Update switch channel metrics."""
    labels = {"device": device_name, "meter": str(reading.channel_index)}
    # Add channel label if provided
    if channel_config and channel_config.label:
        labels["label"] = channel_config.label

    # Check ignore flags from config
    ignore = channel_config or ChannelConfig()

    if not ignore.ignore_output:
        _set_gauge_value(shelly_switch_output, labels, reading.output)

    if not ignore.ignore_active_power:
        _set_gauge_value(shelly_switch_apower, labels, reading.apower_w)

    if not ignore.ignore_voltage:
        _set_gauge_value(shelly_switch_voltage, labels, reading.voltage_v)

    if not ignore.ignore_frequency:
        _set_gauge_value(shelly_switch_frequency, labels, reading.freq_hz)

    if not ignore.ignore_current:
        _set_gauge_value(shelly_switch_current, labels, reading.current_a)

    if not ignore.ignore_power_factor:
        _set_gauge_value(shelly_switch_power_factor, labels, reading.pf)

    if not ignore.ignore_temperature:
        _set_gauge_value(shelly_switch_temperature, labels, reading.temp_c)

    if not ignore.ignore_total_active_energy:
        _set_gauge_value(shelly_switch_aenergy, labels, reading.aenergy_wh)

    if not ignore.ignore_total_returned_active_energy:
        _set_gauge_value(shelly_switch_ret_aenergy, labels, reading.ret_aenergy_wh)


def _update_light_metrics(
    device_name: str,
    reading: ChannelReading,
    channel_config: ChannelConfig | None,
) -> None:
    """Update light channel metrics."""
    labels = {"device": device_name, "channel": str(reading.channel_index)}
    # Add channel label if provided
    if channel_config and channel_config.label:
        labels["label"] = channel_config.label

    # Check ignore flags from config
    ignore = channel_config or ChannelConfig()

    if not ignore.ignore_output:
        _set_gauge_value(shelly_light_output, labels, reading.output)

    if not ignore.ignore_brightness:
        _set_gauge_value(shelly_light_brightness, labels, reading.brightness)

    if not ignore.ignore_active_power:
        _set_gauge_value(shelly_light_apower, labels, reading.apower_w)

    if not ignore.ignore_total_active_energy:
        _set_gauge_value(shelly_light_aenergy, labels, reading.aenergy_wh)

    if not ignore.ignore_voltage:
        _set_gauge_value(shelly_light_voltage, labels, reading.voltage_v)

    if not ignore.ignore_current:
        _set_gauge_value(shelly_light_current, labels, reading.current_a)

    if not ignore.ignore_temperature:
        _set_gauge_value(shelly_light_temperature, labels, reading.temp_c)


def update_metrics_from_reading(
    reading: DeviceReading,
    target_config: TargetConfig,
) -> None:
    """Update all metrics from a device reading.

    Args:
        reading: Complete device reading with channels
        target_config: Target configuration for ignore flags
    """
    # Update device-level metrics
    update_device_metrics(reading)

    # Update system metrics
    if reading.system:
        update_system_metrics(reading.device_name, reading.system)

    # Update WiFi metrics
    if reading.wifi:
        update_wifi_metrics(reading.device_name, reading.wifi)

    # Update connection status metrics
    if reading.connection:
        update_connection_metrics(reading.device_name, reading.connection)

    # Update input metrics
    if reading.inputs:
        update_input_metrics(reading.device_name, reading.inputs)

    # Update channel metrics
    for channel_reading in reading.channels:
        channel_config = _get_channel_config(
            target_config,
            channel_reading.channel_type,
            channel_reading.channel_index,
        )
        update_channel_metrics(
            reading.device_name,
            channel_reading,
            channel_config,
        )


# =============================================================================
# Discovery metrics update functions
# =============================================================================
def update_discovery_scan_started() -> None:
    """Record that a discovery scan has started."""
    shelly_discovery_scans_total.inc()


def update_discovery_scan_completed(duration_seconds: float) -> None:
    """Record completion of a discovery scan."""
    shelly_discovery_scan_duration.set(duration_seconds)
    shelly_discovery_last_scan_timestamp.set(time.time())


def update_discovery_device_found(
    ip: str,
    model: str,
    gen: int,
    app: str,
    mac: str,
    discovered_at: str,
) -> None:
    """Record a discovered device."""
    shelly_discovery_devices_found_total.inc()
    shelly_discovered_device_info.labels(
        ip=ip,
        model=model,
        gen=str(gen),
        app=app,
        mac=mac,
        discovered_at=discovered_at,
    ).set(1)


def update_discovery_scan_error() -> None:
    """Record a scan error."""
    shelly_discovery_scan_errors.inc()


# =============================================================================
# Config reload metrics update functions
# =============================================================================
def update_config_reload_success() -> None:
    """Record a successful config reload."""
    shelly_config_reloads_total.inc()
    shelly_config_last_reload_timestamp.set(time.time())
    shelly_config_last_reload_status.set(1)


def update_config_reload_error() -> None:
    """Record a failed config reload attempt."""
    shelly_config_reload_errors_total.inc()
    shelly_config_last_reload_status.set(0)
