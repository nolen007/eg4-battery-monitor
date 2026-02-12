# EG4 Battery Monitor

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-MQTT-blue.svg)](https://www.home-assistant.io/)

A Python-based monitoring solution for **EG4 WallMount 280Ah LiFePO4 batteries** with real-time terminal UI and Home Assistant integration via MQTT.

![Terminal UI Screenshot](docs/images/terminal-ui.png)

## Features

- 🔋 **Real-time Battery Monitoring** - Poll battery data every 30 seconds (configurable)
- 📊 **Terminal UI** - Live dashboard with SOC, voltage, current, temperature, and cell voltages
- 🏠 **Home Assistant Integration** - MQTT auto-discovery for seamless smart home integration
- ⚠️ **Alarm Detection** - Automatic alerts for over/under voltage, temperature, and cell imbalance
- 📈 **Cell-level Monitoring** - Individual cell voltages with min/max/delta tracking
- 🔌 **Modbus RTU over TCP** - Works with Waveshare RS485-to-Ethernet adapters

## Supported Hardware

- **Battery**: EG4 WallMount Indoor 280Ah (14.3kWh)
- **Adapter**: Waveshare RS485 TO ETH (B) or similar RS485-to-Ethernet converters
- **Protocol**: Modbus RTU over TCP (EG4/LuxPower proprietary register map)

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/eg4-battery-monitor.git
cd eg4-battery-monitor

# Install with pip
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt
```

### Wiring

Connect your EG4 battery to the Waveshare RS485-to-ETH adapter:

| RJ45 Pin | Wire Color (T568B) | Waveshare Terminal |
|----------|-------------------|-------------------|
| Pin 1 | White/Orange | 485A (A+) |
| Pin 2 | Orange | 485B (B-) |

### Configuration

Copy the example config and edit with your settings:

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

### Running

```bash
# Run with default settings
eg4-monitor

# Or run directly
python -m eg4_monitor

# With custom settings
eg4-monitor --battery-ip 192.168.1.100 --mqtt-broker 192.168.1.50
```

## Configuration

### Command Line Options

```
Usage: eg4-monitor [OPTIONS]

Battery Settings:
  --battery-ip TEXT      Battery/adapter IP address [default: 192.168.130.139]
  --battery-port INT     Modbus TCP port [default: 4196]
  --device-id INT        Modbus device ID [default: 1]

MQTT Settings:
  --mqtt-broker TEXT     MQTT broker address [default: localhost]
  --mqtt-port INT        MQTT broker port [default: 1883]
  --mqtt-user TEXT       MQTT username
  --mqtt-pass TEXT       MQTT password

General:
  --interval INT         Poll interval in seconds [default: 30]
  --no-ui                Disable terminal UI (headless mode)
  --json                 Output JSON to stdout
  --debug                Enable debug logging
```

### Configuration File

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
```

### Environment Variables

```bash
export EG4_BATTERY_IP="192.168.130.139"
export EG4_MQTT_BROKER="192.168.128.149"
export EG4_MQTT_USER="homeassistant"
export EG4_MQTT_PASS="your-password"
```

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
| `sensor.eg4_wallmount_280ah_remaining_ah` | Remaining Capacity | Ah |
| `sensor.eg4_wallmount_280ah_cell_min` | Lowest Cell Voltage | V |
| `sensor.eg4_wallmount_280ah_cell_max` | Highest Cell Voltage | V |
| `sensor.eg4_wallmount_280ah_cell_delta` | Cell Voltage Difference | mV |
| `sensor.eg4_wallmount_280ah_cycle_count` | Charge Cycles | cycles |
| `binary_sensor.eg4_wallmount_280ah_online` | Connection Status | |

### Example Lovelace Card

```yaml
type: entities
title: EG4 Battery
entities:
  - entity: sensor.eg4_wallmount_280ah_soc
    name: State of Charge
  - entity: sensor.eg4_wallmount_280ah_power
    name: Power
  - entity: sensor.eg4_wallmount_280ah_voltage
    name: Voltage
  - entity: sensor.eg4_wallmount_280ah_temperature
    name: Temperature
  - entity: sensor.eg4_wallmount_280ah_cell_delta
    name: Cell Balance
```

## Register Map

The EG4 WallMount 280Ah uses a proprietary Modbus register map:

| Register | Scale | Description |
|----------|-------|-------------|
| 19 | ×1 | State of Charge (%) |
| 21 | ×1 | State of Health (%) |
| 22 | ÷100 | Pack Voltage (V) |
| 24 | ÷100 | Current (A, signed) |
| 25 | ÷100 | Remaining Energy (kWh) |
| 26 | ÷100 | Design Capacity (Ah) |
| 27 | ÷100 | Full Charge Capacity (Ah) |
| 28 | ÷10 | Remaining Capacity (Ah) |
| 30 | ÷10 | Temperature (°C) |
| 33 | ÷100 | Max Charge Voltage (V) |
| 35 | ÷100 | Max Current (A) |
| 37 | ÷1000 | Highest Cell Voltage (V) |
| 38 | ÷1000 | Lowest Cell Voltage (V) |
| 39 | ×1 | Cycle Count |
| 40 | ×1 | Status Flags |
| 41 | ×1 | Cell Count |
| 113-128 | ÷1000 | Individual Cell Voltages (V) |

## Running as a Service

### Systemd (Linux)

```bash
sudo cp examples/eg4-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable eg4-monitor
sudo systemctl start eg4-monitor
```

### Docker

```bash
docker build -t eg4-monitor .
docker run -d --name eg4-monitor \
  -e EG4_BATTERY_IP=192.168.130.139 \
  -e EG4_MQTT_BROKER=192.168.128.149 \
  eg4-monitor
```

## Troubleshooting

### Connection Issues

1. **Verify wiring**: Pin 1 (White/Orange) → 485A, Pin 2 (Orange) → 485B
2. **Check IP address**: Ensure the Waveshare adapter IP is correct
3. **Verify DIP switch**: Battery should be set to address 1 (DIP switch 1 ON)
4. **Check protocol**: Battery should be set to RS485 mode with P01-EG4 protocol

### No Data / Timeout

- Try swapping A and B wires (polarity may be reversed)
- Check Waveshare adapter baud rate matches (9600, 8N1)
- Ensure no other device is communicating with the battery

### MQTT Issues

- Verify broker IP, port, username, and password
- Check firewall rules allow connection to MQTT port
- Ensure MQTT broker is running and accessible

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- EG4 Electronics for the battery documentation
- The Home Assistant community for MQTT integration patterns
- PyModbus contributors

## Disclaimer

This project is not affiliated with or endorsed by EG4 Electronics. Use at your own risk. Always follow proper safety procedures when working with lithium batteries.
