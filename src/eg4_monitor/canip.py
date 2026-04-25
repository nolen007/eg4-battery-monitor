"""
CAN over IP (CAN bus messages tunneled over TCP/IP).

Supports connecting to CAN-to-Ethernet bridges/adapters that expose a raw
CAN socket over TCP — for example:
  - Waveshare RS485/CAN-to-ETH adapters (TCP transparent mode)
  - Canable/SLCAN adapters with tcp2can proxy
  - Any device that forwards raw CAN frames over a TCP stream

Protocol details:
  A standard CAN 2.0 frame tunneled over TCP is sent as 13 or 16 bytes:
    Bytes 0-3  : CAN ID (big-endian uint32, bit 31 = extended frame flag)
    Byte  4    : DLC — Data Length Code (0-8)
    Bytes 5-12 : Data payload (DLC bytes valid, rest padding)

  Some bridges add a 3-byte header (length + type); this module supports
  both raw-frame and length-prefixed modes (auto-detected).

BMS CAN IDs used by EG4 / PACE / Pylontech-compatible packs (0x18xx00yy):
  0x18900140 — battery status  (SOC, SOH, voltage, current, temp)
  0x18910140 — cell voltages 1-4
  0x18920140 — cell voltages 5-8
  0x18930140 — cell voltages 9-12
  0x18940140 — cell voltages 13-16
  0x18950140 — alarms / protection flags
  0x18960140 — pack info (capacity, cycles)

The master/inverter polls with request frames; for passive listening the
module can also work in "sniff" mode where it just reads whatever the BMS
broadcasts on its own.
"""

import logging
import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CAN frame constants
# ---------------------------------------------------------------------------

CAN_FRAME_SIZE = 13          # ID(4) + DLC(1) + DATA(8)
CAN_EFF_FLAG   = 0x80000000  # Extended Frame Format flag in CAN ID word
CAN_RTR_FLAG   = 0x40000000  # Remote Transmission Request flag
CAN_ERR_FLAG   = 0x20000000  # Error frame flag
CAN_ID_MASK    = 0x1FFFFFFF  # 29-bit extended ID mask

# ---------------------------------------------------------------------------
# Pylontech / EG4 compatible CAN message IDs (extended, 29-bit)
# The lower byte selects the pack number (0x40 = pack 1, 0x41 = pack 2, …)
# The upper byte selects the message type.
# ---------------------------------------------------------------------------

# Outbound (BMS → inverter)
CAN_ID_STATUS       = 0x18900140   # SOC, SOH, voltage, current, temp
CAN_ID_CELLS_1_4    = 0x18910140   # Cell voltages 1-4
CAN_ID_CELLS_5_8    = 0x18920140   # Cell voltages 5-8
CAN_ID_CELLS_9_12   = 0x18930140   # Cell voltages 9-12
CAN_ID_CELLS_13_16  = 0x18940140   # Cell voltages 13-16
CAN_ID_ALARMS       = 0x18950140   # Alarm / protection status
CAN_ID_PACK_INFO    = 0x18960140   # Pack capacity, cycles, max charge/discharge

# Inbound (inverter → BMS) — request frame
CAN_ID_REQUEST      = 0x18500140   # Poll request from inverter

# Mask for matching pack-independent message type
CAN_TYPE_MASK       = 0xFFFFFF00


# ---------------------------------------------------------------------------
# Alarm bit definitions (CAN_ID_ALARMS byte layout)
# ---------------------------------------------------------------------------

ALARM_BITS = {
    # Byte 0
    0x0001: "Cell Over-Voltage",
    0x0002: "Cell Under-Voltage",
    0x0004: "Pack Over-Voltage",
    0x0008: "Pack Under-Voltage",
    # Byte 1
    0x0010: "Charge Over-Temperature",
    0x0020: "Charge Under-Temperature",
    0x0040: "Discharge Over-Temperature",
    0x0080: "Discharge Under-Temperature",
    # Byte 2
    0x0100: "Charge Over-Current",
    0x0200: "Discharge Over-Current",
    0x0400: "Short Circuit",
    0x0800: "BMS Internal Fault",
    # Byte 3
    0x1000: "Cell Imbalance",
    0x2000: "Low SOC",
    0x4000: "Charge FET Open",
    0x8000: "Discharge FET Open",
}


# ---------------------------------------------------------------------------
# Raw CAN frame helpers
# ---------------------------------------------------------------------------

def pack_can_frame(can_id: int, data: bytes, extended: bool = True) -> bytes:
    """Pack a CAN frame into 13-byte wire format."""
    if extended:
        can_id |= CAN_EFF_FLAG
    dlc = min(len(data), 8)
    payload = data[:dlc].ljust(8, b'\x00')
    return struct.pack('>IB8s', can_id, dlc, payload)


def unpack_can_frame(raw: bytes):
    """
    Unpack a 13-byte CAN frame.

    Returns (can_id, dlc, data_bytes) where can_id has EFF/RTR bits stripped.
    Returns None if the frame is malformed.
    """
    if len(raw) < CAN_FRAME_SIZE:
        return None
    can_id_raw, dlc, data = struct.unpack('>IB8s', raw[:CAN_FRAME_SIZE])
    if dlc > 8:
        return None
    can_id = can_id_raw & CAN_ID_MASK
    return can_id, dlc, data[:dlc]


def build_poll_request(pack_address: int = 0x40) -> bytes:
    """Build the inverter→BMS poll request CAN frame."""
    request_id = (CAN_ID_REQUEST & CAN_TYPE_MASK) | pack_address
    return pack_can_frame(request_id, b'\x00' * 8)


# ---------------------------------------------------------------------------
# CAN over IP connection
# ---------------------------------------------------------------------------

class CANIPConnection:
    """
    Manages a TCP connection to a CAN-over-IP bridge.

    The bridge is expected to forward raw 13-byte CAN frames over the TCP
    stream with no additional framing (transparent TCP mode). If the bridge
    adds a 2-byte length prefix, set ``length_prefixed=True``.
    """

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        length_prefixed: bool = False,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.length_prefixed = length_prefixed
        self._sock: Optional[socket.socket] = None
        self._buf = b''

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open the TCP connection to the CAN bridge."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            self._buf = b''
            logger.info(f"CAN/IP: connected to {self.host}:{self.port}")
            return True
        except OSError as exc:
            logger.error(f"CAN/IP: connection failed to {self.host}:{self.port} — {exc}")
            self._sock = None
            return False

    def disconnect(self):
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        logger.info(f"CAN/IP: disconnected from {self.host}:{self.port}")

    @property
    def connected(self) -> bool:
        return self._sock is not None

    # ------------------------------------------------------------------
    # Frame I/O
    # ------------------------------------------------------------------

    def send_frame(self, can_id: int, data: bytes, extended: bool = True) -> bool:
        """Send a single CAN frame over the TCP stream."""
        if not self.connected:
            return False
        raw = pack_can_frame(can_id, data, extended)
        if self.length_prefixed:
            raw = struct.pack('>H', len(raw)) + raw
        try:
            self._sock.sendall(raw)
            return True
        except OSError as exc:
            logger.error(f"CAN/IP: send error — {exc}")
            self._sock = None
            return False

    def _recv_bytes(self, n: int) -> Optional[bytes]:
        """Read exactly *n* bytes from the socket, buffering as needed."""
        while len(self._buf) < n:
            try:
                chunk = self._sock.recv(256)
            except OSError as exc:
                logger.error(f"CAN/IP: recv error — {exc}")
                self._sock = None
                return None
            if not chunk:
                logger.warning("CAN/IP: connection closed by remote")
                self._sock = None
                return None
            self._buf += chunk

        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def read_frame(self):
        """
        Read the next CAN frame from the stream.

        Returns (can_id, dlc, data) or None on error / timeout.
        """
        if not self.connected:
            return None

        if self.length_prefixed:
            length_bytes = self._recv_bytes(2)
            if length_bytes is None:
                return None
            (frame_len,) = struct.unpack('>H', length_bytes)
            raw = self._recv_bytes(frame_len)
        else:
            raw = self._recv_bytes(CAN_FRAME_SIZE)

        if raw is None:
            return None

        result = unpack_can_frame(raw)
        if result is None:
            logger.warning(f"CAN/IP: malformed frame — {raw.hex()}")
        return result

    def read_frames(self, timeout: float = 1.0) -> List[tuple]:
        """
        Collect all CAN frames arriving within *timeout* seconds.

        Useful for passive sniffing: the caller sends a poll request and
        then collects the burst of response frames.
        """
        frames = []
        if not self.connected:
            return frames

        self._sock.settimeout(timeout)
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            frame = self.read_frame()
            if frame is None:
                break
            frames.append(frame)

        self._sock.settimeout(self.timeout)
        return frames


# ---------------------------------------------------------------------------
# BMS data parser
# ---------------------------------------------------------------------------

class CANBMSParser:
    """
    Parses Pylontech/EG4-compatible CAN messages into BatteryData fields.

    This is a stateful accumulator: call ``process_frame()`` for each
    received frame, then read the ``data`` attribute.
    """

    def __init__(self):
        self._cell_voltages: Dict[int, float] = {}  # index → voltage (V)
        self._alarm_word: int = 0
        self._seen_ids: set = set()

        # Accumulated values (populated as frames arrive)
        self.soc: float = 0.0
        self.soh: float = 100.0
        self.voltage: float = 0.0
        self.current: float = 0.0
        self.temperature: float = 0.0
        self.remaining_ah: float = 0.0
        self.design_capacity: float = 0.0
        self.full_capacity: float = 0.0
        self.max_charge_voltage: float = 0.0
        self.max_charge_current: float = 0.0
        self.max_discharge_current: float = 0.0
        self.cycle_count: int = 0
        self.alarms: List[str] = []

    @property
    def cell_voltages(self) -> List[float]:
        """Ordered list of cell voltages for all cells seen so far."""
        if not self._cell_voltages:
            return []
        max_idx = max(self._cell_voltages.keys())
        return [self._cell_voltages.get(i, 0.0) for i in range(max_idx + 1)]

    def process_frame(self, can_id: int, dlc: int, data: bytes) -> bool:
        """
        Decode one CAN frame and update internal state.

        Returns True if the frame was recognised, False otherwise.
        """
        # Normalise to pack-1 ID for matching (mask out pack address byte)
        msg_type = can_id & CAN_TYPE_MASK

        if msg_type == (CAN_ID_STATUS & CAN_TYPE_MASK):
            self._parse_status(data, dlc)
        elif msg_type == (CAN_ID_CELLS_1_4 & CAN_TYPE_MASK):
            self._parse_cells(data, dlc, offset=0)
        elif msg_type == (CAN_ID_CELLS_5_8 & CAN_TYPE_MASK):
            self._parse_cells(data, dlc, offset=4)
        elif msg_type == (CAN_ID_CELLS_9_12 & CAN_TYPE_MASK):
            self._parse_cells(data, dlc, offset=8)
        elif msg_type == (CAN_ID_CELLS_13_16 & CAN_TYPE_MASK):
            self._parse_cells(data, dlc, offset=12)
        elif msg_type == (CAN_ID_ALARMS & CAN_TYPE_MASK):
            self._parse_alarms(data, dlc)
        elif msg_type == (CAN_ID_PACK_INFO & CAN_TYPE_MASK):
            self._parse_pack_info(data, dlc)
        else:
            return False

        self._seen_ids.add(msg_type)
        return True

    # ------------------------------------------------------------------
    # Individual message parsers
    # ------------------------------------------------------------------

    def _parse_status(self, data: bytes, dlc: int):
        """
        CAN ID 0x1890xx40 — Battery status frame.

        Byte layout (Pylontech/EG4 PYLON protocol):
          0-1 : Voltage        (uint16, 0.1 V/LSB)
          2-3 : Current        (int16,  0.1 A/LSB, positive = charging)
          4-5 : Temperature    (uint16, 0.1 °C/LSB, offset -2731 = -273.1°C base)
          6   : SOC            (uint8,  1 %/LSB)
          7   : SOH            (uint8,  1 %/LSB)
        """
        if dlc < 8 or len(data) < 8:
            return
        voltage_raw, current_raw, temp_raw = struct.unpack('>HhH', data[0:6])
        self.voltage      = voltage_raw * 0.1
        self.current      = current_raw * 0.1
        # Temperature: raw value is in 0.1 K, offset by 2731 (= 273.1 K = 0 °C)
        self.temperature  = (temp_raw - 2731) * 0.1
        self.soc          = data[6]
        self.soh          = data[7]

    def _parse_cells(self, data: bytes, dlc: int, offset: int):
        """
        CAN IDs 0x1891–0x1894xx40 — Cell voltage frames.

        Each frame carries 4 cell voltages:
          Bytes 0-1 : Cell N+0  (uint16, 1 mV/LSB)
          Bytes 2-3 : Cell N+1
          Bytes 4-5 : Cell N+2
          Bytes 6-7 : Cell N+3
        """
        if dlc < 8 or len(data) < 8:
            return
        for i in range(4):
            mv = struct.unpack('>H', data[i*2:i*2+2])[0]
            if 1000 < mv < 5000:   # sanity: 1.0 V – 5.0 V
                self._cell_voltages[offset + i] = mv / 1000.0

    def _parse_alarms(self, data: bytes, dlc: int):
        """
        CAN ID 0x1895xx40 — Alarm / protection flags.

        Bytes 0-1: alarm bitmask (see ALARM_BITS)
        Bytes 2-3: warning bitmask (same layout, lower severity)
        """
        if dlc < 4 or len(data) < 4:
            return
        alarm_word = struct.unpack('>H', data[0:2])[0]
        self._alarm_word = alarm_word
        self.alarms = [
            label for bit, label in ALARM_BITS.items()
            if alarm_word & bit
        ]

    def _parse_pack_info(self, data: bytes, dlc: int):
        """
        CAN ID 0x1896xx40 — Pack information frame.

        Byte layout:
          0-1 : Max charge voltage      (uint16, 0.1 V/LSB)
          2-3 : Max charge current      (uint16, 0.1 A/LSB)
          4-5 : Max discharge current   (uint16, 0.1 A/LSB)
          6-7 : Design capacity         (uint16, 0.1 Ah/LSB)
        """
        if dlc < 8 or len(data) < 8:
            return
        v_max, i_charge, i_discharge, capacity = struct.unpack('>HHHH', data[0:8])
        self.max_charge_voltage    = v_max      * 0.1
        self.max_charge_current    = i_charge   * 0.1
        self.max_discharge_current = i_discharge * 0.1
        self.design_capacity       = capacity   * 0.1
        self.full_capacity         = self.design_capacity


# ---------------------------------------------------------------------------
# High-level CAN/IP reader (integrates with the existing monitor)
# ---------------------------------------------------------------------------

class CANIPReader:
    """
    High-level reader that connects to a CAN-over-IP bridge, sends a poll
    request, and returns a populated BatteryData-compatible dict.

    Usage::

        reader = CANIPReader(battery_config)
        reader.connect()
        data   = reader.poll()   # returns BatteryData
        reader.disconnect()
    """

    # How long to collect response frames after sending the poll request
    RESPONSE_WINDOW = 0.5   # seconds

    def __init__(self, battery_config):
        from eg4_monitor.battery import BatteryData, slugify
        self._BatteryData = BatteryData
        self._slugify = slugify

        self.config  = battery_config
        self.name    = battery_config.name
        self.battery_id = slugify(battery_config.name)

        # Optional config keys (with defaults)
        self._pack_address = getattr(battery_config, 'can_pack_address', 0x40)
        self._length_prefixed = getattr(battery_config, 'can_length_prefixed', False)
        self._sniff_only = getattr(battery_config, 'can_sniff_only', False)

        self._conn   = CANIPConnection(
            host=battery_config.ip,
            port=battery_config.port,
            length_prefixed=self._length_prefixed,
        )
        self._parser = CANBMSParser()

    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._conn.connected

    def connect(self) -> bool:
        return self._conn.connect()

    def disconnect(self):
        self._conn.disconnect()

    # ------------------------------------------------------------------

    def poll(self):
        """
        Send a CAN poll request (unless sniff_only) and parse the response.

        Returns a BatteryData instance.
        """
        from datetime import datetime

        data = self._BatteryData(
            name=self.name,
            battery_id=self.battery_id,
            timestamp=datetime.now().isoformat(),
        )

        if not self.connected:
            if not self.connect():
                return data

        # Reset parser state for fresh accumulation
        self._parser = CANBMSParser()

        # Send poll request (unless we're in passive sniff mode)
        if not self._sniff_only:
            ok = self._conn.send_frame(
                can_id=CAN_ID_REQUEST | self._pack_address,
                data=b'\x00' * 8,
            )
            if not ok:
                logger.warning(f"CAN/IP: failed to send poll request for {self.name}")
                return data

        # Collect response frames
        frames = self._conn.read_frames(timeout=self.RESPONSE_WINDOW)
        if not frames:
            logger.warning(f"CAN/IP: no frames received from {self.name}")
            return data

        recognised = 0
        for (can_id, dlc, payload) in frames:
            if self._parser.process_frame(can_id, dlc, payload):
                recognised += 1

        logger.debug(
            f"CAN/IP {self.name}: received {len(frames)} frames, "
            f"{recognised} recognised"
        )

        if recognised == 0:
            logger.warning(f"CAN/IP: no known BMS frames from {self.name}")
            return data

        # Map parser state → BatteryData
        p = self._parser
        cvs = p.cell_voltages

        data.online        = True
        data.soc           = p.soc
        data.soh           = p.soh
        data.voltage       = p.voltage
        data.current       = p.current
        data.power         = round(p.voltage * p.current, 1)
        data.temperature   = p.temperature

        data.design_capacity  = p.design_capacity
        data.full_capacity    = p.full_capacity
        # Estimate remaining Ah from SOC × full capacity if not provided
        if p.remaining_ah:
            data.remaining_ah = p.remaining_ah
        elif p.full_capacity:
            data.remaining_ah = round(p.full_capacity * p.soc / 100.0, 1)
        data.remaining_kwh = round((data.remaining_ah * data.voltage) / 1000.0, 2) if data.voltage else 0.0

        data.max_voltage   = p.max_charge_voltage
        data.max_current   = p.max_charge_current

        if cvs:
            data.cell_voltages = [round(v, 3) for v in cvs]
            data.cell_count    = len(cvs)
            data.cell_min      = round(min(cvs), 3)
            data.cell_max      = round(max(cvs), 3)
            data.cell_delta    = round((data.cell_max - data.cell_min) * 1000, 1)

        data.alarms      = p.alarms
        data.alarm_count = len(p.alarms)

        logger.debug(
            f"CAN/IP polled {self.name}: "
            f"SOC={data.soc}% V={data.voltage}V I={data.current}A"
        )
        return data
