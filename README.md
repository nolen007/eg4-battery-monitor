# EG4 Battery Monitor

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-MQTT-blue.svg)](https://www.home-assistant.io/)

A Python-based monitoring solution for **EG4 WallMount 280Ah LiFePO4 batteries** with real-time terminal UI and Home Assistant integration via MQTT.

## Features

- 🔋 **Real-time Battery Monitoring** - Poll battery data every 30 seconds (configurable)
- 📊 **Terminal UI** - Live dashboard with SOC, voltage, current, temperature, and cell voltages
- 🏠 **Home Assistant Integration** - MQTT auto-discovery for seamless smart home integration
- ⚠️ **Alarm Detection** - Automatic alerts for over/under voltage, temperature, and cell imbalance
- 📈 **Cell-level Monitoring** - Individual cell voltages with min/max/delta tracking

## Supported Hardware

- **Battery**: EG4 WallMount Indoor 280Ah (14.3kWh)
- **Adapter**: Waveshare RS485 TO ETH (B) or similar RS485-to-Ethernet converters
- **Protocol**: Modbus RTU over TCP (EG4/LuxPower proprietary register map)

---

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/nolen007/eg4-battery-monitor.git
cd eg4-battery-monitor
```

### Step 2: Create a Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install the Package

```bash
pip install -e .
```

This installs the `eg4-monitor` command that you can run from anywhere.

### Step 4: Verify Installation

```bash
eg4-monitor --help
```

You should see:
```
usage: eg4-monitor [-h] [-V] [-c CONFIG] [--debug] [--battery-ip IP] ...
```

---

## Quick Start

### Option A: Run with Command-Line Arguments

```bash
eg4-monitor \
  --battery-ip 192.168.130.139 \
  --mqtt-broker 192.168.128.149 \
  --mqtt-user blake \
  --mqtt-pass YourPassword
```

### Option B: Run with Config File

1. Copy the example config:
   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit with your settings:
   ```bash
   nano config.yaml
   ```

3. Run:
   ```bash
   eg4-monitor --config config.yaml
   ```

### Option C: Run with Environment Variables

```bash
export EG4_BATTERY_IP="192.168.130.139"
export EG4_MQTT_BROKER="192.168.128.149"
export EG4_MQTT_USER="blake"
export EG4_MQTT_PASS="YourPassword"

eg4-monitor
```

---

## Wiring

Connect your EG4 battery to the Waveshare RS485-to-ETH adapter:

| RJ45 Pin | Wire Color (T568B) | Waveshare Terminal |
|----------|-------------------|-------------------|
| Pin 1    | White/Orange      | 485A (A+)         |
| Pin 2    | Orange            | 485B (B-)         |

See [docs/WIRING.md](docs/WIRING.md) for detailed wiring diagrams.

---

## Command-Line Options

```
Usage: eg4-monitor [OPTIONS]

Battery Settings:
  --battery-ip IP        Battery/adapter IP address [default: 192.168.130.139]
  --battery-port PORT    Modbus TCP port [default: 4196]
  --device-id ID         Modbus device ID [default: 1]

MQTT Settings:
  --mqtt-broker HOST     MQTT broker address [default: localhost]
  --mqtt-port PORT       MQTT broker port [default: 1883]
  --mqtt-user USER       MQTT username
  --mqtt-pass PASS       MQTT password

Monitor Settings:
  --interval SEC         Poll interval in seconds [default: 30]
  --no-ui                Disable terminal UI (for background/service mode)
  --json                 Output single JSON reading and exit

General:
  -c, --config FILE      Path to YAML config file
  --debug                Enable debug logging
  -V, --version          Show version and exit
  -h, --help             Show this help message
```

---

## Running as a Background Service

### Using systemd (Linux)

1. Edit the service file with your paths:
   ```bash
   nano examples/eg4-monitor.service
   ```

2. Install and start:
   ```bash
   sudo cp examples/eg4-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable eg4-monitor
   sudo systemctl start eg4-monitor
   ```

3. Check status:
   ```bash
   sudo systemctl status eg4-monitor
   sudo journalctl -u eg4-monitor -f
   ```

### Using Docker

```bash
docker build -t eg4-monitor .

docker run -d \
  --name eg4-monitor \
  --restart unless-stopped \
  -e EG4_BATTERY_IP=192.168.130.139 \
  -e EG4_MQTT_BROKER=192.168.128.149 \
  -e EG4_MQTT_USER=blake \
  -e EG4_MQTT_PASS=YourPassword \
  eg4-monitor
```

Or use Docker Compose:
```bash
# Edit docker-compose.yml with your settings first
docker-compose up -d
```

---

## Home Assistant Integration

The monitor automatically publishes MQTT discovery messages. After starting, your battery will appear in Home Assistant under **Settings → Devices & Services → MQTT**.

### Sensors Created

| Entity ID | Description | Unit |
|-----------|-------------|------|
| `sensor.eg4_wallmount_280ah_soc` | State of Charge | % |
| `sensor.eg4_wallmount_280ah_soh` | State of Health | % |
| `sensor.eg4_wallmount_280ah_voltage` | Pack Voltage | V |
| `sensor.eg4_wallmount_280ah_current` | Current (+discharge/-charge) | A |
| `sensor.eg4_wallmount_280ah_power` | Power | W |
| `sensor.eg4_wallmount_280ah_temperature` | Temperature | °C |
| `sensor.eg4_wallmount_280ah_remaining_kwh` | Remaining Energy | kWh |
| `sensor.eg4_wallmount_280ah_cell_min` | Lowest Cell Voltage | V |
| `sensor.eg4_wallmount_280ah_cell_max` | Highest Cell Voltage | V |
| `sensor.eg4_wallmount_280ah_cell_delta` | Cell Voltage Difference | mV |
| `sensor.eg4_wallmount_280ah_cycle_count` | Charge Cycles | cycles |
| `binary_sensor.eg4_wallmount_280ah_online` | Connection Status | |

### Example Lovelace Card

See [examples/home-assistant-cards.yaml](examples/home-assistant-cards.yaml) for dashboard examples.

---

## Configuration File Format

Create `config.yaml`:

```yaml
battery:
  ip: "192.168.130.139"
  port: 4196
  device_id: 1

mqtt:
  broker: "192.168.128.149"
  port: 1883
  username: "homeassistant"
  password: "your-password"
  base_topic: "homeassistant"

monitor:
  interval: 30
  ui_enabled: true
  debug: false
```

---

## Troubleshooting

### "command not found: eg4-monitor"

Make sure you activated the virtual environment:
```bash
source venv/bin/activate
```

Or install globally (not recommended):
```bash
pip install .
```

### Connection Failed

1. **Check wiring**: Pin 1 → 485A, Pin 2 → 485B
2. **Try swapping A/B**: Polarity may be reversed
3. **Verify IP**: Make sure the Waveshare adapter IP is correct
4. **Check DIP switch**: Battery should be address 1 (DIP 1 ON, others OFF)

### MQTT Not Connecting

1. Verify broker IP and port
2. Check username/password
3. Ensure firewall allows connection

---

## Register Map

For developers - the EG4 WallMount 280Ah register map:

| Register | Scale | Description |
|----------|-------|-------------|
| 19 | ×1 | State of Charge (%) |
| 21 | ×1 | State of Health (%) |
| 22 | ÷100 | Pack Voltage (V) |
| 24 | ÷100 | Current (A, signed) |
| 25 | ÷100 | Remaining Energy (kWh) |
| 30 | ÷10 | Temperature (°C) |
| 37 | ÷1000 | Highest Cell Voltage (V) |
| 38 | ÷1000 | Lowest Cell Voltage (V) |
| 39 | ×1 | Cycle Count |
| 113-128 | ÷1000 | Individual Cell Voltages (V) |

---

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This project is not affiliated with or endorsed by EG4 Electronics. Use at your own risk.
