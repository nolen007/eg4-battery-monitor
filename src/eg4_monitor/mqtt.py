"""
MQTT Publisher with Home Assistant auto-discovery support.
"""

import json
import logging
import time
from typing import Optional

import paho.mqtt.client as mqtt

from .config import Config
from .battery import BatteryData

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """Publishes battery data to MQTT with Home Assistant auto-discovery."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client: Optional[mqtt.Client] = None
        self._connected = False
        self._discovery_sent = False
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    def connect(self) -> bool:
        """Connect to the MQTT broker."""
        try:
            client_id = self.config.mqtt_client_id or f"eg4_monitor_{int(time.time())}"
            
            self.client = mqtt.Client(
                client_id=client_id,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
            
            # Set credentials if provided
            if self.config.mqtt_username:
                self.client.username_pw_set(
                    self.config.mqtt_username,
                    self.config.mqtt_password,
                )
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            
            # Connect
            self.client.connect(
                self.config.mqtt_broker,
                self.config.mqtt_port,
                keepalive=60,
            )
            
            # Start network loop
            self.client.loop_start()
            
            # Wait for connection
            for _ in range(50):  # 5 second timeout
                if self._connected:
                    return True
                time.sleep(0.1)
            
            logger.warning("MQTT connection timeout")
            return False
            
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            return False
    
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT connection."""
        if reason_code == 0:
            self._connected = True
            logger.info(f"Connected to MQTT broker at {self.config.mqtt_broker}")
        else:
            logger.error(f"MQTT connection failed: {reason_code}")
    
    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Handle MQTT disconnection."""
        self._connected = False
        self._discovery_sent = False
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
    
    def disconnect(self):
        """Disconnect from the MQTT broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        self._connected = False
        logger.info("Disconnected from MQTT broker")
    
    def _send_discovery(self):
        """Send Home Assistant MQTT discovery messages."""
        base = self.config.mqtt_base_topic
        device_id = self.config.device_id_slug
        device_name = self.config.device_name
        
        device_info = {
            "identifiers": [device_id],
            "name": device_name,
            "manufacturer": "EG4 Electronics",
            "model": "WallMount Indoor 280Ah",
            "sw_version": "1.0",
        }
        
        state_topic = f"{base}/sensor/{device_id}/state"
        
        # Define sensors: (id, name, unit, device_class, state_class)
        sensors = [
            ("soc", "State of Charge", "%", "battery", "measurement"),
            ("soh", "State of Health", "%", None, "measurement"),
            ("voltage", "Pack Voltage", "V", "voltage", "measurement"),
            ("current", "Current", "A", "current", "measurement"),
            ("power", "Power", "W", "power", "measurement"),
            ("temperature", "Temperature", "°C", "temperature", "measurement"),
            ("remaining_kwh", "Remaining Energy", "kWh", "energy", "measurement"),
            ("remaining_ah", "Remaining Capacity", "Ah", None, "measurement"),
            ("cell_min", "Cell Min Voltage", "V", "voltage", "measurement"),
            ("cell_max", "Cell Max Voltage", "V", "voltage", "measurement"),
            ("cell_delta", "Cell Delta", "mV", None, "measurement"),
            ("cycle_count", "Cycle Count", "cycles", None, "total_increasing"),
            ("alarm_count", "Alarm Count", "", None, "measurement"),
        ]
        
        # Publish sensor discovery
        for sensor_id, name, unit, device_class, state_class in sensors:
            config_topic = f"{base}/sensor/{device_id}_{sensor_id}/config"
            
            payload = {
                "name": f"{device_name} {name}",
                "unique_id": f"{device_id}_{sensor_id}",
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.{sensor_id} }}}}",
                "device": device_info,
            }
            
            if unit:
                payload["unit_of_measurement"] = unit
            if device_class:
                payload["device_class"] = device_class
            if state_class:
                payload["state_class"] = state_class
            
            self.client.publish(config_topic, json.dumps(payload), retain=True)
        
        # Binary sensors
        binary_sensors = [
            ("online", "Online", "connectivity"),
        ]
        
        for sensor_id, name, device_class in binary_sensors:
            config_topic = f"{base}/binary_sensor/{device_id}_{sensor_id}/config"
            
            payload = {
                "name": f"{device_name} {name}",
                "unique_id": f"{device_id}_{sensor_id}",
                "state_topic": state_topic,
                "value_template": f"{{{{ 'ON' if value_json.{sensor_id} else 'OFF' }}}}",
                "device_class": device_class,
                "device": device_info,
            }
            
            self.client.publish(config_topic, json.dumps(payload), retain=True)
        
        self._discovery_sent = True
        logger.info("MQTT discovery messages sent")
    
    def publish(self, data: BatteryData):
        """Publish battery data to MQTT."""
        if not self._connected:
            if not self.connect():
                return
        
        if not self._discovery_sent:
            self._send_discovery()
        
        device_id = self.config.device_id_slug
        base = self.config.mqtt_base_topic
        
        # Publish state
        state_topic = f"{base}/sensor/{device_id}/state"
        state_payload = {
            "soc": data.soc,
            "soh": data.soh,
            "voltage": round(data.voltage, 2),
            "current": round(data.current, 2),
            "power": round(data.power, 1),
            "temperature": round(data.temperature, 1),
            "remaining_kwh": round(data.remaining_kwh, 2),
            "remaining_ah": round(data.remaining_ah, 1),
            "cell_min": round(data.cell_min, 3),
            "cell_max": round(data.cell_max, 3),
            "cell_delta": round(data.cell_delta, 1),
            "cycle_count": data.cycle_count,
            "alarm_count": data.alarm_count,
            "online": data.online,
            "timestamp": data.timestamp,
        }
        
        self.client.publish(state_topic, json.dumps(state_payload), retain=True)
        
        # Publish attributes
        attr_topic = f"{base}/sensor/{device_id}/attributes"
        attr_payload = {
            "alarms": data.alarms,
            "cell_voltages": [round(v, 3) for v in data.cell_voltages],
            "status_raw": data.status,
            "design_capacity": data.design_capacity,
            "max_voltage": data.max_voltage,
            "max_current": data.max_current,
        }
        
        self.client.publish(attr_topic, json.dumps(attr_payload), retain=True)
        
        logger.debug(f"Published battery data to MQTT")
