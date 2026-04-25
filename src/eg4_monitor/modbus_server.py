"""
Virtual Modbus TCP Server — Solar Assistant gateway.

Presents all monitored batteries as a single combined Pylontech-compatible
Modbus device that Solar Assistant (or any Modbus master) can poll over TCP.

Register map (Pylontech / PACE BMS compatible, holding registers):
  0   current         (int16,  ×100 A,   signed — positive = charging)
  1   voltage         (uint16, ×100 V)
  2   soc             (uint16, 1 %)
  3   soh             (uint16, 1 %)
  4   remaining_ah    (uint16, ×100 Ah)
  5   design_capacity (uint16, ×100 Ah)
  6   full_capacity   (uint16, ×100 Ah)
  7   cycle_count     (uint16, 1)
  8   max_voltage     (uint16, ×100 V)
  9   max_current     (uint16, ×100 A)
  10  temperature     (int16,  ×10 °C,   signed)
  11  alarm_count     (uint16, 1)
  12  status_flags    (uint16, bitmask)
  13  power           (int16,  1 W,      signed)
  14  remaining_kwh   (uint16, ×100 kWh)
  15  cell_count      (uint16, 1)
  16  cell_min        (uint16, ×1000 V)
  17  cell_max        (uint16, ×1000 V)
  18  cell_delta      (uint16, 1 mV)
  19  online_count    (uint16, 1)
  20  battery_count   (uint16, 1)

  -- per-cell voltages (up to 32 cells) --
  100–131  cell_voltages[0..31]  (uint16, ×1000 V)

  -- alarm bitmask word --
  200  alarm_bitmask   (uint16, see ALARM_BITS below)

Solar Assistant setup:
  Settings → Battery monitor → Pylontech (RS485/Modbus) → TCP
  IP: <this monitor's IP>   Port: 502 (or modbus_server_port in config)
  Device ID: 1
"""

import asyncio
import logging
import threading
from typing import List, Optional

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer
from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.framer import FramerType

from .battery import BatteryData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alarm bitmask — matches the alarm names used in BatteryData
# ---------------------------------------------------------------------------

ALARM_BIT = {
    "Pack Over-Voltage":      0x0001,
    "Pack Under-Voltage":     0x0002,
    "Cell Over-Voltage":      0x0004,
    "Cell Under-Voltage":     0x0008,
    "High Temperature":       0x0010,
    "Low Temperature":        0x0020,
    "Over Current":           0x0040,
    "Short Circuit":          0x0080,
    "Cell Imbalance":         0x0100,
    "Critical Low SOC":       0x0200,
    "BMS Internal Fault":     0x0400,
    "Charge FET Open":        0x0800,
    "Discharge FET Open":     0x1000,
}

MAX_CELLS = 32   # register space reserved for cell voltages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_uint16(value: float, scale: float = 1.0) -> int:
    """Scale a float, clamp to uint16 range [0, 65535]."""
    raw = round(value * scale)
    return max(0, min(65535, raw))


def _to_int16(value: float, scale: float = 1.0) -> int:
    """Scale a float, clamp to int16 range [-32768, 32767], encode as uint16."""
    raw = round(value * scale)
    raw = max(-32768, min(32767, raw))
    return raw if raw >= 0 else raw + 65536


def _alarm_bitmask(alarms: List[str]) -> int:
    mask = 0
    for alarm in alarms:
        mask |= ALARM_BIT.get(alarm, 0)
    return mask


# ---------------------------------------------------------------------------
# Data aggregation
# ---------------------------------------------------------------------------

def aggregate(batteries: List[BatteryData]) -> dict:
    """
    Combine all online battery data into a single virtual pack, matching
    exactly what the web dashboard displays.

    Aggregation rules:
      - voltage        : average of online packs
      - current        : sum (parallel packs)
      - soc            : average weighted by capacity
      - soh            : minimum (weakest pack)
      - remaining_ah   : sum
      - design_capacity: sum
      - full_capacity  : sum
      - temperature    : maximum (hottest pack)
      - remaining_kwh  : sum
      - power          : sum
      - alarms         : union of all alarm strings
      - cycle_count    : maximum
      - max_voltage    : minimum max_charge_voltage (most conservative limit)
      - max_current    : sum of max_charge_currents
    """
    online = [b for b in batteries if b.online]
    if not online:
        return {}

    total_cap = sum(b.full_capacity for b in online) or 1.0

    agg = {
        "voltage":         sum(b.voltage for b in online) / len(online),
        "current":         sum(b.current for b in online),
        "power":           sum(b.power   for b in online),
        "temperature":     max(b.temperature for b in online),
        "soc":             sum(b.soc * (b.full_capacity / total_cap) for b in online),
        "soh":             min(b.soh for b in online),
        "remaining_ah":    sum(b.remaining_ah    for b in online),
        "design_capacity": sum(b.design_capacity for b in online),
        "full_capacity":   sum(b.full_capacity   for b in online),
        "remaining_kwh":   sum(b.remaining_kwh   for b in online),
        "cycle_count":     max((b.cycle_count if hasattr(b, "cycle_count") else 0)
                               for b in online),
        "max_voltage":     min((b.max_voltage  for b in online if b.max_voltage),
                               default=0.0),
        "max_current":     sum(b.max_current   for b in online if b.max_current),
        "cell_count":      sum(b.cell_count    for b in online),
        "cell_min":        min((b.cell_min for b in online if b.cell_min), default=0.0),
        "cell_max":        max((b.cell_max for b in online if b.cell_max), default=0.0),
        "cell_delta":      max((b.cell_delta for b in online if b.cell_delta), default=0.0),
        "alarm_count":     sum(b.alarm_count for b in online),
        "alarms":          list({a for b in online for a in b.alarms}),
        "status_flags":    0,
        "online_count":    len(online),
        "battery_count":   len(batteries),
        # flatten all cell voltages from all packs in order
        "cell_voltages":   [v for b in online for v in (b.cell_voltages or [])],
    }
    return agg


# ---------------------------------------------------------------------------
# Register builder
# ---------------------------------------------------------------------------

def build_registers(batteries: List[BatteryData]) -> List[int]:
    """
    Convert aggregated battery data into a flat list of Modbus holding
    register values starting at address 0.
    """
    regs = [0] * 256   # pre-fill 256 registers with zeros

    agg = aggregate(batteries)
    if not agg:
        return regs

    # Main telemetry block (registers 0–20)
    regs[0]  = _to_int16(agg["current"],         scale=100)
    regs[1]  = _to_uint16(agg["voltage"],         scale=100)
    regs[2]  = _to_uint16(agg["soc"])
    regs[3]  = _to_uint16(agg["soh"])
    regs[4]  = _to_uint16(agg["remaining_ah"],    scale=100)
    regs[5]  = _to_uint16(agg["design_capacity"], scale=100)
    regs[6]  = _to_uint16(agg["full_capacity"],   scale=100)
    regs[7]  = _to_uint16(agg["cycle_count"])
    regs[8]  = _to_uint16(agg["max_voltage"],     scale=100)
    regs[9]  = _to_uint16(agg["max_current"],     scale=100)
    regs[10] = _to_int16(agg["temperature"],      scale=10)
    regs[11] = _to_uint16(agg["alarm_count"])
    regs[12] = _to_uint16(agg["status_flags"])
    regs[13] = _to_int16(agg["power"])
    regs[14] = _to_uint16(agg["remaining_kwh"],   scale=100)
    regs[15] = _to_uint16(agg["cell_count"])
    regs[16] = _to_uint16(agg["cell_min"],        scale=1000)
    regs[17] = _to_uint16(agg["cell_max"],        scale=1000)
    regs[18] = _to_uint16(agg["cell_delta"])
    regs[19] = _to_uint16(agg["online_count"])
    regs[20] = _to_uint16(agg["battery_count"])

    # Per-cell voltages (registers 100–131)
    for i, v in enumerate(agg["cell_voltages"][:MAX_CELLS]):
        regs[100 + i] = _to_uint16(v, scale=1000)

    # Alarm bitmask (register 200)
    regs[200] = _alarm_bitmask(agg["alarms"])

    return regs


# ---------------------------------------------------------------------------
# Virtual Modbus TCP Server
# ---------------------------------------------------------------------------

class VirtualModbusServer:
    """
    Runs a Modbus TCP server in a background thread.

    Solar Assistant (or any Modbus master) connects to this server and
    reads holding registers that reflect the live combined battery state.

    Usage::

        server = VirtualModbusServer(host="0.0.0.0", port=502)
        server.start()
        # ... when new battery data arrives:
        server.update(batteries)
        # ... on shutdown:
        server.stop()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 502):
        self.host = host
        self.port = port
        self._batteries: List[BatteryData] = []
        self._context: Optional[ModbusServerContext] = None
        self._server: Optional[ModbusTcpServer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the Modbus TCP server in a background thread."""
        self._thread = threading.Thread(
            target=self._run,
            name="modbus-server",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=5.0)
        logger.info(
            f"Virtual Modbus server listening on {self.host}:{self.port} "
            f"(Solar Assistant: Pylontech / TCP)"
        )

    def stop(self):
        """Shut down the Modbus TCP server."""
        if self._loop and self._server:
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("Virtual Modbus server stopped")

    def update(self, batteries: List[BatteryData]):
        """Push fresh battery data into the live register map."""
        self._batteries = batteries
        if self._context is not None:
            self._refresh_registers()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_initial_context(self) -> ModbusServerContext:
        """Create an empty Modbus server context (256 holding registers)."""
        block = ModbusSequentialDataBlock(0, [0] * 256)
        device_ctx = ModbusDeviceContext(hr=block)
        return ModbusServerContext(slaves={1: device_ctx}, single=False)

    def _refresh_registers(self):
        """Write the latest aggregated values into the server's register store."""
        try:
            regs = build_registers(self._batteries)
            # Device ID 1, function code 3 (holding registers), start at 0
            self._context[1].setValues(3, 0, regs)
        except Exception as exc:
            logger.error(f"Modbus register refresh error: {exc}")

    def _make_identity(self) -> ModbusDeviceIdentification:
        ident = ModbusDeviceIdentification()
        ident.VendorName         = "EG4 Battery Monitor"
        ident.ProductCode        = "EG4-VBMS"
        ident.VendorUrl          = "https://github.com/nolen007/eg4-battery-monitor"
        ident.ProductName        = "Virtual BMS Gateway"
        ident.ModelName          = "Pylontech Compatible"
        ident.MajorMinorRevision = "1.0"
        return ident

    def _run(self):
        """Entry point for the background thread — runs the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_run())

    async def _async_run(self):
        """Async server lifecycle."""
        self._context = self._build_initial_context()

        self._server = ModbusTcpServer(
            context=self._context,
            framer=FramerType.SOCKET,
            identity=self._make_identity(),
            address=(self.host, self.port),
        )

        # Signal that we're ready before blocking on serve_forever
        self._ready.set()

        async with self._server:
            await self._server.serve_forever()
