"""Main entry point for the Shelly Exporter."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from shelly_exporter import __version__
from shelly_exporter.config import load_config
from shelly_exporter.poller import DevicePoller
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

    # Start poller in background
    poller_task = asyncio.create_task(poller.start())

    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    finally:
        # Cleanup
        logger.info("Shutting down...")
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
