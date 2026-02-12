"""
EG4 Battery Monitor
===================

A monitoring solution for EG4 WallMount 280Ah LiFePO4 batteries
with Home Assistant MQTT integration.

Example usage:
    from eg4_monitor import BatteryMonitor, Config
    
    config = Config(
        battery_ip="192.168.130.139",
        mqtt_broker="192.168.128.149"
    )
    
    monitor = BatteryMonitor(config)
    monitor.start()
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"

from .config import Config
from .battery import BatteryData, EG4ModbusReader
from .mqtt import MQTTPublisher
from .monitor import BatteryMonitor

__all__ = [
    "Config",
    "BatteryData",
    "EG4ModbusReader",
    "MQTTPublisher",
    "BatteryMonitor",
]
