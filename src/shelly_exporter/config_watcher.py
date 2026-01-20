"""Configuration file watcher for hot-reloading config changes."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from shelly_exporter.config import Config, load_config
from shelly_exporter.metrics import (
    update_config_reload_error,
    update_config_reload_success,
)

logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """Handle file system events for config file changes."""

    def __init__(
        self,
        config_path: Path,
        callback: Callable[[], None],
        debounce_seconds: float = 1.0,
    ) -> None:
        """Initialize handler.

        Args:
            config_path: Path to the config file to watch
            callback: Function to call when config changes
            debounce_seconds: Time to wait after last change before triggering
        """
        self.config_path = config_path
        self.config_filename = config_path.name
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._pending_reload: asyncio.TimerHandle | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop for scheduling callbacks."""
        self._loop = loop

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        # Check if this is our config file
        event_path = Path(event.src_path)
        if event_path.name != self.config_filename:
            return

        logger.debug(f"Config file modified: {event.src_path}")
        self._schedule_reload()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events (config file recreated)."""
        if event.is_directory:
            return

        event_path = Path(event.src_path)
        if event_path.name != self.config_filename:
            return

        logger.debug(f"Config file created: {event.src_path}")
        self._schedule_reload()

    def _schedule_reload(self) -> None:
        """Schedule a debounced reload."""
        if self._loop is None:
            logger.warning("Event loop not set, cannot schedule reload")
            return

        # Cancel any pending reload
        if self._pending_reload is not None:
            self._pending_reload.cancel()

        # Schedule new reload after debounce period
        self._pending_reload = self._loop.call_later(
            self.debounce_seconds,
            self._trigger_reload,
        )

    def _trigger_reload(self) -> None:
        """Trigger the actual reload callback."""
        self._pending_reload = None
        logger.info("Triggering config reload after debounce")

        if self._loop is not None:
            # Schedule callback in the event loop
            self._loop.call_soon_threadsafe(self.callback)


class ConfigWatcher:
    """Service for watching and reloading configuration files."""

    def __init__(
        self,
        config_path: str | Path,
        on_reload: Callable[[Config], Any] | None = None,
        debounce_seconds: float = 1.0,
    ) -> None:
        """Initialize config watcher.

        Args:
            config_path: Path to the configuration file
            on_reload: Async callback function when config is successfully reloaded
            debounce_seconds: Time to wait after last change before reloading
        """
        self.config_path = Path(config_path)
        self.on_reload = on_reload
        self.debounce_seconds = debounce_seconds

        self._current_config: Config | None = None
        self._observer: Observer | None = None
        self._handler: ConfigFileHandler | None = None
        self._running = False
        self._reload_queue: asyncio.Queue[bool] = asyncio.Queue()

    @property
    def current_config(self) -> Config | None:
        """Return the currently loaded configuration."""
        return self._current_config

    def _on_file_changed(self) -> None:
        """Callback when file change is detected (after debounce)."""
        # Put a reload request in the queue
        try:
            self._reload_queue.put_nowait(True)
        except asyncio.QueueFull:
            logger.warning("Reload queue full, skipping reload request")

    async def _reload_config(self) -> bool:
        """Attempt to reload the configuration.

        Returns:
            True if reload was successful, False otherwise
        """
        logger.info(f"Reloading configuration from {self.config_path}")

        try:
            # Check if file exists
            if not self.config_path.exists():
                logger.warning(
                    f"Config file not found: {self.config_path}, keeping current config"
                )
                update_config_reload_error()
                return False

            # Load and validate new config
            new_config = load_config(self.config_path)

            # Store new config
            old_config = self._current_config
            self._current_config = new_config

            # Update metrics
            update_config_reload_success()

            # Notify callback
            if self.on_reload is not None:
                try:
                    result = self.on_reload(new_config)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in reload callback: {e}")
                    # Restore old config on callback error
                    self._current_config = old_config
                    update_config_reload_error()
                    return False

            # Log what changed
            self._log_config_changes(old_config, new_config)

            logger.info("Configuration reloaded successfully")
            return True

        except FileNotFoundError:
            logger.warning(
                f"Config file not found: {self.config_path}, keeping current config"
            )
            update_config_reload_error()
            return False

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            update_config_reload_error()
            return False

    def _log_config_changes(
        self, old_config: Config | None, new_config: Config
    ) -> None:
        """Log what changed between configurations."""
        if old_config is None:
            logger.info(f"Initial config loaded with {len(new_config.targets)} targets")
            return

        old_targets = {t.name for t in old_config.targets}
        new_targets = {t.name for t in new_config.targets}

        added = new_targets - old_targets
        removed = old_targets - new_targets

        if added:
            logger.info(f"Config reload: added targets: {added}")
        if removed:
            logger.info(f"Config reload: removed targets: {removed}")
        if not added and not removed:
            logger.info("Config reload: target list unchanged, settings may have updated")

    async def start(self) -> None:
        """Start watching the configuration file."""
        if self._running:
            logger.warning("Config watcher is already running")
            return

        # Load initial config
        try:
            self._current_config = load_config(self.config_path)
            logger.info(
                f"Loaded initial config with {len(self._current_config.targets)} targets"
            )
        except Exception as e:
            logger.error(f"Failed to load initial config: {e}")
            raise

        # Setup file watcher
        self._handler = ConfigFileHandler(
            self.config_path,
            self._on_file_changed,
            self.debounce_seconds,
        )
        self._handler.set_loop(asyncio.get_running_loop())

        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.config_path.parent),
            recursive=False,
        )
        self._observer.start()

        self._running = True
        logger.info(f"Started watching config file: {self.config_path}")

        # Start reload processing loop
        asyncio.create_task(self._process_reload_queue())

    async def stop(self) -> None:
        """Stop watching the configuration file."""
        self._running = False

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._handler = None
        logger.info("Stopped config file watcher")

    async def _process_reload_queue(self) -> None:
        """Process reload requests from the queue."""
        while self._running:
            try:
                # Wait for reload request with timeout
                await asyncio.wait_for(
                    self._reload_queue.get(),
                    timeout=1.0,
                )
                await self._reload_config()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing reload queue: {e}")

    async def force_reload(self) -> bool:
        """Force an immediate config reload.

        Returns:
            True if reload was successful
        """
        return await self._reload_config()
