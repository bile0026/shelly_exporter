"""Tests for configuration loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from shelly_exporter.config import (
    ChannelConfig,
    Config,
    Credentials,
    LogLevel,
    TargetConfig,
    load_config,
)


class TestConfigModels:
    """Tests for config model validation."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = Config()
        assert config.log_level == LogLevel.INFO
        assert config.listen_host == "0.0.0.0"
        assert config.listen_port == 10037
        assert config.poll_interval_seconds == 10
        assert config.request_timeout_seconds == 3
        assert config.max_concurrency == 50
        assert not config.default_credentials.has_credentials()
        assert config.targets == []

    def test_credentials_has_credentials(self) -> None:
        """Test credentials detection."""
        empty = Credentials()
        assert not empty.has_credentials()

        with_user = Credentials(username="admin")
        assert with_user.has_credentials()

        with_pass = Credentials(password="secret")
        assert with_pass.has_credentials()

        with_both = Credentials(username="admin", password="secret")
        assert with_both.has_credentials()

    def test_channel_config_defaults(self) -> None:
        """Test default channel config values."""
        channel = ChannelConfig()
        assert channel.type == "switch"
        assert channel.index == 0
        assert not channel.ignore_voltage
        assert not channel.ignore_current
        assert not channel.ignore_output

    def test_target_config(self) -> None:
        """Test target configuration."""
        target = TargetConfig(
            name="test_device",
            url="192.168.1.100",
            channels=[
                ChannelConfig(type="switch", index=0),
                ChannelConfig(type="switch", index=1),
            ],
        )
        assert target.name == "test_device"
        assert target.url == "192.168.1.100"
        assert target.poll_interval_seconds is None
        assert len(target.channels) == 2

    def test_get_target_credentials_hierarchy(self) -> None:
        """Test credential resolution: target > default > none."""
        default_creds = Credentials(username="default_user", password="default_pass")
        target_creds = Credentials(username="target_user", password="target_pass")

        config = Config(default_credentials=default_creds)

        # Target with credentials uses target credentials
        target_with_creds = TargetConfig(
            name="t1",
            url="10.0.0.1",
            credentials=target_creds,
        )
        creds = config.get_target_credentials(target_with_creds)
        assert creds is not None
        assert creds.username == "target_user"

        # Target without credentials uses default
        target_no_creds = TargetConfig(name="t2", url="10.0.0.2")
        creds = config.get_target_credentials(target_no_creds)
        assert creds is not None
        assert creds.username == "default_user"

        # No default credentials returns None
        config_no_default = Config()
        creds = config_no_default.get_target_credentials(target_no_creds)
        assert creds is None

    def test_get_target_poll_interval(self) -> None:
        """Test poll interval resolution."""
        config = Config(poll_interval_seconds=10)

        # Target with override uses override
        target_with_override = TargetConfig(
            name="t1",
            url="10.0.0.1",
            poll_interval_seconds=5,
        )
        assert config.get_target_poll_interval(target_with_override) == 5

        # Target without override uses global
        target_no_override = TargetConfig(name="t2", url="10.0.0.2")
        assert config.get_target_poll_interval(target_no_override) == 10


class TestLegacyTargetMeters:
    """Tests for backward compatibility with target_meters."""

    def test_target_meters_conversion(self) -> None:
        """Test that target_meters is converted to channels."""
        data = {
            "name": "legacy_device",
            "url": "10.0.0.1",
            "target_meters": [0, 1, 2],
        }
        target = TargetConfig.model_validate(data)
        assert len(target.channels) == 3
        assert all(ch.type == "switch" for ch in target.channels)
        assert [ch.index for ch in target.channels] == [0, 1, 2]


class TestConfigLoading:
    """Tests for loading config from YAML files."""

    def test_load_valid_config(self) -> None:
        """Test loading a valid configuration file."""
        config_data = {
            "log_level": "DEBUG",
            "listen_port": 9999,
            "poll_interval_seconds": 15,
            "default_credentials": {
                "username": "admin",
                "password": "secret",
            },
            "targets": [
                {
                    "name": "test_device",
                    "url": "192.168.1.100",
                    "channels": [{"type": "switch", "index": 0}],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_data, f)
            f.flush()
            config = load_config(f.name)

        assert config.log_level == LogLevel.DEBUG
        assert config.listen_port == 9999
        assert config.poll_interval_seconds == 15
        assert config.default_credentials.username == "admin"
        assert len(config.targets) == 1
        assert config.targets[0].name == "test_device"

    def test_load_missing_file(self) -> None:
        """Test that missing config file raises error."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yml")

    def test_load_empty_file(self) -> None:
        """Test loading empty config file uses defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("")
            f.flush()
            config = load_config(f.name)

        assert config.log_level == LogLevel.INFO
        assert config.targets == []

    def test_load_config_with_per_target_options(self) -> None:
        """Test loading config with per-target customization."""
        config_data = {
            "targets": [
                {
                    "name": "custom_device",
                    "url": "10.0.0.1",
                    "poll_interval_seconds": 5,
                    "credentials": {"username": "user1", "password": "pass1"},
                    "channels": [
                        {
                            "type": "switch",
                            "index": 0,
                            "ignore_voltage": True,
                            "ignore_temperature": True,
                        }
                    ],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(config_data, f)
            f.flush()
            config = load_config(f.name)

        target = config.targets[0]
        assert target.poll_interval_seconds == 5
        assert target.credentials is not None
        assert target.credentials.username == "user1"
        assert target.channels[0].ignore_voltage is True
        assert target.channels[0].ignore_temperature is True
