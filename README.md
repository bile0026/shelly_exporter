# Shelly Exporter

A production-ready Prometheus exporter for Shelly devices with a modular plugin/driver architecture.

## Features

- Async, concurrent polling of multiple Shelly devices
- Configurable polling intervals (global and per-target)
- Modular driver architecture for easy device support extension
- Support for Gen2, Gen3, and Gen4 Shelly devices
- Switch and light channel support
- Automatic driver selection based on device info
- Network auto-discovery of Shelly devices (CIDR/IP ranges)
- Automatic configuration reload (hot reload without restart)
- Exponential backoff on failures
- Docker support

## Supported Devices

| Device | Gen | App | Driver |
|--------|-----|-----|--------|
| Shelly Pro 4PM | 2 | Pro4PM | `pro4pm_gen2` |
| Shelly 1PM | 4 | S1PMG4 | `s1pm_gen4` |
| Shelly Plug US | 2 | PlugUS | `plugus_gen2` |
| Shelly Dimmer 0/1-10V PM | 3 | Dimmer0110VPMG3 | `dimmer_0110vpm_g3` |

## Quick Start

### Local Development

```bash
# Create virtual environment and install dependencies
uv venv
uv sync

# Run with config file
uv run python -m shelly_exporter --config config/example.yml

# Or using environment variable
CONFIG_PATH=config/example.yml uv run python -m shelly_exporter
```

### Docker

```bash
# Build and run with docker-compose
docker-compose up -d

# Or build manually
docker build -t shelly-exporter .
docker run -p 10037:10037 -v ./config:/config:ro shelly-exporter
```

### Access Metrics

```bash
curl http://localhost:10037/metrics
```

## Configuration

Create a `config.yml` file (see `config/example.yml` for a complete example):

```yaml
log_level: INFO
listen_host: 0.0.0.0
listen_port: 10037
poll_interval_seconds: 10
request_timeout_seconds: 3
max_concurrency: 50

default_credentials:
  username: ""
  password: ""

targets:
  - name: workshop_power
    url: 10.0.80.20
    poll_interval_seconds: 5  # Override global interval
    channels:
      - type: switch
        index: 0
      - type: switch
        index: 1
      - type: switch
        index: 2
      - type: switch
        index: 3

  - name: hallway_dimmer
    url: 10.0.80.35
    channels:
      - type: light
        index: 0
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `log_level` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `listen_host` | 0.0.0.0 | HTTP server bind address |
| `listen_port` | 10037 | HTTP server port |
| `poll_interval_seconds` | 10 | Global polling interval |
| `request_timeout_seconds` | 3 | HTTP request timeout |
| `max_concurrency` | 50 | Maximum concurrent polls |
| `device_info_refresh_seconds` | 21600 | Device info refresh interval (6 hours) |
| `backoff_base_seconds` | 30 | Base backoff time for failures |
| `backoff_max_seconds` | 300 | Maximum backoff time (5 minutes) |

### Channel Options

Each channel can have ignore flags to skip specific metrics:

```yaml
channels:
  - type: switch
    index: 0
    ignore_voltage: false
    ignore_current: false
    ignore_active_power: false
    ignore_power_factor: false
    ignore_frequency: false
    ignore_total_active_energy: false
    ignore_total_returned_active_energy: false
    ignore_temperature: false
    ignore_output: false
```

For light channels:
```yaml
channels:
  - type: light
    index: 0
    ignore_output: false
    ignore_brightness: false
    ignore_active_power: false
    ignore_total_active_energy: false
```

### Network Auto-Discovery

The exporter can automatically discover Shelly devices on your network. When enabled, it periodically scans specified network ranges and adds discovered devices to the polling list.

```yaml
discovery:
  enabled: true
  scan_interval_seconds: 3600          # Scan every hour
  network_ranges:
    - "10.0.80.0/24"                   # CIDR notation
    - "192.168.1.100-192.168.1.200"   # IP range notation
  scan_timeout_seconds: 2.0
  scan_concurrency: 20
  auto_add_discovered: true
  auto_add_credentials:
    username: ""
    password: ""
  exclude_ips:
    - "10.0.80.1"                      # Gateway
  name_template: "shelly_{ip}_{model}"
  persist_path: /app/data/discovered.yml # Persist across restarts
  # Note: Use /app/data/discovered.yml for writable location (recommended)
  # Or use /config/discovered.yml if host directory has write permissions for container user
```

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | false | Enable/disable network discovery |
| `scan_interval_seconds` | 3600 | How often to scan for new devices |
| `network_ranges` | [] | CIDR blocks or IP ranges to scan |
| `scan_timeout_seconds` | 2.0 | Timeout per IP during scan |
| `scan_concurrency` | 20 | Max concurrent scan requests |
| `auto_add_discovered` | true | Automatically add found devices |
| `auto_add_credentials` | null | Credentials for discovered devices |
| `exclude_ips` | [] | IPs to exclude from scanning |
| `name_template` | "shelly_{ip}_{model}" | Template for device names |
| `persist_path` | null | Path to save discovered devices (survives restarts). Use `/app/data/discovered.yml` for writable location (recommended) or ensure `/config` has write permissions for container user |

Name template variables: `{ip}`, `{model}`, `{gen}`, `{app}`, `{mac}`, `{id}`

### Configuration Reloading

The exporter automatically watches the configuration file for changes and reloads it without requiring a restart. Changes are detected within seconds and applied immediately.

**What gets reloaded:**
- Global settings (log_level, poll_interval_seconds, etc.)
- New targets are added automatically
- Removed targets stop being polled
- Updated target settings (poll intervals, credentials, channels) are applied
- Invalid configurations are rejected (old config continues to be used)

**Behavior:**
- Config file changes are debounced (waits ~1 second after last change)
- Invalid YAML or validation errors are logged, old config is retained
- Metrics continue without interruption during reload
- Reload events are logged at INFO level

## Prometheus Metrics

### Per-Device Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_up` | device | Device availability (1=up, 0=down) |
| `shelly_last_poll_timestamp_seconds` | device | Last successful poll timestamp |
| `shelly_poll_duration_seconds` | device | Duration of last poll |
| `shelly_poll_errors_total` | device | Total poll errors (counter) |

### System Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_sys_uptime_seconds` | device | Device uptime in seconds |
| `shelly_sys_ram_size_bytes` | device | Total RAM size |
| `shelly_sys_ram_free_bytes` | device | Free RAM |
| `shelly_sys_ram_min_free_bytes` | device | Minimum free RAM since boot |
| `shelly_sys_fs_size_bytes` | device | Total filesystem size |
| `shelly_sys_fs_free_bytes` | device | Free filesystem space |
| `shelly_sys_restart_required` | device | Restart required (1=yes, 0=no) |
| `shelly_sys_cfg_rev` | device | Configuration revision |

### WiFi Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_wifi_rssi_dbm` | device | WiFi signal strength (dBm) |
| `shelly_wifi_connected` | device | WiFi connected (1=yes, 0=no) |

### Connection Status Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_cloud_connected` | device | Cloud connected (1=yes, 0=no) |
| `shelly_mqtt_connected` | device | MQTT connected (1=yes, 0=no) |

### Input Channel Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_input_state` | device, input | Input state (1=on, 0=off) |

### Switch Channel Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_switch_output` | device, meter | Switch state (1=on, 0=off) |
| `shelly_switch_apower_watts` | device, meter | Active power (W) |
| `shelly_switch_voltage_volts` | device, meter | Voltage (V) |
| `shelly_switch_frequency_hz` | device, meter | Frequency (Hz) |
| `shelly_switch_current_amps` | device, meter | Current (A) |
| `shelly_switch_power_factor` | device, meter | Power factor |
| `shelly_switch_temperature_c` | device, meter | Temperature (C) |
| `shelly_switch_aenergy_wh_total` | device, meter | Total active energy (Wh) |
| `shelly_switch_ret_aenergy_wh_total` | device, meter | Total returned energy (Wh) |

### Light Channel Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_light_output` | device, channel | Light state (1=on, 0=off) |
| `shelly_light_brightness_percent` | device, channel | Brightness (0-100%) |
| `shelly_light_apower_watts` | device, channel | Active power (W) |
| `shelly_light_aenergy_wh_total` | device, channel | Total active energy (Wh) |
| `shelly_light_voltage_volts` | device, channel | Voltage (V) |
| `shelly_light_current_amps` | device, channel | Current (A) |
| `shelly_light_temperature_c` | device, channel | Temperature (C) |

### Discovery Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_discovery_scans_total` | - | Total network scans performed (counter) |
| `shelly_discovery_devices_found_total` | - | Total devices discovered (counter) |
| `shelly_discovery_scan_duration_seconds` | - | Duration of last scan |
| `shelly_discovery_last_scan_timestamp_seconds` | - | Timestamp of last scan |
| `shelly_discovery_scan_errors_total` | - | Total scan errors (counter) |
| `shelly_discovered_device_info` | ip, model, gen, app, mac, discovered_at | Info about discovered devices (value=1) |

### Configuration Metrics

| Metric | Labels | Description |
|--------|--------|-------------|
| `shelly_config_reloads_total` | - | Total successful config reloads (counter) |
| `shelly_config_reload_errors_total` | - | Total failed config reload attempts (counter) |
| `shelly_config_last_reload_timestamp_seconds` | - | Timestamp of last successful config reload |
| `shelly_config_last_reload_status` | - | Status of last reload attempt (1=success, 0=failure) |

## Running Tests

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=shelly_exporter --cov-report=html
```

## Adding New Device Drivers

1. Create a new driver file in `src/shelly_exporter/drivers/`
2. Implement the `DeviceDriver` interface:
   - `driver_id`: Unique identifier
   - `driver_name`: Human-readable name
   - `score(device_info)`: Return match score (>0 if supported)
   - `supported_channels(device_info)`: Return supported channel types/indices
   - `parse_status(status_result, target_config)`: Parse status into readings
3. Register the driver in `src/shelly_exporter/drivers/registry.py`

## License

MIT
