"""HTTP server for Prometheus metrics endpoint."""

from __future__ import annotations

import logging

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)


async def metrics_handler(request: web.Request) -> web.Response:
    """Handle /metrics endpoint for Prometheus scraping."""
    metrics_output = generate_latest()
    # Extract base content type without charset (aiohttp handles charset separately)
    content_type = CONTENT_TYPE_LATEST.split(";")[0].strip()
    return web.Response(
        body=metrics_output,
        content_type=content_type,
    )


async def health_handler(request: web.Request) -> web.Response:
    """Handle /health endpoint for health checks."""
    return web.Response(text="OK")


async def root_handler(request: web.Request) -> web.Response:
    """Handle root endpoint with basic info."""
    return web.Response(
        text="Shelly Exporter\n\nEndpoints:\n  /metrics - Prometheus metrics\n  /health - Health check\n",
        content_type="text/plain",
    )


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    return app


async def run_server(host: str, port: int) -> web.AppRunner:
    """Start the HTTP server.

    Args:
        host: Host to bind to
        port: Port to listen on

    Returns:
        The AppRunner instance (for cleanup)
    """
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"HTTP server listening on http://{host}:{port}")
    return runner
