"""Main entry point for the Shelly Exporter."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from shelly_exporter import __version__
from shelly_exporter.config import Config, TargetConfig, load_config
from shelly_exporter.config_watcher import ConfigWatcher
from shelly_exporter.drivers.registry import get_registry
from shelly_exporter.poller import DevicePoller
from shelly_exporter.scanner import NetworkScanner
from shelly_exporter.web import run_server


def setup_logging(level: str) -> None:
    """Configure logging with timestamps."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Prometheus exporter for Shelly devices",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to configuration file (default: CONFIG_PATH env var or /config/config.yml)",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"shelly-exporter {__version__}",
    )
    return parser.parse_args()


async def async_main(config_path: Path | None) -> None:
    """Async main function."""
    # Resolve config path
    if config_path is None:
        import os

        config_path = Path(os.environ.get("CONFIG_PATH", "/config/config.yml"))

    # Load configuration
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Setup logging based on config
    setup_logging(config.log_level.value)
    logger = logging.getLogger(__name__)

    logger.info(f"Starting Shelly Exporter v{__version__}")
    logger.info(f"Loaded configuration with {len(config.targets)} targets")

    # Create poller
    poller = DevicePoller(config)

    # Create config reload callback
    async def on_config_reload(new_config: Config) -> None:
        logger.info("Applying new configuration...")
        await poller.update_config(new_config)

        # Update scanner config if discovery is enabled
        if scanner is not None:
            scanner.config = new_config
            scanner._configured_urls = scanner._get_configured_urls()
            logger.info("Updated scanner with new configuration")

    # Create config watcher for hot-reload
    config_watcher = ConfigWatcher(
        config_path=config_path,
        on_reload=on_config_reload,
        debounce_seconds=1.0,
    )

    # Create discovery callback that adds targets to poller
    async def on_device_discovered(target: TargetConfig) -> None:
        if not poller.has_target_url(target.url):
            await poller.add_target(target)

    # Create network scanner (if discovery enabled)
    scanner: NetworkScanner | None = None
    if config.discovery.enabled:
        driver_registry = get_registry()
        scanner = NetworkScanner(
            config=config,
            driver_registry=driver_registry,
            on_device_discovered=on_device_discovered,
        )
        logger.info("Network discovery is enabled")

    # Create shutdown event
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        shutdown_event.set()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start HTTP server
    runner = await run_server(config.listen_host, config.listen_port)

    # Start config watcher
    await config_watcher.start()
    logger.info(f"Watching config file for changes: {config_path}")

    # Start poller in background
    poller_task = asyncio.create_task(poller.start())

    # Start scanner in background (if enabled)
    scanner_task: asyncio.Task[None] | None = None
    if scanner:
        await scanner.start()
        # Scanner runs its own background task, but we need to track it for cleanup

    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    finally:
        # Cleanup
        logger.info("Shutting down...")

        # Stop config watcher
        await config_watcher.stop()

        # Stop scanner first
        if scanner:
            await scanner.stop()

        await poller.stop()
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()
        logger.info("Shutdown complete")


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Basic logging for startup (will be reconfigured after loading config)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        asyncio.run(async_main(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
