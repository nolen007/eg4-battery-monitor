"""
Main battery monitor coordinator.
"""

import logging
import time
from typing import Optional

from .config import Config
from .battery import BatteryData, EG4ModbusReader
from .mqtt import MQTTPublisher
from .ui import TerminalUI, HeadlessUI
from .web import WebServer

logger = logging.getLogger(__name__)


class BatteryMonitor:
    """Main application coordinator."""
    
    def __init__(self, config: Config):
        self.config = config
        self.reader = EG4ModbusReader(config)
        self.mqtt = MQTTPublisher(config)
        self.ui = TerminalUI() if config.ui_enabled else HeadlessUI()
        self.web: Optional[WebServer] = None
        self.running = False
        self.data = BatteryData()
        
        # Initialize web server if enabled
        if config.web_enabled:
            self.web = WebServer(host=config.web_host, port=config.web_port)
    
    def start(self):
        """Start the battery monitor."""
        self.running = True
        
        logger.info("Starting EG4 Battery Monitor")
        logger.info(f"Battery: {self.config.battery_ip}:{self.config.battery_port}")
        logger.info(f"MQTT: {self.config.mqtt_broker}:{self.config.mqtt_port}")
        logger.info(f"Poll interval: {self.config.poll_interval}s")
        
        # Start web server if enabled
        if self.web:
            self.web.start()
            logger.info(f"Web GUI: http://{self.config.web_host}:{self.config.web_port}")
        
        # Initial connections
        if not self.reader.connect():
            logger.warning("Could not connect to battery. Will retry...")
        
        if not self.mqtt.connect():
            logger.warning("Could not connect to MQTT. Will retry...")
        
        # Give connections time to establish
        time.sleep(1)
        
        # Main loop
        try:
            while self.running:
                self._poll_cycle()
                time.sleep(self.config.poll_interval)
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()
    
    def _poll_cycle(self):
        """Execute one poll cycle."""
        # Poll battery
        self.data = self.reader.poll()
        
        # Publish to MQTT
        self.mqtt.publish(self.data)
        
        # Update web server data
        if self.web:
            self.web.update_data(self.data, self.mqtt.connected)
        
        # Update terminal UI
        if self.config.ui_enabled:
            self.ui.render(self.data, self.mqtt.connected)
    
    def stop(self):
        """Stop the battery monitor."""
        self.running = False
        self.reader.disconnect()
        self.mqtt.disconnect()
        if self.web:
            self.web.stop()
        logger.info("Battery monitor stopped")
    
    def poll_once(self) -> BatteryData:
        """Poll once and return data (for external use)."""
        if not self.reader.connected:
            self.reader.connect()
        return self.reader.poll()
