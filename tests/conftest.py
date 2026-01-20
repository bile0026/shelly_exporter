"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture file."""
    path = FIXTURES_DIR / name
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def pro4pm_deviceinfo() -> dict[str, Any]:
    """Pro 4PM Gen2 device info fixture."""
    return load_fixture("pro4pm_gen2_deviceinfo.json")


@pytest.fixture
def pro4pm_status() -> dict[str, Any]:
    """Pro 4PM Gen2 status fixture."""
    return load_fixture("pro4pm_gen2_status.json")


@pytest.fixture
def s1pm_deviceinfo() -> dict[str, Any]:
    """1PM Gen4 device info fixture."""
    return load_fixture("s1pm_gen4_deviceinfo.json")


@pytest.fixture
def s1pm_status() -> dict[str, Any]:
    """1PM Gen4 status fixture."""
    return load_fixture("s1pm_gen4_status.json")


@pytest.fixture
def plugus_deviceinfo() -> dict[str, Any]:
    """Plug US Gen2 device info fixture."""
    return load_fixture("plugus_gen2_deviceinfo.json")


@pytest.fixture
def plugus_status() -> dict[str, Any]:
    """Plug US Gen2 status fixture."""
    return load_fixture("plugus_gen2_status.json")


@pytest.fixture
def dimmer_deviceinfo() -> dict[str, Any]:
    """Dimmer Gen3 device info fixture."""
    return load_fixture("dimmer_g3_deviceinfo.json")


@pytest.fixture
def dimmer_status() -> dict[str, Any]:
    """Dimmer Gen3 status fixture."""
    return load_fixture("dimmer_g3_status.json")


@pytest.fixture
def pluswalldimmer_deviceinfo() -> dict[str, Any]:
    """Plus Wall Dimmer Gen2 device info fixture."""
    return load_fixture("pluswalldimmer_gen2_deviceinfo.json")


@pytest.fixture
def pluswalldimmer_status() -> dict[str, Any]:
    """Plus Wall Dimmer Gen2 status fixture."""
    return load_fixture("pluswalldimmer_gen2_status.json")


@pytest.fixture
def blugw_gen2_deviceinfo() -> dict[str, Any]:
    """BLU Gateway Gen2 device info fixture."""
    return load_fixture("blugw_gen2_deviceinfo.json")


@pytest.fixture
def blugw_gen2_status() -> dict[str, Any]:
    """BLU Gateway Gen2 status fixture."""
    return load_fixture("blugw_gen2_status.json")


@pytest.fixture
def blugw_gen3_deviceinfo() -> dict[str, Any]:
    """BLU Gateway Gen3 device info fixture."""
    return load_fixture("blugw_gen3_deviceinfo.json")


@pytest.fixture
def blugw_gen3_status() -> dict[str, Any]:
    """BLU Gateway Gen3 status fixture."""
    return load_fixture("blugw_gen3_status.json")
