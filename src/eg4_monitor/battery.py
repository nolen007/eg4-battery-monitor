"""
EG4 Battery data models and Modbus communication.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)


# =============================================================================
# EG4 WALLMOUNT 280Ah REGISTER MAP
# =============================================================================

# Format: register -> (name, divisor, unit, description)
EG4_REGISTER_MAP = {
    19: ('soc', 1, '%', 'State of Charge'),
    21: ('soh', 1, '%', 'State of Health'),
    22: ('pack_voltage', 100, 'V', 'Pack Voltage'),
    23: ('remaining_kwh', 100, 'kWh', 'Remaining Energy'),
    24: ('current', 100, 'A', 'Current'),
    25: ('full_energy_kwh', 1000, 'kWh', 'Full Energy Capacity'),
    26: ('remaining_ah', 100, 'Ah', 'Remaining Capacity'),
    27: ('design_capacity', 100, 'Ah', 'Design Capacity'),
    28: ('unknown_28', 1, '', 'Unknown'),
    30: ('temperature', 10, '°C', 'Battery Temperature'),
    32: ('soh_2', 1, '%', 'State of Health (alt)'),
    33: ('max_charge_voltage', 100, 'V', 'Max Charge Voltage'),
    35: ('max_current', 100, 'A', 'Max Current Rating'),
    37: ('cell_max_voltage', 1000, 'V', 'Highest Cell Voltage'),
    38: ('cell_min_voltage', 1000, 'V', 'Lowest Cell Voltage'),
    39: ('cycle_count', 1, '', 'Charge Cycles'),
    40: ('status_flags', 1, '', 'Status Flags'),
    41: ('cell_count', 1, '', 'Number of Cells'),
}

# EG4 Cell voltage registers
EG4_CELL_VOLTAGE_START = 113
EG4_CELL_VOLTAGE_COUNT = 16

# =============================================================================
# ECO-WORTHY 314Ah REGISTER MAP (PACE BMS)
# =============================================================================

ECOWORTHY_REGISTER_MAP = {
    0: ('current', 100, 'A', 'Current (signed)'),
    1: ('pack_voltage', 100, 'V', 'Pack Voltage'),
    2: ('soc', 1, '%', 'State of Charge'),
    3: ('soh', 1, '%', 'State of Health'),
    4: ('remaining_ah', 100, 'Ah', 'Remaining Capacity'),
    5: ('design_capacity', 100, 'Ah', 'Design Capacity'),
    6: ('full_capacity', 100, 'Ah', 'Full Capacity'),
    7: ('cycle_count', 1, '', 'Charge Cycles'),
}

# ECO-WORTHY Cell voltage registers (15-30 for 16 cells)
ECOWORTHY_CELL_VOLTAGE_START = 15
ECOWORTHY_CELL_VOLTAGE_COUNT = 16
# Temperature registers (31-36)
ECOWORTHY_TEMP_START = 31

# =============================================================================
# ECO-WORTHY / PACE BMS REGISTER MAP
# =============================================================================

ECOWORTHY_REGISTER_MAP = {
    "voltage": 1,           # ÷100
    "soc": 2,               # direct
    "soh": 3,               # direct
    "design_capacity": 4,   # ÷100 (in Ah)
    "cell_voltage_start": 15,
    "cell_voltage_count": 16,
    "temperature": 31,      # ÷10 (first temp sensor)
    "max_voltage": 107,     # ÷100 (from extended registers)
}

# Alarm thresholds
ALARM_THRESHOLDS = {
    "pack_overvoltage": 57.6,
    "pack_undervoltage": 44.8,
    "cell_overvoltage": 3.65,
    "cell_undervoltage": 2.5,
    "cell_imbalance_mv": 50,
    "high_temp": 55,
    "low_temp": -20,
    "critical_soc": 10,
    "overcurrent": 200,
}


# =============================================================================
# DATA MODEL
# =============================================================================

@dataclass
class BatteryData:
    """Battery telemetry data."""
    
    # Identity
    name: str = ""
    battery_id: str = ""
    
    timestamp: str = ""
    online: bool = False
    
    # State
    soc: float = 0.0
    soh: float = 0.0
    cycle_count: int = 0
    status: int = 0
    
    # Electrical
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    temperature: float = 0.0
    
    # Capacity
    design_capacity: float = 0.0
    full_capacity: float = 0.0
    remaining_ah: float = 0.0
    remaining_kwh: float = 0.0
    
    # Limits
    max_voltage: float = 0.0
    max_current: float = 0.0
    
    # Cell data
    cell_count: int = 0
    cell_min: float = 0.0
    cell_max: float = 0.0
    cell_delta: float = 0.0
    cell_voltages: List[float] = field(default_factory=list)
    
    # Alarms
    alarm_count: int = 0
    alarms: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "battery_id": self.battery_id,
            "timestamp": self.timestamp,
            "online": self.online,
            "soc": self.soc,
            "soh": self.soh,
            "cycle_count": self.cycle_count,
            "status": self.status,
            "voltage": round(self.voltage, 2),
            "current": round(self.current, 2),
            "power": round(self.power, 1),
            "temperature": round(self.temperature, 1),
            "design_capacity": self.design_capacity,
            "full_capacity": self.full_capacity,
            "remaining_ah": round(self.remaining_ah, 1),
            "remaining_kwh": round(self.remaining_kwh, 2),
            "max_voltage": self.max_voltage,
            "max_current": self.max_current,
            "cell_count": self.cell_count,
            "cell_min": round(self.cell_min, 3),
            "cell_max": round(self.cell_max, 3),
            "cell_delta": round(self.cell_delta, 1),
            "cell_voltages": [round(v, 3) for v in self.cell_voltages],
            "alarm_count": self.alarm_count,
            "alarms": self.alarms,
        }


# =============================================================================
# MODBUS READER
# =============================================================================

def slugify(name: str) -> str:
    """Convert a name to a slug for IDs."""
    import re
    slug = name.lower()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = slug.strip('_')
    return slug


class EG4ModbusReader:
    """Reads data from EG4/ECO-WORTHY battery via Modbus TCP."""
    
    def __init__(self, battery_config):
        """Initialize with a BatteryConfig object."""
        self.config = battery_config
        self.name = battery_config.name
        self.battery_id = slugify(battery_config.name)
        self.protocol = battery_config.protocol
        self.client: Optional[ModbusTcpClient] = None
        self._connected = False
    
    @property
    def connected(self) -> bool:
        return self._connected and self.client and self.client.is_socket_open()
    
    def connect(self) -> bool:
        """Connect to the battery via Modbus TCP."""
        try:
            self.client = ModbusTcpClient(
                host=self.config.ip,
                port=self.config.port,
                timeout=10,
            )
            self._connected = self.client.connect()
            
            if self._connected:
                logger.info(f"Connected to {self.name} at {self.config.ip}:{self.config.port}")
            else:
                logger.warning(f"Failed to connect to {self.name} at {self.config.ip}")
            
            return self._connected
            
        except Exception as e:
            logger.error(f"Modbus connection error for {self.name}: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """Close the Modbus connection."""
        if self.client:
            self.client.close()
        self._connected = False
        logger.info(f"Disconnected from {self.name}")
    
    def _read_registers(self, address: int, count: int) -> Optional[List[int]]:
        """Read holding registers from the battery."""
        try:
            result = self.client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.config.device_id,
            )
            
            if result.isError():
                logger.warning(f"Modbus read error at {address} for {self.name}: {result}")
                return None
            
            return result.registers
            
        except Exception as e:
            logger.error(f"Modbus read exception for {self.name}: {e}")
            return None
    
    @staticmethod
    def _signed16(value: int) -> int:
        """Convert unsigned 16-bit to signed."""
        return value - 65536 if value > 32767 else value
    
    def poll(self) -> BatteryData:
        """Poll the battery and return current data."""
        data = BatteryData(
            name=self.name,
            battery_id=self.battery_id,
            timestamp=datetime.now().isoformat(),
        )
        
        # Ensure connection
        if not self.connected:
            if not self.connect():
                return data
        
        # Use appropriate protocol
        if self.protocol == "ecoworthy":
            return self._poll_ecoworthy(data)
        else:
            return self._poll_eg4(data)
    
    def _poll_eg4(self, data: BatteryData) -> BatteryData:
        """Poll using EG4 register map."""
        # Read main registers (0-60)
        regs = self._read_registers(0, 60)
        if not regs:
            self._connected = False
            return data
        
        data.online = True
        
        # Parse registers using corrected EG4 format
        # Note: SOC is at reg 21, not 19 (19 appears to be something else)
        data.soc = float(regs[21])
        data.soh = float(regs[32])  # SOH at reg 32
        data.voltage = regs[22] / 100.0
        data.remaining_kwh = regs[23] / 100.0
        data.current = self._signed16(regs[24]) / 100.0
        data.power = data.voltage * data.current
        # reg 25 = full_energy_kwh (÷1000)
        data.remaining_ah = regs[26] / 100.0
        data.design_capacity = regs[27] / 100.0
        data.full_capacity = regs[27] / 100.0  # Use design as full for now
        data.temperature = regs[30] / 10.0
        data.max_voltage = regs[33] / 100.0
        data.max_current = regs[35] / 100.0
        data.cell_max = regs[37] / 1000.0
        data.cell_min = regs[38] / 1000.0
        data.cycle_count = regs[39]
        data.status = regs[40]
        data.cell_count = regs[41]
        data.cell_delta = (data.cell_max - data.cell_min) * 1000
        
        # Read cell voltages (registers 113-128)
        cell_regs = self._read_registers(EG4_CELL_VOLTAGE_START, EG4_CELL_VOLTAGE_COUNT)
        if cell_regs:
            data.cell_voltages = [v / 1000.0 for v in cell_regs]
        
        # Check for alarms
        data.alarms = self._check_alarms(data)
        data.alarm_count = len(data.alarms)
        
        logger.debug(f"Polled {self.name}: SOC={data.soc}%, V={data.voltage}V, I={data.current}A")
        
        return data
    
    def _poll_ecoworthy(self, data: BatteryData) -> BatteryData:
        """Poll using ECO-WORTHY/PACE BMS register map."""
        # Read main registers (0-40)
        regs = self._read_registers(0, 40)
        if not regs:
            self._connected = False
            return data
        
        data.online = True
        
        # Parse ECO-WORTHY registers
        data.current = self._signed16(regs[0]) / 100.0
        data.voltage = regs[1] / 100.0
        data.soc = float(regs[2])
        data.soh = float(regs[3])
        data.remaining_ah = regs[4] / 100.0
        data.design_capacity = regs[5] / 100.0
        data.full_capacity = regs[6] / 100.0
        data.cycle_count = regs[7]
        data.power = data.voltage * data.current
        data.remaining_kwh = (data.remaining_ah * data.voltage) / 1000.0
        
        # Cell voltages are in registers 15-30
        data.cell_count = 16
        data.cell_voltages = []
        for i in range(ECOWORTHY_CELL_VOLTAGE_START, ECOWORTHY_CELL_VOLTAGE_START + ECOWORTHY_CELL_VOLTAGE_COUNT):
            voltage = regs[i] / 1000.0
            # Filter out invalid readings (65535 = 0xFFFF)
            if regs[i] != 65535 and 2.0 <= voltage <= 4.0:
                data.cell_voltages.append(voltage)
        
        if data.cell_voltages:
            data.cell_min = min(data.cell_voltages)
            data.cell_max = max(data.cell_voltages)
            data.cell_delta = (data.cell_max - data.cell_min) * 1000
            data.cell_count = len(data.cell_voltages)
        
        # Temperature from register 31 (first temp sensor)
        if regs[31] != 65535 and regs[31] < 1000:
            data.temperature = regs[31] / 10.0
        
        # Check for alarms
        data.alarms = self._check_alarms(data)
        data.alarm_count = len(data.alarms)
        
        logger.debug(f"Polled {self.name}: SOC={data.soc}%, V={data.voltage}V, I={data.current}A")
        
        return data
    
    def _check_alarms(self, data: BatteryData) -> List[str]:
        """Check for alarm conditions."""
        alarms = []
        thresholds = ALARM_THRESHOLDS
        
        # Voltage alarms
        if data.voltage > thresholds["pack_overvoltage"]:
            alarms.append("Pack Over-Voltage")
        if data.voltage < thresholds["pack_undervoltage"]:
            alarms.append("Pack Under-Voltage")
        
        # Cell voltage alarms
        if data.cell_max > thresholds["cell_overvoltage"]:
            alarms.append("Cell Over-Voltage")
        if data.cell_min < thresholds["cell_undervoltage"]:
            alarms.append("Cell Under-Voltage")
        
        # Cell imbalance
        if data.cell_delta > thresholds["cell_imbalance_mv"]:
            alarms.append("Cell Imbalance")
        
        # Temperature alarms
        if data.temperature > thresholds["high_temp"]:
            alarms.append("High Temperature")
        if data.temperature < thresholds["low_temp"]:
            alarms.append("Low Temperature")
        
        # SOC alarms
        if data.soc < thresholds["critical_soc"]:
            alarms.append("Critical Low SOC")
        
        # Current alarms
        if abs(data.current) > thresholds["overcurrent"]:
            alarms.append("Over Current")
        
        return alarms
