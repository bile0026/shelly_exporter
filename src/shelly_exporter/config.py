"""Configuration models using Pydantic v2."""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Credentials(BaseModel):
    """Authentication credentials for a Shelly device."""

    username: str = ""
    password: str = ""

    def has_credentials(self) -> bool:
        return bool(self.username or self.password)


class ChannelConfig(BaseModel):
    """Configuration for a single channel (switch or light)."""

    type: str = "switch"
    index: int = 0
    ignore_voltage: bool = False
    ignore_current: bool = False
    ignore_active_power: bool = False
    ignore_power_factor: bool = False
    ignore_frequency: bool = False
    ignore_total_active_energy: bool = False
    ignore_total_returned_active_energy: bool = False
    ignore_temperature: bool = False
    ignore_output: bool = False
    ignore_brightness: bool = False

    @field_validator("index", mode="before")
    @classmethod
    def normalize_index(cls, v: int) -> int:
        """Normalize 1-based indices to 0-based with a warning."""
        if v >= 1 and v <= 4:
            # Check if this looks like a 1-based index
            # We'll handle the warning at the target level
            pass
        return v


class TargetConfig(BaseModel):
    """Configuration for a single Shelly device target."""

    name: str
    url: str
    poll_interval_seconds: int | None = None
    credentials: Credentials | None = None
    channels: list[ChannelConfig] = Field(default_factory=list)
    discovered: bool = False  # True if this target was auto-discovered

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_target_meters(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Handle backward compatibility with target_meters key."""
        if isinstance(data, dict) and "target_meters" in data:
            meters = data.pop("target_meters")
            channels = data.get("channels", [])
            for meter in meters:
                if isinstance(meter, int):
                    channels.append({"type": "switch", "index": meter})
                elif isinstance(meter, dict):
                    meter.setdefault("type", "switch")
                    channels.append(meter)
            data["channels"] = channels
            logging.warning(
                f"Target '{data.get('name', 'unknown')}' uses deprecated 'target_meters'. "
                "Please migrate to 'channels' with type 'switch'."
            )
        return data


class DiscoveryConfig(BaseModel):
    """Configuration for network scanning and auto-discovery."""

    enabled: bool = False
    scan_interval_seconds: int = 3600  # 1 hour
    network_ranges: list[str] = Field(default_factory=list)
    scan_timeout_seconds: float = 2.0
    scan_concurrency: int = 20
    auto_add_discovered: bool = True
    auto_add_credentials: Credentials | None = None
    exclude_ips: list[str] = Field(default_factory=list)
    name_template: str = "shelly_{ip}_{model}"
    persist_path: str | None = None  # Path to save discovered devices (e.g., /config/discovered.yml)


class Config(BaseModel):
    """Main application configuration."""

    log_level: LogLevel = LogLevel.INFO
    listen_host: str = "0.0.0.0"
    listen_port: int = 10037
    poll_interval_seconds: int = 10
    request_timeout_seconds: int = 3
    max_concurrency: int = 50
    default_credentials: Credentials = Field(default_factory=Credentials)
    targets: list[TargetConfig] = Field(default_factory=list)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)

    # Device info refresh interval (seconds) - how often to re-fetch device info
    device_info_refresh_seconds: int = 21600  # 6 hours

    # Backoff settings for failed polls
    backoff_base_seconds: float = 30.0
    backoff_max_seconds: float = 300.0  # 5 minutes
    backoff_multiplier: float = 2.0

    def get_target_credentials(self, target: TargetConfig) -> Credentials | None:
        """Get effective credentials for a target (target > default > none)."""
        if target.credentials and target.credentials.has_credentials():
            return target.credentials
        if self.default_credentials.has_credentials():
            return self.default_credentials
        return None

    def get_target_poll_interval(self, target: TargetConfig) -> int:
        """Get effective poll interval for a target."""
        return target.poll_interval_seconds or self.poll_interval_seconds

    def get_discovery_credentials(self) -> Credentials | None:
        """Get credentials to use for discovered devices."""
        if self.discovery.auto_add_credentials:
            if self.discovery.auto_add_credentials.has_credentials():
                return self.discovery.auto_add_credentials
        if self.default_credentials.has_credentials():
            return self.default_credentials
        return None


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses CONFIG_PATH env var
                    or defaults to /config/config.yml

    Returns:
        Validated Config object
    """
    if config_path is None:
        config_path = os.environ.get("CONFIG_PATH", "/config/config.yml")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    return Config.model_validate(data or {})
