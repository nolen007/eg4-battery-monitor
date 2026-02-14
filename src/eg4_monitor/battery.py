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

EG4_REGISTER_MAP = {
    "soc": 19,
    "soh": 21,
    "voltage": 22,
    "current": 24,
    "remaining_kwh": 25,
    "design_capacity": 26,
    "full_capacity": 27,
    "remaining_ah": 28,
    "temperature": 30,
    "max_voltage": 33,
    "max_current": 35,
    "cell_max": 37,
    "cell_min": 38,
    "cycle_count": 39,
    "status": 40,
    "cell_count": 41,
    "cell_voltage_start": 113,
    "cell_voltage_count": 16,
}

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
        
        # Parse registers - EG4 format
        data.soc = float(regs[19])
        data.soh = float(regs[21])
        data.voltage = regs[22] / 100.0
        data.current = self._signed16(regs[24]) / 100.0
        data.power = data.voltage * data.current
        data.remaining_kwh = regs[25] / 100.0
        data.design_capacity = regs[26] / 100.0
        data.full_capacity = regs[27] / 100.0
        data.remaining_ah = regs[28] / 10.0
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
        cell_regs = self._read_registers(CELL_VOLTAGE_START, CELL_VOLTAGE_COUNT)
        if cell_regs:
            data.cell_voltages = [v / 1000.0 for v in cell_regs]
        
        # Check for alarms
        data.alarms = self._check_alarms(data)
        data.alarm_count = len(data.alarms)
        
        logger.debug(f"Polled {self.name}: SOC={data.soc}%, V={data.voltage}V, I={data.current}A")
        
        return data
    
    def _poll_ecoworthy(self, data: BatteryData) -> BatteryData:
        """Poll using ECO-WORTHY/PACE register map."""
        # Read main registers (0-40)
        regs = self._read_registers(0, 40)
        if not regs:
            self._connected = False
            return data
        
        data.online = True
        
        # Parse registers - ECO-WORTHY format
        # Reg 1: Voltage (÷100)
        # Reg 2: SOC
        # Reg 3: SOH
        # Reg 4: Remaining Ah (÷100)
        # Reg 5: Design Capacity (÷100)
        # Reg 6: Full Capacity (÷100)
        # Reg 7: Current (÷100, signed)
        # Regs 15-30: Cell voltages (÷1000)
        # Regs 31-35: Temperatures (÷10)
        
        data.voltage = regs[1] / 100.0
        data.soc = float(regs[2])
        data.soh = float(regs[3])
        data.remaining_ah = regs[4] / 100.0
        data.design_capacity = regs[5] / 100.0
        data.full_capacity = regs[6] / 100.0
        data.current = self._signed16(regs[7]) / 100.0
        data.power = data.voltage * data.current
        data.remaining_kwh = data.voltage * data.remaining_ah / 1000.0
        
        # Cell voltages at registers 15-30 (16 cells)
        data.cell_voltages = [regs[i] / 1000.0 for i in range(15, 31)]
        data.cell_count = 16
        
        # Filter out invalid cells (65.535V = 0xFFFF) and calculate min/max
        valid_cells = [v for v in data.cell_voltages if 2.0 < v < 4.5]
        if valid_cells:
            data.cell_min = min(valid_cells)
            data.cell_max = max(valid_cells)
            data.cell_delta = (data.cell_max - data.cell_min) * 1000
        else:
            data.cell_min = 0
            data.cell_max = 0
            data.cell_delta = 0
        
        # Temperature - average of sensors at registers 31-35
        temps = [regs[i] / 10.0 for i in range(31, 36) if regs[i] < 1000]
        data.temperature = sum(temps) / len(temps) if temps else 0
        
        # These aren't available in same format, use defaults
        data.cycle_count = 0
        data.status = 0
        data.max_voltage = 58.4  # Typical for 16S LiFePO4
        data.max_current = 200.0
        
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
