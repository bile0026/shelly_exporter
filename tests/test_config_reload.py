"""Tests for configuration hot-reload functionality."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from shelly_exporter.config import Config, TargetConfig
from shelly_exporter.config_watcher import ConfigFileHandler, ConfigWatcher
from shelly_exporter.poller import DevicePoller


class TestConfigFileHandler:
    """Tests for ConfigFileHandler class."""

    def test_handler_init(self) -> None:
        """Test handler initialization."""
        callback = MagicMock()
        handler = ConfigFileHandler(
            config_path=Path("/tmp/test.yml"),
            callback=callback,
            debounce_seconds=2.0,
        )

        assert handler.config_filename == "test.yml"
        assert handler.debounce_seconds == 2.0
        assert handler._pending_reload is None

    def test_on_modified_ignores_directories(self) -> None:
        """Test that directory events are ignored."""
        callback = MagicMock()
        handler = ConfigFileHandler(
            config_path=Path("/tmp/config.yml"),
            callback=callback,
        )

        event = MagicMock()
        event.is_directory = True

        handler.on_modified(event)
        callback.assert_not_called()

    def test_on_modified_ignores_other_files(self) -> None:
        """Test that modifications to other files are ignored."""
        callback = MagicMock()
        handler = ConfigFileHandler(
            config_path=Path("/tmp/config.yml"),
            callback=callback,
        )
        loop = asyncio.new_event_loop()
        handler.set_loop(loop)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/other_file.yml"

        handler.on_modified(event)
        # No pending reload scheduled for other files
        assert handler._pending_reload is None
        loop.close()


class TestConfigWatcher:
    """Tests for ConfigWatcher class."""

    @pytest.fixture
    def temp_config_file(self) -> Path:
        """Create a temporary config file."""
        config_data = {
            "targets": [
                {"name": "device1", "url": "10.0.0.1", "channels": []},
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            return Path(f.name)

    async def test_watcher_start_loads_initial_config(
        self, temp_config_file: Path
    ) -> None:
        """Test that starting the watcher loads initial config."""
        watcher = ConfigWatcher(config_path=temp_config_file)

        try:
            await watcher.start()

            assert watcher.current_config is not None
            assert len(watcher.current_config.targets) == 1
            assert watcher.current_config.targets[0].name == "device1"
        finally:
            await watcher.stop()

    async def test_watcher_force_reload(self, temp_config_file: Path) -> None:
        """Test force_reload method."""
        reload_callback = AsyncMock()
        watcher = ConfigWatcher(
            config_path=temp_config_file,
            on_reload=reload_callback,
        )

        try:
            await watcher.start()

            # Modify the config file
            config_data = {
                "targets": [
                    {"name": "device1", "url": "10.0.0.1", "channels": []},
                    {"name": "device2", "url": "10.0.0.2", "channels": []},
                ],
            }
            with open(temp_config_file, "w") as f:
                yaml.dump(config_data, f)

            # Force reload
            result = await watcher.force_reload()

            assert result is True
            assert watcher.current_config is not None
            assert len(watcher.current_config.targets) == 2
            reload_callback.assert_called_once()
        finally:
            await watcher.stop()

    async def test_watcher_reload_with_invalid_config(
        self, temp_config_file: Path
    ) -> None:
        """Test that invalid config is rejected and old config preserved."""
        watcher = ConfigWatcher(config_path=temp_config_file)

        try:
            await watcher.start()
            original_config = watcher.current_config

            # Write invalid YAML
            with open(temp_config_file, "w") as f:
                f.write("invalid: yaml: content: [")

            # Force reload should fail
            result = await watcher.force_reload()

            assert result is False
            # Original config should be preserved
            assert watcher.current_config == original_config
        finally:
            await watcher.stop()

    async def test_watcher_callback_error_restores_config(
        self, temp_config_file: Path
    ) -> None:
        """Test that callback errors restore previous config."""

        async def failing_callback(config: Config) -> None:
            raise ValueError("Callback failed")

        watcher = ConfigWatcher(
            config_path=temp_config_file,
            on_reload=failing_callback,
        )

        try:
            await watcher.start()
            original_config = watcher.current_config

            # Modify the config file
            config_data = {
                "targets": [
                    {"name": "new_device", "url": "10.0.0.99", "channels": []},
                ],
            }
            with open(temp_config_file, "w") as f:
                yaml.dump(config_data, f)

            # Force reload should fail due to callback
            result = await watcher.force_reload()

            assert result is False
            # Original config should be restored
            assert watcher.current_config == original_config
        finally:
            await watcher.stop()


class TestPollerConfigUpdate:
    """Tests for DevicePoller config update functionality."""

    @pytest.fixture
    def base_config(self) -> Config:
        """Create a base configuration."""
        return Config(
            targets=[
                TargetConfig(name="device1", url="10.0.0.1", channels=[]),
                TargetConfig(name="device2", url="10.0.0.2", channels=[]),
            ],
        )

    async def test_update_config_adds_new_targets(
        self, base_config: Config
    ) -> None:
        """Test that new targets are added during config update."""
        poller = DevicePoller(base_config)

        # Initialize states manually (simulate started state)
        for target in base_config.targets:
            poller._states[target.name] = MagicMock()
            poller._states[target.name].target = target

        # Create new config with an additional target
        new_config = Config(
            targets=[
                TargetConfig(name="device1", url="10.0.0.1", channels=[]),
                TargetConfig(name="device2", url="10.0.0.2", channels=[]),
                TargetConfig(name="device3", url="10.0.0.3", channels=[]),
            ],
        )

        await poller.update_config(new_config)

        assert "device3" in poller._states
        assert len(poller._states) == 3

    async def test_update_config_removes_old_targets(
        self, base_config: Config
    ) -> None:
        """Test that removed targets are cleaned up during config update."""
        poller = DevicePoller(base_config)

        # Initialize states manually
        for target in base_config.targets:
            poller._states[target.name] = MagicMock()
            poller._states[target.name].target = target

        # Create new config with device2 removed
        new_config = Config(
            targets=[
                TargetConfig(name="device1", url="10.0.0.1", channels=[]),
            ],
        )

        await poller.update_config(new_config)

        assert "device1" in poller._states
        assert "device2" not in poller._states
        assert len(poller._states) == 1

    async def test_update_config_updates_existing_targets(
        self, base_config: Config
    ) -> None:
        """Test that existing targets are updated with new config values."""
        poller = DevicePoller(base_config)

        # Initialize states manually
        for target in base_config.targets:
            from shelly_exporter.poller import TargetState

            poller._states[target.name] = TargetState(target=target)

        # Create new config with updated poll interval for device1
        new_config = Config(
            targets=[
                TargetConfig(
                    name="device1",
                    url="10.0.0.1",
                    poll_interval_seconds=5,
                    channels=[],
                ),
                TargetConfig(name="device2", url="10.0.0.2", channels=[]),
            ],
        )

        await poller.update_config(new_config)

        # Check that target config was updated
        assert poller._states["device1"].target.poll_interval_seconds == 5

    async def test_remove_target(self, base_config: Config) -> None:
        """Test removing a single target."""
        poller = DevicePoller(base_config)

        # Initialize states manually
        for target in base_config.targets:
            poller._states[target.name] = MagicMock()
            poller._states[target.name].target = target

        result = await poller.remove_target("device1")

        assert result is True
        assert "device1" not in poller._states
        assert "device2" in poller._states

    async def test_remove_nonexistent_target(self, base_config: Config) -> None:
        """Test removing a target that doesn't exist."""
        poller = DevicePoller(base_config)

        result = await poller.remove_target("nonexistent")

        assert result is False
