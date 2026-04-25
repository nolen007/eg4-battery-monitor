#!/usr/bin/env python3
"""
pylontech_relay.py — Pylontech RS485 relay for Solar Assistant.

Runs on the Solar Assistant Pi. Shares ttyUSB0 with Solar Assistant:
  - Solar Assistant sends a Pylontech poll request to ttyUSB0
  - This service intercepts the request
  - Fetches live combined battery data from the eg4-monitor Modbus server
  - Responds with a valid Pylontech RS485 frame
  - Solar Assistant reads it as a real Pylontech battery

Install:
    pip3 install pyserial requests

Usage:
    python3 pylontech_relay.py --serial /dev/ttyUSB0 --host 192.168.x.x --port 5020

Run as service:
    sudo cp pylontech-relay.service /etc/systemd/system/
    sudo systemctl enable --now pylontech-relay
"""

import argparse
import logging
import serial
import socket
import struct
import time
from typing import Optional, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pylontech RS485 protocol
# ---------------------------------------------------------------------------

SOI = 0x7E
EOI = 0x0D

CMD_ANALOG   = 0x42   # voltage, current, SOC, temp, capacity
CMD_ALARM    = 0x44   # alarm flags
CMD_SYSINFO  = 0x47   # system info / capacity
CMD_PROTOVER = 0x4F   # protocol version


def _lchksum(length: int) -> int:
    s = ((length >> 8) & 0xF) + ((length >> 4) & 0xF) + (length & 0xF)
    s = ~s & 0xF
    return (s + 1) & 0xF


def _chksum(data: bytes) -> int:
    s = sum(data) & 0xFFFF
    s = ~s & 0xFFFF
    return (s + 1) & 0xFFFF


def _encode_length(n: int) -> int:
    lchk = _lchksum(n)
    return (lchk << 12) | (n & 0xFFF)


def build_response(adr: int, cid2: int, data: bytes) -> bytes:
    """Build a complete Pylontech RS485 response frame."""
    ver     = 0x20
    rtn     = 0x46
    rtnflag = 0x00
    lenid   = _encode_length(len(data))
    payload = bytes([ver, adr, rtn, rtnflag,
                     (lenid >> 8) & 0xFF, lenid & 0xFF]) + data
    chk = _chksum(payload)
    return (bytes([SOI]) + payload +
            bytes([(chk >> 8) & 0xFF, chk & 0xFF, EOI]))


def parse_request(raw: bytes) -> Optional[dict]:
    """Parse a Pylontech request frame. Returns dict or None if invalid."""
    if len(raw) < 7 or raw[0] != SOI:
        return None
    return {
        "adr":  raw[2],
        "cid1": raw[3],
        "cid2": raw[4],
    }


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _temp(c: float) -> int:
    """Pylontech temperature: (°C + 273.15) × 10."""
    return max(0, round((c + 273.15) * 10))


def analog_response(adr: int, b: dict) -> bytes:
    """CMD 0x42 — voltage, current, SOC, temperature, capacity."""
    cells = b["cell_voltages"]
    ncells = min(len(cells), 16)

    d = bytearray()
    d.append(1)          # number of packs (1 combined)
    d.append(ncells)     # cell count

    for i in range(ncells):
        mv = round(cells[i] * 1000) if i < len(cells) else 3000
        d += struct.pack(">H", mv)

    d.append(1)          # number of temp sensors
    d += struct.pack(">H", _temp(b["temperature"]))

    # Current: 10 mA/LSB signed
    d += struct.pack(">h", max(-32768, min(32767, round(b["current"] * 100))))

    # Voltage: 1 mV/LSB
    d += struct.pack(">H", min(65535, round(b["voltage"] * 1000)))

    # Remaining capacity: 10 mAh/LSB
    d += struct.pack(">H", min(65535, round(b["remaining_ah"] * 100)))

    d.append(0)          # user defined

    # Full capacity: 10 mAh/LSB
    d += struct.pack(">H", min(65535, round(b["full_capacity"] * 100)))

    # Cycle count
    d += struct.pack(">H", min(65535, b["cycle_count"]))

    # SOC: 0.1%/LSB
    d += struct.pack(">H", min(1000, round(b["soc"] * 10)))

    return build_response(adr, CMD_ANALOG, bytes(d))


def alarm_response(adr: int, b: dict) -> bytes:
    """CMD 0x44 — alarm flags."""
    ncells = min(b["cell_count"], 16)
    mask   = b["alarm_bitmask"]

    d = bytearray()
    d.append(1)       # num packs
    d.append(ncells)

    # Cell voltage alarms (0=ok, 1=under, 2=over)
    for _ in range(ncells):
        if mask & 0x0004:
            d.append(0x02)   # cell over voltage
        elif mask & 0x0008:
            d.append(0x01)   # cell under voltage
        else:
            d.append(0x00)

    # Temp alarms
    d.append(1)
    if mask & 0x0010:
        d.append(0x02)   # over temp
    elif mask & 0x0020:
        d.append(0x01)   # under temp
    else:
        d.append(0x00)

    # Charge current alarm
    d.append(0x02 if mask & 0x0040 else 0x00)
    # Pack voltage alarm
    d.append(0x02 if mask & 0x0001 else (0x01 if mask & 0x0002 else 0x00))
    # Discharge alarm
    d.append(0x02 if mask & 0x0040 else 0x00)
    # Status byte (bit0=charging, bit1=discharging, bit2=current limit, bit3=shutdown)
    status = 0
    if b["current"] > 0:   status |= 0x01
    if b["current"] < 0:   status |= 0x02
    d.append(status)

    return build_response(adr, CMD_ALARM, bytes(d))


def sysinfo_response(adr: int, b: dict) -> bytes:
    """CMD 0x47 — system parameters (capacity, SOH, etc.)."""
    d = bytearray()
    d.append(1)   # num packs

    # Cell high/low voltage limits (mV)
    d += struct.pack(">H", 3650)   # cell over voltage
    d += struct.pack(">H", 3650)   # cell over voltage recover
    d += struct.pack(">H", 3600)   # cell high voltage alarm
    d += struct.pack(">H", 2800)   # cell low voltage alarm
    d += struct.pack(">H", 2750)   # cell under voltage recover
    d += struct.pack(">H", 2750)   # cell under voltage

    # Temp limits (0.1°C + 2731)
    d += struct.pack(">H", _temp(45))   # charge over temp
    d += struct.pack(">H", _temp(40))   # charge over temp recover
    d += struct.pack(">H", _temp(0))    # charge under temp recover
    d += struct.pack(">H", _temp(-5))   # charge under temp

    # Design capacity (10 mAh/LSB)
    d += struct.pack(">H", min(65535, round(b["design_capacity"] * 100)))

    # Design voltage (1 mV/LSB)
    d += struct.pack(">H", min(65535, round(b["max_voltage"] * 1000)))

    # AH10 rate capacity
    d += struct.pack(">H", min(65535, round(b["design_capacity"] * 100)))

    # Max charge current (10 mA/LSB)
    d += struct.pack(">H", min(65535, round(b["max_current"] * 100)))

    # Max discharge current (10 mA/LSB)
    d += struct.pack(">H", min(65535, round(b["max_current"] * 100)))

    # SOH
    d.append(min(100, round(b["soh"])))

    # Cycle count
    d += struct.pack(">H", min(65535, b["cycle_count"]))

    return build_response(adr, CMD_SYSINFO, bytes(d))


def protover_response(adr: int) -> bytes:
    """CMD 0x4F — protocol version."""
    return build_response(adr, CMD_PROTOVER, bytes([0x20, 0x00]))


# ---------------------------------------------------------------------------
# Modbus TCP reader
# ---------------------------------------------------------------------------

class ModbusReader:
    """Minimal Modbus TCP client that reads from the eg4-monitor."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._tid = 0

    def connect(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((self.host, self.port))
            self._sock = s
            logger.info(f"Connected to eg4-monitor at {self.host}:{self.port}")
            return True
        except OSError as e:
            logger.warning(f"eg4-monitor connect failed: {e}")
            self._sock = None
            return False

    def _recv(self, n: int) -> Optional[bytes]:
        buf = b""
        while len(buf) < n:
            try:
                chunk = self._sock.recv(n - len(buf))
                if not chunk:
                    return None
                buf += chunk
            except OSError:
                return None
        return buf

    def read_registers(self, start: int, count: int) -> Optional[List[int]]:
        if not self._sock:
            if not self.connect():
                return None
        self._tid = (self._tid + 1) & 0xFFFF
        req = struct.pack(">HHHBBHH",
            self._tid, 0, 6, 1, 3, start, count)
        try:
            self._sock.sendall(req)
            hdr = self._recv(9)
            if not hdr or len(hdr) < 9:
                self._sock = None
                return None
            byte_count = hdr[8]
            data = self._recv(byte_count)
            if not data:
                self._sock = None
                return None
            return [struct.unpack(">H", data[i:i+2])[0]
                    for i in range(0, byte_count, 2)]
        except OSError as e:
            logger.warning(f"Modbus read error: {e}")
            self._sock = None
            return None


def _int16(raw: int) -> int:
    return raw if raw < 32768 else raw - 65536


def fetch_battery(reader: ModbusReader) -> Optional[dict]:
    """Read all registers and return a battery dict."""
    # Read main registers 0-20
    main = reader.read_registers(0, 21)
    if not main or len(main) < 21:
        return None

    # Read cell voltages 100-131
    cells_raw = reader.read_registers(100, 32) or []

    # Read alarm bitmask at 200
    alarm_raw = reader.read_registers(200, 1) or [0]

    cell_count = main[15]
    cell_voltages = [cells_raw[i] / 1000.0
                     for i in range(min(cell_count, len(cells_raw)))
                     if cells_raw[i] > 0]

    return {
        "current":         _int16(main[0])  / 100.0,
        "voltage":         main[1]           / 100.0,
        "soc":             main[2],
        "soh":             main[3],
        "remaining_ah":    main[4]           / 100.0,
        "design_capacity": main[5]           / 100.0,
        "full_capacity":   main[6]           / 100.0,
        "cycle_count":     main[7],
        "max_voltage":     main[8]           / 100.0,
        "max_current":     main[9]           / 100.0,
        "temperature":     _int16(main[10])  / 10.0,
        "alarm_count":     main[11],
        "power":           _int16(main[13]),
        "remaining_kwh":   main[14]          / 100.0,
        "cell_count":      cell_count,
        "cell_min":        main[16]          / 1000.0,
        "cell_max":        main[17]          / 1000.0,
        "cell_delta":      main[18],
        "online_count":    main[19],
        "battery_count":   main[20],
        "alarm_bitmask":   alarm_raw[0] if alarm_raw else 0,
        "cell_voltages":   cell_voltages,
    }


# ---------------------------------------------------------------------------
# Main relay loop
# ---------------------------------------------------------------------------

def run_relay(serial_port: str, host: str, port: int, baud: int = 9600):
    reader = ModbusReader(host, port)

    # Cache battery data so we can respond even if Modbus is briefly unavailable
    cached: Optional[dict] = None
    last_fetch = 0.0
    CACHE_TTL = 10.0   # seconds

    logger.info(f"Opening {serial_port} at {baud} baud")
    ser = serial.Serial(
        port=serial_port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1,
    )

    logger.info("Pylontech relay running — waiting for Solar Assistant polls...")
    buf = bytearray()

    while True:
        # Refresh battery data cache
        now = time.monotonic()
        if now - last_fetch > CACHE_TTL:
            data = fetch_battery(reader)
            if data:
                cached = data
                last_fetch = now
                logger.debug(
                    f"Cache refreshed — SOC={cached['soc']}% "
                    f"V={cached['voltage']}V I={cached['current']}A"
                )
            elif not cached:
                time.sleep(1.0)
                continue

        # Read incoming bytes from Solar Assistant
        chunk = ser.read(64)
        if chunk:
            buf.extend(chunk)

        # Look for a complete Pylontech frame (SOI...EOI)
        if SOI in buf:
            start = buf.index(SOI)
            buf = buf[start:]   # trim leading garbage
            if EOI in buf:
                end = buf.index(EOI) + 1
                frame = bytes(buf[:end])
                buf = buf[end:]

                req = parse_request(frame)
                if req:
                    adr  = req["adr"]
                    cid2 = req["cid2"]
                    logger.info(
                        f"Poll from SA: adr=0x{adr:02X} cmd=0x{cid2:02X}"
                    )

                    if cid2 == CMD_ANALOG:
                        response = analog_response(adr, cached)
                    elif cid2 == CMD_ALARM:
                        response = alarm_response(adr, cached)
                    elif cid2 == CMD_SYSINFO:
                        response = sysinfo_response(adr, cached)
                    elif cid2 == CMD_PROTOVER:
                        response = protover_response(adr)
                    else:
                        logger.debug(f"Unknown command 0x{cid2:02X}, ignoring")
                        continue

                    # Small delay before responding (RS485 turnaround)
                    time.sleep(0.01)
                    ser.write(response)
                    ser.flush()
                    logger.debug(f"Responded with {len(response)} bytes")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pylontech RS485 relay for Solar Assistant")
    parser.add_argument("--serial", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--host",   required=True,          help="eg4-monitor IP address")
    parser.add_argument("--port",   type=int, default=5020, help="eg4-monitor Modbus port (default: 5020)")
    parser.add_argument("--baud",   type=int, default=9600, help="Serial baud rate (default: 9600)")
    parser.add_argument("--debug",  action="store_true",    help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    run_relay(args.serial, args.host, args.port, args.baud)
