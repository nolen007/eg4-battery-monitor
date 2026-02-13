"""
Configuration management for EG4 Battery Monitor.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Config:
    """Configuration settings for the battery monitor."""
    
    # Modbus/Battery Settings
    battery_ip: str = "192.168.130.139"
    battery_port: int = 4196
    device_id: int = 1
    
    # MQTT Settings
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_base_topic: str = "homeassistant"
    mqtt_client_id: str = ""
    
    # Web Server Settings
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 5000
    
    # Monitor Settings
    poll_interval: int = 30
    ui_enabled: bool = True
    debug: bool = False
    
    # Device identification
    device_name: str = "EG4 WallMount 280Ah"
    device_id_slug: str = "eg4_wallmount_280ah"
    
    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create config from a dictionary."""
        config = cls()
        
        # Battery settings
        if "battery" in data:
            battery = data["battery"]
            config.battery_ip = battery.get("ip", config.battery_ip)
            config.battery_port = battery.get("port", config.battery_port)
            config.device_id = battery.get("device_id", config.device_id)
        
        # MQTT settings
        if "mqtt" in data:
            mqtt = data["mqtt"]
            config.mqtt_broker = mqtt.get("broker", config.mqtt_broker)
            config.mqtt_port = mqtt.get("port", config.mqtt_port)
            config.mqtt_username = mqtt.get("username", config.mqtt_username)
            config.mqtt_password = mqtt.get("password", config.mqtt_password)
            config.mqtt_base_topic = mqtt.get("base_topic", config.mqtt_base_topic)
            config.mqtt_client_id = mqtt.get("client_id", config.mqtt_client_id)
        
        # Web settings
        if "web" in data:
            web = data["web"]
            config.web_enabled = web.get("enabled", config.web_enabled)
            config.web_host = web.get("host", config.web_host)
            config.web_port = web.get("port", config.web_port)
        
        # Monitor settings
        if "monitor" in data:
            monitor = data["monitor"]
            config.poll_interval = monitor.get("interval", config.poll_interval)
            config.ui_enabled = monitor.get("ui_enabled", config.ui_enabled)
            config.debug = monitor.get("debug", config.debug)
        
        # Device settings
        if "device" in data:
            device = data["device"]
            config.device_name = device.get("name", config.device_name)
            config.device_id_slug = device.get("id", config.device_id_slug)
        
        return config
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        config = cls()
        
        # Battery settings
        config.battery_ip = os.getenv("EG4_BATTERY_IP", config.battery_ip)
        config.battery_port = int(os.getenv("EG4_BATTERY_PORT", config.battery_port))
        config.device_id = int(os.getenv("EG4_DEVICE_ID", config.device_id))
        
        # MQTT settings
        config.mqtt_broker = os.getenv("EG4_MQTT_BROKER", config.mqtt_broker)
        config.mqtt_port = int(os.getenv("EG4_MQTT_PORT", config.mqtt_port))
        config.mqtt_username = os.getenv("EG4_MQTT_USER", config.mqtt_username)
        config.mqtt_password = os.getenv("EG4_MQTT_PASS", config.mqtt_password)
        config.mqtt_base_topic = os.getenv("EG4_MQTT_TOPIC", config.mqtt_base_topic)
        
        # Monitor settings
        config.poll_interval = int(os.getenv("EG4_POLL_INTERVAL", config.poll_interval))
        config.debug = os.getenv("EG4_DEBUG", "").lower() in ("true", "1", "yes")
        
        return config
    
    def to_dict(self) -> dict:
        """Export configuration as a dictionary."""
        return {
            "battery": {
                "ip": self.battery_ip,
                "port": self.battery_port,
                "device_id": self.device_id,
            },
            "mqtt": {
                "broker": self.mqtt_broker,
                "port": self.mqtt_port,
                "username": self.mqtt_username,
                "password": "***" if self.mqtt_password else "",
                "base_topic": self.mqtt_base_topic,
            },
            "web": {
                "enabled": self.web_enabled,
                "host": self.web_host,
                "port": self.web_port,
            },
            "monitor": {
                "interval": self.poll_interval,
                "ui_enabled": self.ui_enabled,
                "debug": self.debug,
            },
            "device": {
                "name": self.device_name,
                "id": self.device_id_slug,
            },
        }
    
    def save(self, path: str | Path):
        """Save configuration to a YAML file."""
        path = Path(path)
        data = self.to_dict()
        # Don't save masked password
        data["mqtt"]["password"] = self.mqtt_password
        
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
