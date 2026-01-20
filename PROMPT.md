You are a senior Python engineer. Build a complete, production-ready Python 3.12 project (uv-managed) that polls Shelly devices asynchronously and exposes Prometheus metrics at /metrics. This should be a modular exporter framework capable of supporting multiple Shelly models with a plugin/driver architecture.

High-level goals:
- Async, concurrent polling of many devices with configurable max concurrency.
- Configurable polling intervals (global default + per-target override).
- Default credentials at the top-level (applies to all targets unless overridden per target).
- Docker support: run as a container and expose /metrics.
- Robust parsing: never crash on missing/extra fields; log and continue.
- Optional network scanning service to auto-discover Shelly devices on specified network ranges (CIDR or IP ranges).

Dependency management:
- Use uv (pyproject.toml + uv.lock). Provide commands to create venv, sync deps, run, and run tests.
- Use Python 3.12.

Device API requirements:
- Use Shelly RPC API via HTTP JSON-RPC POST (preferred for consistency):
  POST http://{url}/rpc
  {"id":1,"method":"Shelly.GetStatus"}
  Response:
  {"id":1,"src":"...","result":{...}}
- Also call Shelly.GetDeviceInfo to auto-detect model/gen/app:
  POST /rpc {"id":1,"method":"Shelly.GetDeviceInfo"}
- Devices can be Gen2, Gen3, Gen4 (and potentially more later).

Real model examples you MUST handle (payload shapes differ):
1) Shelly Pro 4PM Gen2
DeviceInfo result contains: {"model":"SPSW-104PE16EU","gen":2,"app":"Pro4PM", ...}
Status result includes keys: "switch:0","switch:1","switch:2","switch:3","sys",...
Each switch includes: output, apower, voltage, freq, current, pf, temperature{tC,tF}, aenergy{total,...}, ret_aenergy{total,...}

2) Shelly 1PM Gen4
DeviceInfo result contains: {"model":"S4SW-001P16EU","gen":4,"app":"S1PMG4", ...,"matter": true}
Status result includes keys: "switch:0","sys","matter",...
switch:0 may NOT include pf; temperature.tC/tF may be null.
sys may include extra keys like "alt".

3) Shelly Plug US Gen2 (app "PlugUS")
DeviceInfo result contains: {"model":"SNPL-00116US","gen":2,"app":"PlugUS", ...}
Status result includes: "switch:0","sys",...
switch:0 includes: output, apower, voltage, current, aenergy{total,...}, temperature{tC,tF}
Notably may NOT include: freq, pf, ret_aenergy, etc. Your code must handle missing fields gracefully.

4) Shelly Dimmer 0/1-10V PM Gen3 (app "Dimmer0110VPMG3")
DeviceInfo result contains: {"model":"S3DM-0010WW","gen":3,"app":"Dimmer0110VPMG3", ...}
Status result includes keys: "light:0", "sys", "input:0", "input:1", ...
There is NO "switch:0" key; instead the controllable channel is "light:0".
Your code must support non-switch channel types (e.g., light channels).

Dimmer status parsing requirements:
- Parse data from result["light:0"] (not switch).
- Expect that light channels may have different fields than switch channels.
- Implement a generic “channel” abstraction:
  - ChannelReading(channel_type, channel_index, output/on, brightness if present, apower/energy/voltage/current/temp if present)
- Expose metrics so dimmers still fit into a consistent naming scheme.
  Preferred approach:
  - Keep existing switch metrics for switch-like devices
  - Add parallel light metrics:
    shelly_light_output{device,channel}
    shelly_light_brightness_percent{device,channel} (0-100) if available
    shelly_light_apower_watts{device,channel} if available
    shelly_light_aenergy_wh_total{device,channel} if available
  - Also expose common per-device metrics (up, last_poll, duration, errors).
- If "light:0" lacks certain power fields, handle gracefully (NaN/skip).

Modular driver/plugin architecture (must implement):
- Base interface/class DeviceDriver:
  - score(device_info: dict) -> int (higher is better; 0 means not supported)
  - supported_channels(device_info)->dict[str,set[int]] (e.g., {"switch":{0,1,2,3}} or {"light":{0}})
  - parse_status(status_result: dict, target_config)->list[ChannelReading]
  - driver_id/name string for logging
- Runtime selection:
  - For each target, call Shelly.GetDeviceInfo once at startup to select the best driver.
  - Cache driver selection; periodically refresh device info (e.g., every 6 hours) or on repeated failures.
- Drivers to implement now:
  - Pro4PMGen2Driver (gen==2, app=="Pro4PM") → channels: switch 0..3
  - Shelly1PMGen4Driver (gen==4, app=="S1PMG4") → channels: switch 0
  - PlugUSGen2Driver (gen==2, app=="PlugUS") → channels: switch 0
  - Dimmer0110VPMG3Driver (gen==3, app=="Dimmer0110VPMG3") → channels: light 0
- Make it easy to add more drivers later without modifying polling core (registry/discovery pattern).

Normalization + robustness:
- Normalize meter/channel indices:
  - If config uses 1..4, normalize to 0..3 with a warning.
  - Skip out-of-range channels for the chosen driver/model with a warning.
- Handle missing fields:
  - Never crash. If a field is absent, either emit NaN or skip metric update (choose one and document; preferred: set NaN when possible).
  - Handle null temperature values (tC/tF null) without exceptions.
- Auth:
  - Resolve credentials as: target.credentials > default_credentials > none
  - Use HTTP Basic Auth when either username or password is non-empty.
  - On 401/403, set shelly_up=0, increment errors counter, log warning.

Configuration (YAML):
- Must support:
log_level: INFO|DEBUG|WARNING|ERROR
listen_host: 0.0.0.0
listen_port: 10037
poll_interval_seconds: 10              # global default polling interval
request_timeout_seconds: 3
max_concurrency: 50
default_credentials:
  username: ""
  password: ""
# Optional network scanning/discovery:
discovery:
  enabled: false                       # set to true to enable auto-discovery
  scan_interval_seconds: 3600          # how often to scan for new devices (default: 1 hour)
  network_ranges:                      # list of CIDR blocks or IP ranges to scan
    - "10.0.80.0/24"                   # CIDR notation
    - "192.168.1.100-192.168.1.200"   # IP range notation
  scan_timeout_seconds: 2              # timeout per IP address during scan
  scan_concurrency: 20                 # max concurrent scan requests
  auto_add_discovered: true            # automatically add discovered devices to targets
  auto_add_credentials:                # credentials to use for discovered devices (if auto_add_discovered=true)
    username: ""                       # defaults to default_credentials if not specified
    password: ""
  exclude_ips:                         # IPs to exclude from scanning (optional)
    - "10.0.80.1"                      # gateway/router
    - "10.0.80.100"                    # other non-Shelly devices
  name_template: "shelly_{ip}_{model}" # template for auto-generated device names
                                        # Available variables: {ip}, {model}, {gen}, {app}, {mac}
targets:
  - name: parking_lot_light_power
    url: 10.0.80.22
    poll_interval_seconds: 5           # optional per-target override
    credentials:
      username: ""
      password: ""
    channels:                          # supports multiple channel types
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
  - name: dimmer_hallway
    url: 10.0.80.35
    channels:
      - type: light
        index: 0
        ignore_output: false
        ignore_brightness: false
        ignore_active_power: false
        ignore_total_active_energy: false
        ignore_temperature: true        # if not available
# Backward compatibility:
- Also accept old key "target_meters" meaning type "switch" channels, for users migrating.

Polling / scheduling:
- Implement an async scheduler:
  - Each target has its own next_run time based on per-target poll_interval_seconds or global.
  - Use a single loop that enqueues due targets.
  - Use asyncio.Semaphore(max_concurrency) to limit in-flight polls.
- Keep metrics updates separate from HTTP serving.
- Add exponential backoff on repeated failures per target (with sane defaults; configurable if you add config keys—document defaults clearly).

Network scanning / auto-discovery:
- Implement a NetworkScanner service (scanner.py):
  - Parse CIDR notation (e.g., "10.0.80.0/24") and IP ranges (e.g., "192.168.1.100-192.168.1.200").
  - Generate list of IP addresses to scan from configured ranges.
  - Exclude IPs listed in exclude_ips configuration.
  - Concurrently probe each IP address:
    - Attempt HTTP connection to http://{ip}/rpc
    - Call Shelly.GetDeviceInfo to identify if device is a Shelly
    - Use scan_timeout_seconds for each probe
    - Respect scan_concurrency limit (use asyncio.Semaphore)
  - For discovered Shelly devices:
    - Extract device info (model, gen, app, MAC address)
    - Generate device name using name_template
    - If auto_add_discovered=true:
      - Create target configuration automatically
      - Use auto_add_credentials (or default_credentials if not specified)
      - Auto-detect supported channels using driver.supported_channels()
      - Add all supported channels to the target config
      - Log discovery event
    - Update discovery metrics
  - Run scans periodically based on scan_interval_seconds (only if discovery.enabled=true)
  - Integrate with poller: discovered devices should be added to the polling queue
  - Handle errors gracefully: network timeouts, non-Shelly devices, auth failures
  - Log discovery activity at INFO level (device found) and DEBUG level (scan progress)
- Discovery should run in parallel with polling (separate async task)
- When a device is discovered and auto-added:
  - It should immediately start being polled (no restart required)
  - Use in-memory target registry that can be updated dynamically
  - Optionally persist discovered devices to a file for persistence across restarts (optional feature)

Prometheus metrics:
- Use prometheus_client.
- Common per-device metrics:
  shelly_up{device}
  shelly_last_poll_timestamp_seconds{device}
  shelly_poll_duration_seconds{device}
  shelly_poll_errors_total{device} (counter)
- Discovery/scanning metrics:
  shelly_discovery_scans_total (counter) - total number of network scans performed
  shelly_discovery_devices_found_total (counter) - total devices discovered across all scans
  shelly_discovery_scan_duration_seconds (gauge) - duration of last scan in seconds
  shelly_discovery_last_scan_timestamp_seconds (gauge) - timestamp of last scan
  shelly_discovery_scan_errors_total (counter) - total scan errors
  shelly_discovered_device_info{ip,model,gen,app,mac,discovered_at} (gauge, value=1) - info about discovered devices
- Switch channel metrics (device,meter):
  shelly_switch_output{device,meter}
  shelly_switch_apower_watts{device,meter}
  shelly_switch_voltage_volts{device,meter}
  shelly_switch_frequency_hz{device,meter}
  shelly_switch_current_amps{device,meter}
  shelly_switch_power_factor{device,meter}
  shelly_switch_temperature_c{device,meter}
  shelly_switch_aenergy_wh_total{device,meter}
  shelly_switch_ret_aenergy_wh_total{device,meter}
- Light channel metrics (device,channel):
  shelly_light_output{device,channel}
  shelly_light_brightness_percent{device,channel}       # if available
  shelly_light_apower_watts{device,channel}             # if available
  shelly_light_aenergy_wh_total{device,channel}         # if available

Implementation details:
- Use httpx.AsyncClient with keepalive pooling.
- Use pydantic v2 for config models and validation.
- Use PyYAML (or ruamel.yaml) for YAML parsing.
- Use standard logging with timestamps.
- Use ipaddress module for CIDR parsing and IP range generation.
- Provide normalized data models:
  - DeviceReading for per-device fields (up, duration, etc.)
  - ChannelReading(channel_type, channel_index, output, brightness, apower_w, voltage_v, freq_hz, current_a, pf, temp_c, aenergy_wh, ret_aenergy_wh)
  - Drivers convert raw Shelly JSON into ChannelReading objects.
  - DiscoveredDevice(ip, device_info, discovered_at) for tracking discovered devices.

Project structure (must create all files):
- pyproject.toml (uv-compatible)
- uv.lock (assume generated; include command to generate)
- src/shelly_exporter/
  - __init__.py
  - config.py
  - drivers/
    - __init__.py
    - base.py                 # DeviceDriver base class + ChannelReading dataclass
    - pro4pm_gen2.py
    - s1pm_gen4.py
    - plugus_gen2.py
    - dimmer_0110vpm_g3.py
    - registry.py             # driver registry/discovery
  - shelly_client.py          # RPC client + device info/status methods
  - scanner.py                # network scanning service for auto-discovery
  - metrics.py
  - poller.py
  - web.py
  - main.py
- config/example.yml demonstrating:
  - default_credentials
  - one Pro4PM target with 4 switch channels
  - one 1PM Gen4 target with 1 switch channel
  - one PlugUS target with 1 switch channel
  - one Dimmer0110VPMG3 target with 1 light channel
  - per-target poll interval override and per-target credential override example
  - discovery configuration example (commented out, showing how to enable auto-discovery)
- tests/:
  - test_config_load.py
  - test_driver_selection.py
  - test_pro4pm_parsing.py
  - test_s1pm_parsing.py
  - test_plugus_parsing.py
  - test_dimmer_parsing.py
  - test_metrics_update.py
  - test_scanner.py                 # tests for network scanning functionality
  Include JSON fixtures in tests/fixtures/ for deviceinfo + status for each model, including a dimmer status fixture showing light:0.

Docker:
- Provide Dockerfile using uv:
  - install uv in image (or use official uv base)
  - uv sync --frozen (or documented approach)
  - run app with the venv created by uv (or uv run)
- Provide docker-compose.yml:
  - mount ./config:/config
  - env CONFIG_PATH=/config/config.yml
  - expose 10037
- App defaults to CONFIG_PATH=/config/config.yml if env not set.

CLI:
- python -m shelly_exporter --config /path/to/config.yml
- CONFIG_PATH env var override.

Deliverables:
- Output the full repository file tree.
- Then output the complete contents of each file.
- Keep code copy/paste runnable.
- Do not omit any files. Include instructions to run locally, run tests, and run in Docker.

Before coding:
- Briefly explain assumptions (max 5 bullets), then generate the project.
