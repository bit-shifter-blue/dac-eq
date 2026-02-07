"""Tanchjim DSP device handler (Fission, Bunny, One DSP)"""

import hid
import time
from typing import Optional, List
from ..base import (
    DeviceHandler,
    PEQProfile,
    FilterDefinition,
    DeviceCapabilities,
    DeviceNotConnectedError,
    DeviceCommunicationError,
)


class TanchjimHandler(DeviceHandler):
    """Handler for Tanchjim DSP devices (Fission, Bunny, One DSP)"""

    # Protocol constants
    VENDOR_ID = 0x31B2
    REPORT_ID = 0x4B

    # Commands
    COMMAND_READ = 0x52
    COMMAND_WRITE = 0x57
    COMMAND_COMMIT = 0x53
    COMMAND_CLEAR = 0x43

    # Field IDs
    FIELD_ENABLE = 0x24
    FIELD_PREGAIN = 0x66
    FIELD_FILTER_BASE = 0x26  # Gain/freq for filter 0, increments by 2

    # Slots
    DISABLED_SLOT = 0x02
    CUSTOM_SLOT = 0x03

    # Filter types
    FILTER_TYPE_MAP = {"PK": 0, "LSQ": 3, "HSQ": 4}
    FILTER_TYPE_REVERSE = {0: "PK", 3: "LSQ", 4: "HSQ"}

    # Timing
    WRITE_DELAY = 0.02  # 20ms between writes
    COMMIT_DELAY = 1.0  # 1s after commit
    READ_TIMEOUT_MS = 1000  # HID read timeout

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

        # Check product name for Tanchjim devices
        product_name = device_dict.get('product_string', '').upper()
        return any(keyword in product_name for keyword in ['FISSION', 'TANCHJIM', 'BUNNY', 'ONE'])

    def connect(self, device_dict: dict) -> None:
        """Connect to the device"""
        self.hid_device = hid.device()
        self.hid_device.open_path(device_dict['path'])
        self.hid_device.set_nonblocking(False)

        if self.debug:
            product_name = device_dict.get('product_string', 'Unknown')
            print(f"[DEBUG] Tanchjim: Connected to {product_name}")

    def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    def _send_and_receive(self, packet: bytes, timeout_ms: int = READ_TIMEOUT_MS) -> Optional[bytes]:
        """Send HID packet and receive response"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        self.hid_device.write([self.REPORT_ID] + list(packet))
        resp = self.hid_device.read(64, timeout_ms)

        if self.debug and resp:
            print(f"  DEBUG sent: {' '.join(f'{b:02X}' for b in packet[:12])}")
            print(f"  DEBUG recv: {' '.join(f'{b:02X}' for b in resp[:16])}")

        return bytes(resp) if resp else None

    def _build_read_packet(self, field_id: int) -> bytes:
        """Build a read packet for a field"""
        return bytes([field_id, 0x00, 0x00, 0x00, self.COMMAND_READ, 0x00, 0x00, 0x00, 0x00])

    def _build_write_gain_freq(self, filter_id: int, freq: int, gain: float) -> bytes:
        """Build packet for gain/frequency write"""
        # Gain: signed 16-bit, scaled by 10
        gain_raw = int(gain * 10)
        if gain_raw < 0:
            gain_raw += 0x10000

        # Freq: unsigned 16-bit (no 2x compensation for Fission)
        freq_raw = int(freq)

        return bytes([
            filter_id, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00,
            gain_raw & 0xFF, (gain_raw >> 8) & 0xFF,
            freq_raw & 0xFF, (freq_raw >> 8) & 0xFF
        ])

    def _build_write_q(self, filter_id: int, q: float, filter_type: str) -> bytes:
        """Build packet for Q value write"""
        q_raw = int(q * 1000)
        type_byte = self.FILTER_TYPE_MAP.get(filter_type, 0)

        return bytes([
            filter_id, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00,
            q_raw & 0xFF, (q_raw >> 8) & 0xFF,
            type_byte, 0x00
        ])

    def _build_enable_eq(self, slot_id: int) -> bytes:
        """Build packet to enable EQ with slot"""
        return bytes([self.FIELD_ENABLE, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00, slot_id, 0x00, 0x00, 0x00])

    def _build_write_pregain(self, value: float) -> bytes:
        """Build packet to write pregain"""
        val = int(round(value))
        if val < 0:
            val = val & 0xFF
        return bytes([self.FIELD_PREGAIN, 0x00, 0x00, 0x00, self.COMMAND_WRITE, 0x00, val, 0x00, 0x00, 0x00])

    def _build_commit(self) -> bytes:
        """Build commit packet"""
        return bytes([0x00, 0x00, 0x00, 0x00, self.COMMAND_COMMIT, 0x00, 0x00, 0x00, 0x00, 0x00])

    def _decode_gain_freq(self, data: bytes) -> tuple:
        """Decode gain and frequency from response"""
        # Note: hidapi includes report ID as byte 0, so all indices are +1 from WebHID
        # Bytes: [ReportID, FieldID, 0, 0, 0, Cmd, 0, GainLo, GainHi, FreqLo, FreqHi]
        gain_raw = data[7] | (data[8] << 8)
        if gain_raw > 0x7FFF:
            gain_raw -= 0x10000
        gain = gain_raw / 10.0

        freq = data[9] | (data[10] << 8)

        return gain, freq

    def _decode_q(self, data: bytes) -> tuple:
        """Decode Q and filter type from response"""
        # Bytes: [ReportID, FieldID, 0, 0, 0, Cmd, 0, QLo, QHi, FilterType, 0]
        q = (data[7] | (data[8] << 8)) / 1000.0
        filter_type = self.FILTER_TYPE_REVERSE.get(data[9], "PK")

        return q, filter_type

    def _read_filter(self, index: int) -> Optional[FilterDefinition]:
        """Read a single filter (0-4)"""
        gain_freq_id = self.FIELD_FILTER_BASE + index * 2
        q_id = gain_freq_id + 1

        # Read gain/freq
        resp = self._send_and_receive(self._build_read_packet(gain_freq_id))
        if not resp:
            return None
        gain, freq = self._decode_gain_freq(resp)

        # Read Q
        resp = self._send_and_receive(self._build_read_packet(q_id))
        if not resp:
            return None
        q, filter_type = self._decode_q(resp)

        return FilterDefinition(freq=freq, gain=gain, q=q, type=filter_type)

    def _read_pregain(self) -> float:
        """Read current pregain value"""
        resp = self._send_and_receive(
            bytes([self.FIELD_PREGAIN, 0x00, 0x00, 0x00, self.COMMAND_READ, 0x00, 0x00, 0x00, 0x00])
        )
        if resp:
            val = resp[7]
            return float(val - 256 if val > 127 else val)
        return 0.0

    def read_peq(self) -> PEQProfile:
        """Read current PEQ settings from device"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        filters = []
        for i in range(self.capabilities.max_filters):
            f = self._read_filter(i)
            if f:
                filters.append(f)

        pregain = self._read_pregain()

        return PEQProfile(filters=filters, pregain=pregain)

    def _write_filter(self, index: int, filter_def: FilterDefinition) -> None:
        """Write a single filter"""
        gain_freq_id = self.FIELD_FILTER_BASE + index * 2
        q_id = gain_freq_id + 1

        # Write gain/freq
        self.hid_device.write(
            [self.REPORT_ID] + list(self._build_write_gain_freq(gain_freq_id, filter_def.freq, filter_def.gain))
        )
        time.sleep(self.WRITE_DELAY)

        # Write Q
        self.hid_device.write(
            [self.REPORT_ID] + list(self._build_write_q(q_id, filter_def.q, filter_def.type))
        )
        time.sleep(self.WRITE_DELAY)

    def _write_pregain(self, value: float) -> None:
        """Write pregain value"""
        self.hid_device.write([self.REPORT_ID] + list(self._build_write_pregain(value)))
        time.sleep(self.WRITE_DELAY)

    def _enable_eq(self, slot_id: int) -> None:
        """Enable EQ with specified slot"""
        self.hid_device.write([self.REPORT_ID] + list(self._build_enable_eq(slot_id)))
        time.sleep(self.WRITE_DELAY)

    def _commit(self) -> None:
        """Save changes to device"""
        self.hid_device.write([self.REPORT_ID] + list(self._build_commit()))
        time.sleep(self.COMMIT_DELAY)

    def write_peq(self, profile: PEQProfile) -> None:
        """Write PEQ settings to device"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Validate profile first
        self.validate_profile(profile)

        # Enable custom slot
        self._enable_eq(self.CUSTOM_SLOT)

        # Write filters
        for i, f in enumerate(profile.filters):
            self._write_filter(i, f)
            if self.debug:
                print(f"  Filter {i+1}: {f.freq} Hz, {f.gain:+.1f} dB, Q={f.q:.2f}, {f.type}")

        # Write pregain
        self._write_pregain(profile.pregain)
        if self.debug:
            print(f"  Pregain: {profile.pregain} dB")

        # Commit changes
        self._commit()

        if self.debug:
            print("  Changes saved to device!")
