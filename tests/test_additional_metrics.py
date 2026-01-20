"""Tests for additional metrics parsing (system, wifi, connection, inputs)."""

from __future__ import annotations

from typing import Any

import pytest

from shelly_exporter.drivers.pro4pm_gen2 import Pro4PMGen2Driver
from shelly_exporter.drivers.base import (
    ConnectionStatus,
    InputReading,
    SystemReading,
    WifiReading,
)
from shelly_exporter.metrics import (
    shelly_cloud_connected,
    shelly_input_state,
    shelly_mqtt_connected,
    shelly_sys_cfg_rev,
    shelly_sys_fs_free,
    shelly_sys_fs_size,
    shelly_sys_ram_free,
    shelly_sys_ram_min_free,
    shelly_sys_ram_size,
    shelly_sys_restart_required,
    shelly_sys_uptime,
    shelly_wifi_connected,
    shelly_wifi_rssi,
    update_connection_metrics,
    update_input_metrics,
    update_system_metrics,
    update_wifi_metrics,
)


class TestSystemParsing:
    """Tests for system metrics parsing."""

    @pytest.fixture
    def driver(self) -> Pro4PMGen2Driver:
        """Create driver instance."""
        return Pro4PMGen2Driver()

    def test_parse_system_data(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test parsing system data from status."""
        system = driver.parse_system(pro4pm_status)

        assert system is not None
        assert system.uptime_seconds == 86400
        assert system.ram_size_bytes == 245760
        assert system.ram_free_bytes == 150000
        assert system.ram_min_free_bytes == 100000
        assert system.fs_size_bytes == 524288
        assert system.fs_free_bytes == 200000
        assert system.restart_required == 0.0  # False -> 0.0
        assert system.cfg_rev == 10

    def test_parse_system_empty(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when sys is missing."""
        system = driver.parse_system({})
        assert system is None

    def test_parse_system_restart_required_true(
        self, driver: Pro4PMGen2Driver
    ) -> None:
        """Test parsing restart_required when true."""
        status = {"sys": {"restart_required": True, "uptime": 100}}
        system = driver.parse_system(status)

        assert system is not None
        assert system.restart_required == 1.0


class TestWifiParsing:
    """Tests for WiFi metrics parsing."""

    @pytest.fixture
    def driver(self) -> Pro4PMGen2Driver:
        """Create driver instance."""
        return Pro4PMGen2Driver()

    def test_parse_wifi_data(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test parsing WiFi data from status."""
        wifi = driver.parse_wifi(pro4pm_status)

        assert wifi is not None
        assert wifi.rssi_dbm == -55
        assert wifi.connected == 1.0
        assert wifi.sta_ip == "10.0.80.20"
        assert wifi.ssid == "HomeNetwork"

    def test_parse_wifi_empty(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when wifi is missing."""
        wifi = driver.parse_wifi({})
        assert wifi is None

    def test_parse_wifi_disconnected(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when WiFi is disconnected."""
        status = {"wifi": {"status": "disconnected"}}
        wifi = driver.parse_wifi(status)

        assert wifi is not None
        assert wifi.connected == 0.0


class TestConnectionParsing:
    """Tests for connection status parsing."""

    @pytest.fixture
    def driver(self) -> Pro4PMGen2Driver:
        """Create driver instance."""
        return Pro4PMGen2Driver()

    def test_parse_connection_data(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test parsing connection status from status."""
        conn = driver.parse_connection_status(pro4pm_status)

        assert conn is not None
        assert conn.cloud_connected == 1.0
        assert conn.mqtt_connected == 1.0

    def test_parse_connection_empty(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when cloud/mqtt are missing."""
        conn = driver.parse_connection_status({})
        assert conn is None

    def test_parse_connection_mixed(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when only some connections are present."""
        status = {"cloud": {"connected": True}}
        conn = driver.parse_connection_status(status)

        assert conn is not None
        assert conn.cloud_connected == 1.0
        assert conn.mqtt_connected is None


class TestInputParsing:
    """Tests for input channel parsing."""

    @pytest.fixture
    def driver(self) -> Pro4PMGen2Driver:
        """Create driver instance."""
        return Pro4PMGen2Driver()

    def test_parse_inputs(
        self,
        driver: Pro4PMGen2Driver,
        pro4pm_status: dict[str, Any],
    ) -> None:
        """Test parsing input channels from status."""
        inputs = driver.parse_inputs(pro4pm_status)

        assert len(inputs) == 4
        assert inputs[0].input_index == 0
        assert inputs[0].state == 0.0  # False -> 0.0
        assert inputs[1].input_index == 1
        assert inputs[1].state == 1.0  # True -> 1.0
        assert inputs[2].input_index == 2
        assert inputs[2].state == 0.0
        assert inputs[3].input_index == 3
        assert inputs[3].state == 0.0

    def test_parse_inputs_empty(self, driver: Pro4PMGen2Driver) -> None:
        """Test parsing when no inputs are present."""
        inputs = driver.parse_inputs({})
        assert len(inputs) == 0

    def test_parse_inputs_sorted(self, driver: Pro4PMGen2Driver) -> None:
        """Test that inputs are sorted by index."""
        status = {
            "input:3": {"id": 3, "state": True},
            "input:1": {"id": 1, "state": False},
            "input:0": {"id": 0, "state": True},
        }
        inputs = driver.parse_inputs(status)

        assert len(inputs) == 3
        assert [i.input_index for i in inputs] == [0, 1, 3]


class TestSystemMetricsUpdate:
    """Tests for system metrics Prometheus updates."""

    def test_update_system_metrics(self) -> None:
        """Test updating system metrics."""
        system = SystemReading(
            uptime_seconds=86400,
            ram_size_bytes=245760,
            ram_free_bytes=150000,
            ram_min_free_bytes=100000,
            fs_size_bytes=524288,
            fs_free_bytes=200000,
            restart_required=0.0,
            cfg_rev=10,
        )

        update_system_metrics("test_sys", system)

        assert shelly_sys_uptime.labels(device="test_sys")._value.get() == 86400
        assert shelly_sys_ram_size.labels(device="test_sys")._value.get() == 245760
        assert shelly_sys_ram_free.labels(device="test_sys")._value.get() == 150000
        assert (
            shelly_sys_ram_min_free.labels(device="test_sys")._value.get() == 100000
        )
        assert shelly_sys_fs_size.labels(device="test_sys")._value.get() == 524288
        assert shelly_sys_fs_free.labels(device="test_sys")._value.get() == 200000
        assert (
            shelly_sys_restart_required.labels(device="test_sys")._value.get() == 0.0
        )
        assert shelly_sys_cfg_rev.labels(device="test_sys")._value.get() == 10


class TestWifiMetricsUpdate:
    """Tests for WiFi metrics Prometheus updates."""

    def test_update_wifi_metrics(self) -> None:
        """Test updating WiFi metrics."""
        wifi = WifiReading(
            rssi_dbm=-55,
            connected=1.0,
            sta_ip="10.0.0.1",
            ssid="TestNetwork",
        )

        update_wifi_metrics("test_wifi", wifi)

        assert shelly_wifi_rssi.labels(device="test_wifi")._value.get() == -55
        assert shelly_wifi_connected.labels(device="test_wifi")._value.get() == 1.0


class TestConnectionMetricsUpdate:
    """Tests for connection status metrics Prometheus updates."""

    def test_update_connection_metrics(self) -> None:
        """Test updating connection metrics."""
        conn = ConnectionStatus(
            cloud_connected=1.0,
            mqtt_connected=0.0,
        )

        update_connection_metrics("test_conn", conn)

        assert shelly_cloud_connected.labels(device="test_conn")._value.get() == 1.0
        assert shelly_mqtt_connected.labels(device="test_conn")._value.get() == 0.0


class TestInputMetricsUpdate:
    """Tests for input metrics Prometheus updates."""

    def test_update_input_metrics(self) -> None:
        """Test updating input metrics."""
        inputs = [
            InputReading(input_index=0, state=0.0),
            InputReading(input_index=1, state=1.0),
            InputReading(input_index=2, state=0.0),
        ]

        update_input_metrics("test_input", inputs)

        assert (
            shelly_input_state.labels(device="test_input", input="0")._value.get()
            == 0.0
        )
        assert (
            shelly_input_state.labels(device="test_input", input="1")._value.get()
            == 1.0
        )
        assert (
            shelly_input_state.labels(device="test_input", input="2")._value.get()
            == 0.0
        )
