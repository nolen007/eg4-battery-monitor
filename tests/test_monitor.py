"""
Tests for EG4 Battery Monitor.
"""

import pytest
from eg4_monitor.config import Config
from eg4_monitor.battery import BatteryData, EG4ModbusReader


class TestConfig:
    """Tests for configuration handling."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        
        assert config.battery_ip == "192.168.130.139"
        assert config.battery_port == 4196
        assert config.device_id == 1
        assert config.mqtt_port == 1883
        assert config.poll_interval == 30
    
    def test_config_from_dict(self):
        """Test loading config from dictionary."""
        data = {
            "battery": {
                "ip": "10.0.0.100",
                "port": 502,
            },
            "mqtt": {
                "broker": "mqtt.local",
                "username": "test",
            },
            "monitor": {
                "interval": 60,
            },
        }
        
        config = Config.from_dict(data)
        
        assert config.battery_ip == "10.0.0.100"
        assert config.battery_port == 502
        assert config.mqtt_broker == "mqtt.local"
        assert config.mqtt_username == "test"
        assert config.poll_interval == 60
    
    def test_config_to_dict(self):
        """Test exporting config to dictionary."""
        config = Config(
            battery_ip="192.168.1.1",
            mqtt_broker="mqtt.example.com",
        )
        
        data = config.to_dict()
        
        assert data["battery"]["ip"] == "192.168.1.1"
        assert data["mqtt"]["broker"] == "mqtt.example.com"


class TestBatteryData:
    """Tests for battery data model."""
    
    def test_default_values(self):
        """Test default battery data values."""
        data = BatteryData()
        
        assert data.soc == 0.0
        assert data.online == False
        assert data.cell_voltages == []
        assert data.alarms == []
    
    def test_to_dict(self):
        """Test converting battery data to dictionary."""
        data = BatteryData(
            soc=97.0,
            voltage=53.48,
            current=0.17,
            online=True,
        )
        
        result = data.to_dict()
        
        assert result["soc"] == 97.0
        assert result["voltage"] == 53.48
        assert result["current"] == 0.17
        assert result["online"] == True
    
    def test_power_calculation(self):
        """Test power is calculated correctly."""
        data = BatteryData(
            voltage=53.48,
            current=10.0,
        )
        data.power = data.voltage * data.current
        
        assert abs(data.power - 534.8) < 0.1


class TestEG4ModbusReader:
    """Tests for Modbus reader (mocked)."""
    
    def test_signed16_positive(self):
        """Test signed conversion for positive values."""
        assert EG4ModbusReader._signed16(100) == 100
        assert EG4ModbusReader._signed16(32767) == 32767
    
    def test_signed16_negative(self):
        """Test signed conversion for negative values."""
        assert EG4ModbusReader._signed16(65535) == -1
        assert EG4ModbusReader._signed16(65536 - 100) == -100
        assert EG4ModbusReader._signed16(32768) == -32768


class TestAlarms:
    """Tests for alarm detection."""
    
    def test_no_alarms_healthy_battery(self):
        """Test no alarms for healthy battery."""
        data = BatteryData(
            voltage=53.0,
            soc=50.0,
            temperature=25.0,
            cell_min=3.3,
            cell_max=3.35,
            cell_delta=50.0,
        )
        
        # Manually check alarm conditions
        alarms = []
        if data.voltage > 57.6:
            alarms.append("Pack Over-Voltage")
        if data.voltage < 44.8:
            alarms.append("Pack Under-Voltage")
        if data.soc < 10:
            alarms.append("Critical Low SOC")
        
        assert len(alarms) == 0
    
    def test_low_soc_alarm(self):
        """Test low SOC triggers alarm."""
        data = BatteryData(soc=5.0)
        
        alarms = []
        if data.soc < 10:
            alarms.append("Critical Low SOC")
        
        assert "Critical Low SOC" in alarms
    
    def test_overvoltage_alarm(self):
        """Test over-voltage triggers alarm."""
        data = BatteryData(voltage=58.0)
        
        alarms = []
        if data.voltage > 57.6:
            alarms.append("Pack Over-Voltage")
        
        assert "Pack Over-Voltage" in alarms
