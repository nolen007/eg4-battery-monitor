"""
Unit tests for CAN over IP module.
"""

import struct
import pytest

from eg4_monitor.canip import (
    CAN_EFF_FLAG,
    CAN_ID_MASK,
    CAN_ID_STATUS,
    CAN_ID_CELLS_1_4,
    CAN_ID_CELLS_5_8,
    CAN_ID_CELLS_9_12,
    CAN_ID_CELLS_13_16,
    CAN_ID_ALARMS,
    CAN_ID_PACK_INFO,
    pack_can_frame,
    unpack_can_frame,
    CANBMSParser,
)


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------

class TestFrameHelpers:

    def test_pack_unpack_roundtrip(self):
        """pack_can_frame → unpack_can_frame should be lossless."""
        can_id = 0x18900140
        data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
        raw = pack_can_frame(can_id, data, extended=True)
        assert len(raw) == 13

        result = unpack_can_frame(raw)
        assert result is not None
        out_id, dlc, out_data = result
        assert out_id == can_id & CAN_ID_MASK
        assert dlc == 8
        assert out_data == data

    def test_pack_short_payload(self):
        """DLC should reflect actual payload length."""
        raw = pack_can_frame(0x123, b'\xAB\xCD', extended=False)
        can_id, dlc, payload = unpack_can_frame(raw)
        assert dlc == 2
        assert payload == b'\xAB\xCD'

    def test_unpack_malformed_returns_none(self):
        """Frames shorter than 13 bytes should return None."""
        assert unpack_can_frame(b'\x00' * 5) is None

    def test_extended_flag_stripped(self):
        """EFF bit should be stripped from the returned can_id."""
        raw = pack_can_frame(0x18900140, b'\x00' * 8, extended=True)
        can_id, _, _ = unpack_can_frame(raw)
        assert can_id == 0x18900140  # EFF flag already in the ID value but masked
        assert not (can_id & CAN_EFF_FLAG)


# ---------------------------------------------------------------------------
# BMS parser
# ---------------------------------------------------------------------------

def _make_status_frame(voltage_raw, current_raw, temp_raw, soc, soh):
    """Build a raw status data payload."""
    return struct.pack('>HhH', voltage_raw, current_raw, temp_raw) + bytes([soc, soh])


def _make_cell_frame(mv_list):
    """Build a 4-cell voltage payload."""
    assert len(mv_list) == 4
    return struct.pack('>HHHH', *mv_list)


def _make_alarm_frame(alarm_word, warning_word=0):
    return struct.pack('>HH', alarm_word, warning_word) + b'\x00\x00'


def _make_pack_info_frame(v_max, i_charge, i_discharge, capacity):
    return struct.pack('>HHHH', v_max, i_charge, i_discharge, capacity)


class TestCANBMSParser:

    def test_status_frame(self):
        parser = CANBMSParser()
        # 520 * 0.1 = 52.0 V, 15 * 0.1 = 1.5 A (charging),
        # 2981 - 2731 = 250 * 0.1 = 25.0 °C, SOC=85%, SOH=98%
        data = _make_status_frame(520, 15, 2981, 85, 98)
        ok = parser.process_frame(CAN_ID_STATUS & CAN_ID_MASK, 8, data)
        assert ok
        assert parser.voltage    == pytest.approx(52.0)
        assert parser.current    == pytest.approx(1.5)
        assert parser.temperature == pytest.approx(25.0)
        assert parser.soc == 85
        assert parser.soh == 98

    def test_status_negative_current(self):
        """Discharging current should be negative."""
        parser = CANBMSParser()
        data = _make_status_frame(520, -50, 2981, 60, 100)
        parser.process_frame(CAN_ID_STATUS & CAN_ID_MASK, 8, data)
        assert parser.current == pytest.approx(-5.0)

    def test_cell_voltages_1_4(self):
        parser = CANBMSParser()
        data = _make_cell_frame([3200, 3210, 3190, 3205])
        ok = parser.process_frame(CAN_ID_CELLS_1_4 & CAN_ID_MASK, 8, data)
        assert ok
        cvs = parser.cell_voltages
        assert len(cvs) == 4
        assert cvs[0] == pytest.approx(3.200)
        assert cvs[2] == pytest.approx(3.190)

    def test_cell_voltages_all_groups(self):
        parser = CANBMSParser()
        groups = [
            (CAN_ID_CELLS_1_4,   [3200, 3210, 3190, 3205]),
            (CAN_ID_CELLS_5_8,   [3215, 3200, 3195, 3210]),
            (CAN_ID_CELLS_9_12,  [3205, 3210, 3200, 3215]),
            (CAN_ID_CELLS_13_16, [3200, 3195, 3205, 3210]),
        ]
        for can_id, mv_list in groups:
            parser.process_frame(can_id & CAN_ID_MASK, 8, _make_cell_frame(mv_list))

        cvs = parser.cell_voltages
        assert len(cvs) == 16
        assert cvs[0]  == pytest.approx(3.200)
        assert cvs[15] == pytest.approx(3.210)

    def test_out_of_range_cell_voltage_ignored(self):
        """Voltages outside 1 V – 5 V should be silently dropped."""
        parser = CANBMSParser()
        data = _make_cell_frame([3200, 500, 3190, 6000])  # 500 mV and 6000 mV invalid
        parser.process_frame(CAN_ID_CELLS_1_4 & CAN_ID_MASK, 8, data)
        cvs = parser.cell_voltages
        # Cells at index 1 and 3 should be missing / zero
        # Only indices 0 and 2 were valid; 1 and 3 were dropped entirely.
        # cell_voltages fills gaps with 0.0 up to the highest seen index (2).
        assert len(cvs) == 3   # indices 0, 1, 2 — index 3 never stored
        assert cvs[0] == pytest.approx(3.200)
        assert cvs[1] == 0.0   # gap-filled
        assert cvs[2] == pytest.approx(3.190)

    def test_alarm_frame_no_alarms(self):
        parser = CANBMSParser()
        data = _make_alarm_frame(0x0000)
        ok = parser.process_frame(CAN_ID_ALARMS & CAN_ID_MASK, 8, data)
        assert ok
        assert parser.alarms == []

    def test_alarm_frame_with_alarms(self):
        parser = CANBMSParser()
        # Bit 0x0001 = Cell Over-Voltage, Bit 0x2000 = Low SOC
        data = _make_alarm_frame(0x2001)
        parser.process_frame(CAN_ID_ALARMS & CAN_ID_MASK, 8, data)
        assert "Cell Over-Voltage" in parser.alarms
        assert "Low SOC" in parser.alarms

    def test_pack_info_frame(self):
        parser = CANBMSParser()
        # 576 * 0.1 = 57.6 V max, 1500 * 0.1 = 150 A, 1500 A discharge, 2800 * 0.1 = 280 Ah
        data = _make_pack_info_frame(576, 1500, 1500, 2800)
        ok = parser.process_frame(CAN_ID_PACK_INFO & CAN_ID_MASK, 8, data)
        assert ok
        assert parser.max_charge_voltage    == pytest.approx(57.6)
        assert parser.max_charge_current    == pytest.approx(150.0)
        assert parser.max_discharge_current == pytest.approx(150.0)
        assert parser.design_capacity       == pytest.approx(280.0)

    def test_unknown_frame_returns_false(self):
        parser = CANBMSParser()
        ok = parser.process_frame(0x00000001, 8, b'\x00' * 8)
        assert not ok

    def test_multi_pack_address_normalisation(self):
        """Frames with pack address 0x41 (pack 2) should be parsed the same as pack 1."""
        parser = CANBMSParser()
        # Pack 2 status frame: CAN_ID_STATUS with 0x41 instead of 0x40
        can_id_pack2 = (CAN_ID_STATUS & 0xFFFFFF00) | 0x41
        data = _make_status_frame(520, 0, 2981, 90, 100)
        ok = parser.process_frame(can_id_pack2 & CAN_ID_MASK, 8, data)
        assert ok
        assert parser.soc == 90
