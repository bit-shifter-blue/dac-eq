"""Tanchjim DSP device handler (Fission, Bunny, One DSP)

Based on official Tanchjim Android app protocol (DSPCommand.java)
Source: Decompiled Tanchjim Android APK
Date: 2026-02-11
"""

import hid
import time
from typing import Optional, List
from ..base import (
    DeviceHandler,
    PEQProfile,
    FilterDefinition,
    DeviceCapabilities,
    DeviceNotConnectedError,
)


class TanchjimHandler(DeviceHandler):
    """Handler for Tanchjim DSP devices (Fission, Bunny, One DSP)

    Protocol: USB HID with single EQ buffer (no hardware slots/presets)
    """

    # USB identification
    VENDOR_ID = 0x31B2
    REPORT_ID = 0x4B

    # Protocol commands (from DSPCommand.java)
    COMMAND_READ = 0x52
    COMMAND_WRITE = 0x57
    COMMAND_COMMIT = 0x53

    # Field IDs (from DSPCommand.java)
    FIELD_PREGAIN = 0x65  # CMD_GET_DIGITAL_ADC / cmdADCWriteHeader
    FIELD_FILTER_BASE = 0x26  # commandFreqAndGain1 / modeDataInit[0]

    # Filter type encoding (from DSPCommand.java decodeEQCommand)
    FILTER_TYPE_MAP = {"PK": 0x00, "LSQ": 0x03, "HSQ": 0x04}
    FILTER_TYPE_REVERSE = {0x00: "PK", 0x03: "LSQ", 0x04: "HSQ"}

    # Timing constants
    WRITE_DELAY = 0.02  # 20ms between write commands
    COMMIT_DELAY = 1.0  # 1s after commit for flash write
    READ_TIMEOUT_MS = 1000

    def __init__(self):
        super().__init__()
        self.hid_device: Optional[hid.device] = None

    @property
    def name(self) -> str:
        return "Tanchjim"

    @property
    def vendor_id(self) -> int:
        return self.VENDOR_ID

    @property
    def product_ids(self) -> Optional[List[int]]:
        return None  # Accept any product from this vendor

    @property
    def capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(
            max_filters=5,
            gain_range=(-20.0, 20.0),
            pregain_range=(-12.0, 12.0),
            supported_filter_types={'PK', 'LSQ', 'HSQ'},
            freq_range=(20, 20000),
            q_range=(0.1, 10.0),
            supports_read=True,
            supports_write=True,
        )

    def matches_device(self, device_dict: dict) -> bool:
        """Check if this handler matches the device"""
        if device_dict['vendor_id'] != self.VENDOR_ID:
            return False

        # Match by product name keywords
        product_name = device_dict.get('product_string', '').upper()
        return any(keyword in product_name for keyword in ['FISSION', 'TANCHJIM', 'BUNNY', 'ONE'])

    def connect(self, device_dict: dict) -> None:
        """Connect to the device"""
        self.hid_device = hid.device()
        self.hid_device.open_path(device_dict['path'])
        self.hid_device.set_nonblocking(False)

        if self.debug:
            product_name = device_dict.get('product_string', 'Unknown')
            print(f"[DEBUG] Connected to {product_name}")

    def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    # ========================================================================
    # Low-level HID communication
    # ========================================================================

    def _send_and_receive(self, packet: bytes, timeout_ms: int = READ_TIMEOUT_MS) -> Optional[bytes]:
        """Send HID packet and receive response (for READ commands)"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        self.hid_device.write([self.REPORT_ID] + list(packet))
        resp = self.hid_device.read(64, timeout_ms)

        if self.debug and resp:
            print(f"  → {' '.join(f'{b:02X}' for b in packet[:11])}")
            print(f"  ← {' '.join(f'{b:02X}' for b in resp[:11])}")

        return bytes(resp) if resp else None

    def _send_command(self, packet: bytes) -> None:
        """Send HID packet without response (for WRITE/COMMIT commands)"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        self.hid_device.write([self.REPORT_ID] + list(packet))
        time.sleep(self.WRITE_DELAY)

        if self.debug:
            print(f"  → {' '.join(f'{b:02X}' for b in packet[:11])}")

    # ========================================================================
    # Packet builders (from DSPCommand.java)
    # ========================================================================

    def _build_read_packet(self, field_id: int) -> bytes:
        """Build READ packet: [FieldID, 0, 0, 0, 0x52, 0, 0, 0, 0]"""
        return bytes([field_id, 0x00, 0x00, 0x00, self.COMMAND_READ, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def _build_write_gain_freq(self, field_id: int, freq: int, gain: float) -> bytes:
        """Build WRITE packet for filter gain/frequency

        Encoding (from getTypeCQGain):
        - Gain: signed 16-bit, ×10 scaling, little-endian
        - Freq: unsigned 16-bit, little-endian
        """
        # Gain encoding: multiply by 10, handle negative with two's complement
        gain_raw = int(gain * 10)
        if gain_raw < 0:
            gain_raw += 0x10000

        # Frequency (no 2x compensation for Fission per official code)
        freq_raw = int(freq)

        return bytes([
            field_id, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00,
            gain_raw & 0xFF,
            (gain_raw >> 8) & 0xFF,
            freq_raw & 0xFF,
            (freq_raw >> 8) & 0xFF,
            0x00
        ])

    def _build_write_q(self, field_id: int, q: float, filter_type: str) -> bytes:
        """Build WRITE packet for filter Q factor and type

        Encoding (from getTypeCQGain):
        - Q: unsigned 16-bit, ×1000 scaling, little-endian
        - Type: single byte (0x00=PK, 0x03=LSQ, 0x04=HSQ)
        """
        q_raw = int(q * 1000)
        type_byte = self.FILTER_TYPE_MAP.get(filter_type, 0x00)

        return bytes([
            field_id, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00,
            q_raw & 0xFF,
            (q_raw >> 8) & 0xFF,
            type_byte,
            0x00,
            0x00
        ])

    def _build_write_pregain(self, value: float) -> bytes:
        """Build WRITE packet for pregain

        Encoding (from saveADCCommand):
        - Signed 8-bit, ×2 scaling
        - If negative: (value * 2) + 256
        - If positive: value * 2
        """
        val = int(round(value * 2))
        if val < 0:
            val = (val + 256) & 0xFF

        return bytes([
            self.FIELD_PREGAIN, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00,
            val, 0x00, 0x00, 0x00, 0x00
        ])

    def _build_commit(self) -> bytes:
        """Build COMMIT packet (CMD_SAVE_REG)"""
        return bytes([0x00, 0x00, 0x00, 0x00, self.COMMAND_COMMIT, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    # ========================================================================
    # Response decoders (from DSPCommand.java decodeEQCommand)
    # ========================================================================

    def _decode_gain_freq(self, data: bytes) -> tuple:
        """Decode gain and frequency from READ response

        Response format: [ReportID, FieldID, 0, 0, 0, Cmd, 0, GainLo, GainHi, FreqLo, FreqHi, ...]
        """
        # Gain: signed 16-bit, ×10 scaling
        gain_raw = data[7] | (data[8] << 8)
        if gain_raw > 0x7FFF:
            gain_raw -= 0x10000
        gain = gain_raw / 10.0

        # Frequency: unsigned 16-bit
        freq = data[9] | (data[10] << 8)

        return gain, freq

    def _decode_q(self, data: bytes) -> tuple:
        """Decode Q factor and filter type from READ response

        Response format: [ReportID, FieldID, 0, 0, 0, Cmd, 0, QLo, QHi, Type, ...]
        """
        # Q: unsigned 16-bit, ×1000 scaling
        q = (data[7] | (data[8] << 8)) / 1000.0

        # Filter type
        filter_type = self.FILTER_TYPE_REVERSE.get(data[9], "PK")

        return q, filter_type

    def _decode_pregain(self, data: bytes) -> float:
        """Decode pregain from READ response

        Decoding (from decodeDigitalAdc):
        - If raw > 128: (raw - 256) / 2
        - Else: raw / 2
        """
        val = data[7]
        if val > 128:
            return float((val - 256) / 2.0)
        else:
            return float(val / 2.0)

    # ========================================================================
    # Filter read/write helpers
    # ========================================================================

    def _read_filter(self, index: int) -> Optional[FilterDefinition]:
        """Read a single filter (index 0-4)

        Each filter uses 2 field IDs:
        - Even field (0x26, 0x28, ...): Gain/Freq
        - Odd field (0x27, 0x29, ...): Q/Type
        """
        gain_freq_id = self.FIELD_FILTER_BASE + (index * 2)
        q_id = gain_freq_id + 1

        # Read gain/frequency
        resp = self._send_and_receive(self._build_read_packet(gain_freq_id))
        if not resp:
            return None
        gain, freq = self._decode_gain_freq(resp)

        # Read Q/type
        resp = self._send_and_receive(self._build_read_packet(q_id))
        if not resp:
            return None
        q, filter_type = self._decode_q(resp)

        # Skip bypassed filters (freq=0 or q=0 indicates disabled)
        if freq == 0 or q == 0.0:
            return None

        return FilterDefinition(freq=freq, gain=gain, q=q, type=filter_type)

    def _write_filter(self, index: int, filter_def: FilterDefinition) -> None:
        """Write a single filter (index 0-4)"""
        gain_freq_id = self.FIELD_FILTER_BASE + (index * 2)
        q_id = gain_freq_id + 1

        # Write gain/frequency
        self._send_command(
            self._build_write_gain_freq(gain_freq_id, filter_def.freq, filter_def.gain)
        )

        # Write Q/type
        self._send_command(
            self._build_write_q(q_id, filter_def.q, filter_def.type)
        )

    # ========================================================================
    # Public API
    # ========================================================================

    def read_peq(self) -> PEQProfile:
        """Read current PEQ settings from device

        Returns:
            PEQProfile with current filters and pregain

        Raises:
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Read all 5 filters
        filters = []
        for i in range(self.capabilities.max_filters):
            f = self._read_filter(i)
            if f:
                filters.append(f)

        # Read pregain
        resp = self._send_and_receive(self._build_read_packet(self.FIELD_PREGAIN))
        pregain = self._decode_pregain(resp) if resp else 0.0

        if self.debug:
            print(f"  Read {len(filters)} active filters, pregain={pregain} dB")

        return PEQProfile(filters=filters, pregain=pregain)

    def write_peq(self, profile: PEQProfile) -> None:
        """Write PEQ settings to device

        Args:
            profile: PEQ profile with filters and pregain

        Raises:
            DeviceNotConnectedError: If device not connected
            ProfileValidationError: If profile validation fails
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Validate profile
        self.validate_profile(profile)

        # Write all filters
        for i, f in enumerate(profile.filters):
            self._write_filter(i, f)
            if self.debug:
                print(f"  Filter {i+1}: {f.freq} Hz, {f.gain:+.1f} dB, Q={f.q:.2f}, {f.type}")

        # Clear remaining filter slots
        for i in range(len(profile.filters), self.capabilities.max_filters):
            # Write zero freq/Q to disable
            self._send_command(self._build_write_gain_freq(self.FIELD_FILTER_BASE + i * 2, 0, 0.0))
            self._send_command(self._build_write_q(self.FIELD_FILTER_BASE + i * 2 + 1, 0.0, "PK"))

        # Write pregain
        self._send_command(self._build_write_pregain(profile.pregain))
        if self.debug:
            print(f"  Pregain: {profile.pregain} dB")

        # Commit to flash
        if self.debug:
            print("  Committing to flash...")
        self.hid_device.write([self.REPORT_ID] + list(self._build_commit()))
        time.sleep(self.COMMIT_DELAY)

        if self.debug:
            print("  ✓ Changes saved to device")

    def set_pregain(self, pregain: float) -> None:
        """Set pregain only (without modifying filters)

        Args:
            pregain: Pregain value in dB

        Raises:
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Write pregain
        self._send_command(self._build_write_pregain(pregain))

        # Commit
        self.hid_device.write([self.REPORT_ID] + list(self._build_commit()))
        time.sleep(self.COMMIT_DELAY)

        if self.debug:
            print(f"  ✓ Pregain set to {pregain} dB")
