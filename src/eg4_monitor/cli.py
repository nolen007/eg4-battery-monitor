#!/usr/bin/env python3
"""
Command-line interface for EG4 Battery Monitor.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .monitor import BatteryMonitor


def setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    
    # Reduce noise from libraries
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    logging.getLogger("paho").setLevel(logging.WARNING)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="eg4-monitor",
        description="Monitor EG4 WallMount 280Ah battery with Home Assistant MQTT integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  eg4-monitor                              # Run with defaults
  eg4-monitor --config config.yaml         # Use config file
  eg4-monitor --interval 60                # Poll every 60 seconds
  eg4-monitor --battery-ip 192.168.1.100   # Different battery IP
  eg4-monitor --no-ui                      # Headless mode
  eg4-monitor --json                       # Single JSON output
        """,
    )
    
    # General options
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    # Battery settings
    battery_group = parser.add_argument_group("Battery Settings")
    battery_group.add_argument(
        "--battery-ip",
        metavar="IP",
        help="Battery/adapter IP address [default: 192.168.130.139]",
    )
    battery_group.add_argument(
        "--battery-port",
        type=int,
        metavar="PORT",
        help="Modbus TCP port [default: 4196]",
    )
    battery_group.add_argument(
        "--device-id",
        type=int,
        metavar="ID",
        help="Modbus device ID [default: 1]",
    )
    
    # MQTT settings
    mqtt_group = parser.add_argument_group("MQTT Settings")
    mqtt_group.add_argument(
        "--mqtt-broker",
        metavar="HOST",
        help="MQTT broker address [default: localhost]",
    )
    mqtt_group.add_argument(
        "--mqtt-port",
        type=int,
        metavar="PORT",
        help="MQTT broker port [default: 1883]",
    )
    mqtt_group.add_argument(
        "--mqtt-user",
        metavar="USER",
        help="MQTT username",
    )
    mqtt_group.add_argument(
        "--mqtt-pass",
        metavar="PASS",
        help="MQTT password",
    )
    mqtt_group.add_argument(
        "--mqtt-topic",
        metavar="TOPIC",
        help="MQTT base topic [default: homeassistant]",
    )
    
    # Monitor settings
    monitor_group = parser.add_argument_group("Monitor Settings")
    monitor_group.add_argument(
        "--interval",
        type=int,
        metavar="SEC",
        help="Poll interval in seconds [default: 30]",
    )
    monitor_group.add_argument(
        "--no-ui",
        action="store_true",
        help="Disable terminal UI (headless mode)",
    )
    monitor_group.add_argument(
        "--json",
        action="store_true",
        help="Output single JSON reading and exit",
    )
    
    return parser.parse_args()


def build_config(args) -> Config:
    """Build configuration from arguments, file, and environment."""
    # Start with defaults
    config = Config()
    
    # Load from config file if specified
    if args.config:
        try:
            config = Config.from_file(args.config)
        except FileNotFoundError:
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Override with environment variables
    env_config = Config.from_env()
    
    # Override with command-line arguments
    if args.battery_ip:
        config.battery_ip = args.battery_ip
    if args.battery_port:
        config.battery_port = args.battery_port
    if args.device_id:
        config.device_id = args.device_id
    
    if args.mqtt_broker:
        config.mqtt_broker = args.mqtt_broker
    if args.mqtt_port:
        config.mqtt_port = args.mqtt_port
    if args.mqtt_user:
        config.mqtt_username = args.mqtt_user
    if args.mqtt_pass:
        config.mqtt_password = args.mqtt_pass
    if args.mqtt_topic:
        config.mqtt_base_topic = args.mqtt_topic
    
    if args.interval:
        config.poll_interval = args.interval
    if args.no_ui:
        config.ui_enabled = False
    if args.debug:
        config.debug = True
    
    return config


def main():
    """Main entry point."""
    args = parse_args()
    config = build_config(args)
    
    setup_logging(config.debug)
    
    # JSON mode: single reading and exit
    if args.json:
        from .battery import EG4ModbusReader
        
        reader = EG4ModbusReader(config)
        if not reader.connect():
            print(json.dumps({"error": "Connection failed"}))
            sys.exit(1)
        
        data = reader.poll()
        reader.disconnect()
        
        print(json.dumps(data.to_dict(), indent=2))
        sys.exit(0)
    
    # Normal monitor mode
    monitor = BatteryMonitor(config)
    
    try:
        monitor.start()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
