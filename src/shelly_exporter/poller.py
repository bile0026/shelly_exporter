"""Async poller for Shelly devices with scheduling and backoff."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from shelly_exporter.config import Config, TargetConfig
from shelly_exporter.drivers.base import DeviceDriver, DeviceReading
from shelly_exporter.drivers.registry import get_registry
from shelly_exporter.metrics import update_metrics_from_reading
from shelly_exporter.shelly_client import (
    ShellyAuthError,
    ShellyClient,
    ShellyClientError,
    ShellyClientPool,
)

logger = logging.getLogger(__name__)


@dataclass
class TargetState:
    """Runtime state for a polling target."""

    target: TargetConfig
    driver: DeviceDriver | None = None
    device_info: dict[str, Any] = field(default_factory=dict)
    device_info_fetched_at: float = 0.0
    next_poll_time: float = 0.0
    consecutive_failures: int = 0
    backoff_until: float = 0.0


class DevicePoller:
    """Async poller that polls multiple Shelly devices concurrently."""

    def __init__(self, config: Config) -> None:
        """Initialize poller.

        Args:
            config: Application configuration
        """
        self.config = config
        self._states: dict[str, TargetState] = {}
        self._client_pool: ShellyClientPool | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._running = False
        self._registry = get_registry()

    async def start(self) -> None:
        """Start the poller."""
        logger.info(f"Starting poller with {len(self.config.targets)} targets")

        # Initialize states for all targets
        for target in self.config.targets:
            self._states[target.name] = TargetState(target=target)

        # Create semaphore for concurrency limiting
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)

        # Create client pool
        self._client_pool = ShellyClientPool(
            timeout=self.config.request_timeout_seconds,
            max_connections=self.config.max_concurrency * 2,
        )

        self._running = True
        await self._client_pool.__aenter__()

        # Start polling loop
        await self._polling_loop()

    async def stop(self) -> None:
        """Stop the poller."""
        logger.info("Stopping poller")
        self._running = False
        if self._client_pool:
            await self._client_pool.__aexit__(None, None, None)
            self._client_pool = None

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            now = time.time()
            tasks: list[asyncio.Task[None]] = []

            # Find targets due for polling
            for state in self._states.values():
                if now >= state.next_poll_time and now >= state.backoff_until:
                    task = asyncio.create_task(self._poll_target(state))
                    tasks.append(task)

            # Wait for batch to complete (if any)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Sleep briefly before next check
            await asyncio.sleep(0.1)

    async def _poll_target(self, state: TargetState) -> None:
        """Poll a single target.

        Args:
            state: Target state to poll
        """
        if not self._semaphore or not self._client_pool:
            return

        async with self._semaphore:
            target = state.target
            start_time = time.time()

            try:
                # Get credentials
                credentials = self.config.get_target_credentials(target)

                # Create client for this target
                client = self._client_pool.get_client(target.url, credentials)

                # Fetch device info if needed (first time or refresh interval)
                if await self._should_refresh_device_info(state):
                    await self._fetch_device_info(client, state)

                # Skip if no driver available
                if not state.driver:
                    logger.warning(f"No driver for target '{target.name}', skipping poll")
                    self._schedule_next_poll(state)
                    return

                # Fetch status
                status = await client.get_status()
                duration = time.time() - start_time

                # Parse status into readings
                channel_readings = state.driver.parse_status(status, target)

                # Parse additional data (system, wifi, connection, inputs)
                system_reading = state.driver.parse_system(status)
                wifi_reading = state.driver.parse_wifi(status)
                connection_reading = state.driver.parse_connection_status(status)
                input_readings = state.driver.parse_inputs(status)

                # Create device reading
                reading = DeviceReading(
                    device_name=target.name,
                    up=True,
                    poll_duration_seconds=duration,
                    channels=channel_readings,
                    inputs=input_readings,
                    system=system_reading,
                    wifi=wifi_reading,
                    connection=connection_reading,
                )

                # Update metrics
                update_metrics_from_reading(reading, target)

                # Reset failure count on success
                state.consecutive_failures = 0
                state.backoff_until = 0.0

                logger.debug(
                    f"Polled '{target.name}' successfully in {duration:.3f}s, "
                    f"{len(channel_readings)} channels"
                )

            except ShellyAuthError as e:
                duration = time.time() - start_time
                self._handle_poll_error(state, str(e), duration)
                logger.warning(f"Auth error for '{target.name}': {e}")

            except ShellyClientError as e:
                duration = time.time() - start_time
                self._handle_poll_error(state, str(e), duration)
                logger.warning(f"Client error for '{target.name}': {e}")

            except Exception as e:
                duration = time.time() - start_time
                self._handle_poll_error(state, str(e), duration)
                logger.exception(f"Unexpected error polling '{target.name}'")

            finally:
                self._schedule_next_poll(state)

    async def _should_refresh_device_info(self, state: TargetState) -> bool:
        """Check if device info should be refreshed."""
        now = time.time()

        # First fetch
        if state.device_info_fetched_at == 0:
            return True

        # Refresh interval elapsed
        if now - state.device_info_fetched_at >= self.config.device_info_refresh_seconds:
            return True

        # Repeated failures may indicate device change
        if state.consecutive_failures >= 5 and state.driver is None:
            return True

        return False

    async def _fetch_device_info(
        self,
        client: ShellyClient,
        state: TargetState,
    ) -> None:
        """Fetch and cache device info, select driver.

        Args:
            client: Shelly client
            state: Target state to update
        """
        try:
            device_info = await client.get_device_info()
            state.device_info = device_info
            state.device_info_fetched_at = time.time()

            # Select best driver
            driver = self._registry.get_best_driver(device_info)
            if driver:
                state.driver = driver
                logger.info(
                    f"Target '{state.target.name}': selected driver "
                    f"'{driver.driver_name}' for gen={device_info.get('gen')}, "
                    f"app={device_info.get('app')}"
                )
            else:
                state.driver = None
                logger.warning(
                    f"Target '{state.target.name}': no driver for "
                    f"gen={device_info.get('gen')}, app={device_info.get('app')}"
                )

        except ShellyClientError as e:
            logger.error(f"Failed to fetch device info for '{state.target.name}': {e}")
            # Keep existing driver if any
            state.device_info_fetched_at = time.time()  # Prevent immediate retry

    def _handle_poll_error(
        self,
        state: TargetState,
        error_message: str,
        duration: float,
    ) -> None:
        """Handle a poll error with backoff.

        Args:
            state: Target state
            error_message: Error description
            duration: Poll duration in seconds
        """
        state.consecutive_failures += 1

        # Calculate backoff
        backoff = min(
            self.config.backoff_base_seconds
            * (self.config.backoff_multiplier ** (state.consecutive_failures - 1)),
            self.config.backoff_max_seconds,
        )
        state.backoff_until = time.time() + backoff

        # Create error reading for metrics
        reading = DeviceReading(
            device_name=state.target.name,
            up=False,
            poll_duration_seconds=duration,
            error_message=error_message,
        )
        update_metrics_from_reading(reading, state.target)

        logger.debug(
            f"Target '{state.target.name}' failed ({state.consecutive_failures} consecutive), "
            f"backing off for {backoff:.1f}s"
        )

    def _schedule_next_poll(self, state: TargetState) -> None:
        """Schedule next poll time for target.

        Args:
            state: Target state to update
        """
        interval = self.config.get_target_poll_interval(state.target)
        state.next_poll_time = time.time() + interval

    async def add_target(self, target: TargetConfig) -> None:
        """Add a new target to the poller dynamically.

        Args:
            target: Target configuration to add
        """
        if target.name in self._states:
            logger.warning(f"Target '{target.name}' already exists, skipping")
            return

        self._states[target.name] = TargetState(target=target)
        self.config.targets.append(target)
        logger.info(f"Added new target '{target.name}' to poller")

    def has_target(self, name: str) -> bool:
        """Check if a target exists by name.

        Args:
            name: Target name to check

        Returns:
            True if target exists
        """
        return name in self._states

    def has_target_url(self, url: str) -> bool:
        """Check if a target exists by URL.

        Args:
            url: Target URL to check

        Returns:
            True if target with URL exists
        """
        for state in self._states.values():
            if state.target.url == url:
                return True
        return False

    async def remove_target(self, name: str) -> bool:
        """Remove a target from the poller.

        Args:
            name: Target name to remove

        Returns:
            True if target was removed, False if not found
        """
        if name not in self._states:
            return False

        del self._states[name]
        # Also remove from config.targets list
        self.config.targets = [t for t in self.config.targets if t.name != name]
        logger.info(f"Removed target '{name}' from poller")
        return True

    async def update_config(self, new_config: Config) -> None:
        """Update poller with new configuration.

        Handles adding new targets, removing old targets, and updating settings.

        Args:
            new_config: New configuration to apply
        """
        old_target_names = set(self._states.keys())
        new_target_names = {t.name for t in new_config.targets}

        # Find targets to add and remove
        to_add = new_target_names - old_target_names
        to_remove = old_target_names - new_target_names

        # Remove old targets
        for name in to_remove:
            await self.remove_target(name)

        # Update the config reference
        self.config = new_config

        # Add new targets
        for target in new_config.targets:
            if target.name in to_add:
                self._states[target.name] = TargetState(target=target)
                logger.info(f"Added new target '{target.name}' from config reload")

        # Update existing targets with new config values
        for name in old_target_names & new_target_names:
            # Find the updated target config
            for target in new_config.targets:
                if target.name == name:
                    self._states[name].target = target
                    break

        logger.info(
            f"Config update complete: added {len(to_add)}, removed {len(to_remove)}, "
            f"total targets: {len(self._states)}"
        )
