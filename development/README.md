# Development Environment

This directory contains a complete development/testing setup with Prometheus and Grafana for monitoring the Shelly Exporter.

## Quick Start

1. Start all services:
   ```bash
   cd development
   docker compose up -d
   ```

2. Access the services:
   - **Shelly Exporter**: http://localhost:10037/metrics
   - **Prometheus**: http://localhost:9090
   - **Grafana**: http://localhost:3001
     - Username: `admin`
     - Password: `admin`

3. View the dashboard:
   - Log into Grafana
   - The "Shelly Exporter Dashboard" should be automatically available
   - Or navigate to Dashboards → Shelly Exporter Dashboard

## Services

### Shelly Exporter
- Port: `10037`
- Metrics endpoint: `/metrics`
- Health endpoint: `/health`
- Uses the main project's Dockerfile (builds from parent directory)

### Prometheus
- Port: `9090`
- Scrapes Shelly Exporter every 15 seconds
- Data retention: 30 days
- Configuration: `prometheus/prometheus.yml`

### Grafana
- Port: `3001` (mapped from container port 3000 to avoid conflicts)
- Pre-configured with Prometheus datasource
- Pre-loaded with Shelly Exporter dashboard
- Default credentials: admin/admin (change in production!)

## Stopping Services

```bash
docker compose down
```

To remove all data (Prometheus and Grafana):
```bash
docker compose down -v
```

## Customization

### Prometheus Configuration
Edit `prometheus/prometheus.yml` to modify scrape intervals, add targets, or configure alerting rules.

### Grafana Dashboards
- Pre-provisioned dashboard: `grafana/dashboards/shelly-exporter.json`
- Add more dashboards by placing JSON files in `grafana/dashboards/`
- They will be automatically loaded on Grafana startup

### Grafana Datasources
Edit `grafana/provisioning/datasources/prometheus.yml` to modify the Prometheus connection or add additional datasources.

## Troubleshooting

### Check service status:
```bash
docker compose ps
```

### View logs:
```bash
docker compose logs -f [service-name]
# Examples:
docker compose logs -f shelly-exporter
docker compose logs -f prometheus
docker compose logs -f grafana
```

### Verify Prometheus is scraping:
1. Open http://localhost:9090
2. Navigate to Status → Targets
3. Check that `shelly-exporter` shows as UP

### Verify Grafana can connect to Prometheus:
1. Open http://localhost:3001
2. Navigate to Configuration → Data Sources
3. Click on Prometheus and click "Test" button
