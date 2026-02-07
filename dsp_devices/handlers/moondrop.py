"""Moondrop DSP device handler (Modern Protocol)

Supports:
- DSP Cables: FreeDSP Pro, FreeDSP Mini
- IEMs with DSP: Rays, Marigold, MAY DSP
- Other: ddHiFi DSP IEM - Memory

Protocol: Conexant-based, 63-byte packets, biquad coefficients, 256x scaling
"""

import hid
import math
import time
from typing import Optional, List, Tuple
from ..base import (
    DeviceHandler,
    PEQProfile,
    FilterDefinition,
    DeviceCapabilities,
    DeviceNotConnectedError,
    DeviceCommunicationError,
)


class MoondropHandler(DeviceHandler):
    """Handler for Moondrop DSP devices using modern protocol (Conexant-based)"""

    # Protocol constants
    VENDOR_IDS = [
        0x3302,  # WalkPlay (primary)
        0x0762,  # Nextech
        0x35D8,  # Conexant variant
        0x2FC6,  # OEM variant
        0x0104,  # Panasonic
        0xB445,  # Zephyr
        0x0661,  # TP-Link variant 1
        0x0666,  # TP-Link variant 2
        0x0D8C,  # GN Store Nord
    ]
    REPORT_ID = 0x4B

    # Commands
    COMMAND_READ = 0x80
    COMMAND_WRITE = 0x01
    COMMAND_UPDATE_EQ = 0x09
    COMMAND_UPDATE_EQ_COEFF_TO_REG = 0x0A
    COMMAND_SAVE_EQ_TO_FLASH = 0x01
    COMMAND_PRE_GAIN = 0x23
    COMMAND_SET_DAC_OFFSET = 0x03

    # Filter types (Moondrop uses different codes than Tanchjim!)
    FILTER_TYPE_MAP = {
        "PK": 2,   # Peaking
        "LSQ": 1,  # Low-shelf
        "HSQ": 3,  # High-shelf
    }
    FILTER_TYPE_REVERSE = {2: "PK", 1: "LSQ", 3: "HSQ"}

    # Timing
    WRITE_DELAY = 0.02  # 20ms between writes
    SAVE_DELAY = 1.0    # 1s after save

    # Scaling factors
    BIQUAD_SCALE = 1073741824  # 2^30 for biquad coefficients
    VALUE_SCALE = 256          # 256x for gain/Q values
    SAMPLE_RATE = 96000        # Assumed sample rate for biquad calculation

    def __init__(self):
        super().__init__()
        self.hid_device: Optional[hid.device] = None

    @property
    def name(self) -> str:
        return "Moondrop"

    @property
    def vendor_id(self) -> int:
        """Return primary vendor ID for base class compatibility"""
        return self.VENDOR_IDS[0]

    @property
    def product_ids(self) -> Optional[List[int]]:
        return None  # Accept any product from supported vendors

    @property
    def capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities(
            max_filters=8,
            gain_range=(-20.0, 20.0),
            pregain_range=(-12.0, 12.0),
            supported_filter_types={'PK', 'LSQ', 'HSQ'},
            freq_range=(20, 20000),
            q_range=(0.1, 10.0),
            supports_read=True,
            supports_write=True,
        )

    def matches_device(self, device_dict: dict) -> bool:
        """Check if this handler matches a Moondrop DSP device"""
        # Check vendor ID
        if device_dict['vendor_id'] not in self.VENDOR_IDS:
            return False

        # Check product name for Moondrop keywords
        product_name = device_dict.get('product_string', '').upper()

        # Keywords that indicate Moondrop DSP device
        keywords = ['MOONDROP', 'RAYS', 'MARIGOLD', 'MAY', 'FREEDSP', 'DDHIFI DSP']

        # Keywords to exclude (devices without DSP)
        exclude = ['MOONRIVER', 'ARIA', 'BLESSING', 'STARFIELD', 'KATO']

        has_keyword = any(kw in product_name for kw in keywords)
        has_exclude = any(kw in product_name for kw in exclude)

        return has_keyword and not has_exclude

    def connect(self, device_dict: dict) -> None:
        """Connect to the device"""
        self.hid_device = hid.device()
        self.hid_device.open_path(device_dict['path'])
        self.hid_device.set_nonblocking(False)

        if self.debug:
            product_name = device_dict.get('product_string', 'Unknown')
            vendor_id = device_dict['vendor_id']
            print(f"[DEBUG] Moondrop: Connected to {product_name} (VID: 0x{vendor_id:04X})")

    def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    def _send_and_receive(self, packet: bytes, timeout_ms: int = 1000) -> Optional[bytes]:
        """Send HID packet and receive response"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Send packet with report ID
        self.hid_device.write([self.REPORT_ID] + list(packet))

        # Receive response
        resp = self.hid_device.read(64, timeout_ms)

        if self.debug and resp:
            print(f"  DEBUG sent: {' '.join(f'{b:02X}' for b in packet[:20])}")
            print(f"  DEBUG recv: {' '.join(f'{b:02X}' for b in resp[:20])}")

        return bytes(resp) if resp else None

    def _encode_biquad(self, freq: int, gain: float, q: float) -> List[int]:
        """Calculate biquad coefficients for peaking filter

        Based on Robert Bristow-Johnson's Audio EQ Cookbook
        Returns: [b0, b1, b2, a1, -a2] as 32-bit signed integers

        Args:
            freq: Center frequency in Hz
            gain: Gain in dB
            q: Q factor

        Returns:
            List of 5 coefficients scaled by 2^30
        """
        # Step 1: Convert gain to amplitude
        A = math.pow(10, gain / 40.0)

        # Step 2: Calculate angular frequency (normalized to sample rate)
        w0 = (2 * math.pi * freq) / self.SAMPLE_RATE

        # Step 3: Calculate alpha (bandwidth parameter)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2 * q)

        # Step 4: Calculate cosine
        cos_w0 = math.cos(w0)

        # Step 5: Calculate normalization factor
        norm = 1 + alpha / A

        # Step 6: Calculate b coefficients (numerator)
        b0 = (1 + alpha * A) / norm
        b1 = (-2 * cos_w0) / norm
        b2 = (1 - alpha * A) / norm

        # Step 7: Calculate a coefficients (denominator)
        a1 = -b1
        a2 = (1 - alpha / A) / norm

        # Step 8: Scale by 2^30 and convert to 32-bit signed integers
        coefficients = [b0, b1, b2, a1, -a2]
        scaled = [round(c * self.BIQUAD_SCALE) for c in coefficients]

        if self.debug:
            print(f"  DEBUG biquad: freq={freq}Hz, gain={gain}dB, q={q}")
            print(f"    Coefficients: {[f'{c:.6f}' for c in coefficients]}")
            print(f"    Scaled: {[f'0x{s & 0xFFFFFFFF:08X}' for s in scaled]}")

        return scaled

    def _encode_int32_le(self, value: int) -> List[int]:
        """Encode 32-bit signed integer as 4 little-endian bytes"""
        # Handle negative values (two's complement)
        if value < 0:
            value = value + 0x100000000

        return [
            value & 0xFF,
            (value >> 8) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 24) & 0xFF,
        ]

    def _decode_int32_le(self, data: bytes, offset: int) -> int:
        """Decode 32-bit signed integer from 4 little-endian bytes"""
        value = (data[offset] |
                (data[offset + 1] << 8) |
                (data[offset + 2] << 16) |
                (data[offset + 3] << 24))

        # Convert to signed
        if value > 0x7FFFFFFF:
            value -= 0x100000000

        return value

    def _encode_int16_le(self, value: int) -> List[int]:
        """Encode 16-bit signed integer as 2 little-endian bytes"""
        # Handle negative values (two's complement)
        if value < 0:
            value = value + 0x10000

        return [value & 0xFF, (value >> 8) & 0xFF]

    def _decode_int16_le(self, data: bytes, offset: int) -> int:
        """Decode 16-bit signed integer from 2 little-endian bytes"""
        value = data[offset] | (data[offset + 1] << 8)

        # Convert to signed
        if value > 0x7FFF:
            value -= 0x10000

        return value

    def _build_read_packet(self, filter_index: int) -> bytes:
        """Build read packet for a filter (6 bytes)

        Format: [0x80, 0x09, 0x18, 0x00, filterIndex, 0x00]
        """
        return bytes([
            self.COMMAND_READ,
            self.COMMAND_UPDATE_EQ,
            0x18,
            0x00,
            filter_index,
            0x00
        ])

    def _build_read_pregain_packet(self) -> bytes:
        """Build read packet for pregain (2 bytes minimum)"""
        return bytes([self.COMMAND_READ, self.COMMAND_SET_DAC_OFFSET])

    def _build_write_packet(self, filter_index: int, filter_def: FilterDefinition) -> bytes:
        """Build 63-byte write packet for a filter

        Packet structure:
        - Bytes 0-6: Header
        - Bytes 7-26: Biquad coefficients (5 × 4 bytes)
        - Bytes 27-28: Frequency (16-bit unsigned LE)
        - Bytes 29-30: Q value (16-bit unsigned LE, scaled by 256)
        - Bytes 31-32: Gain (16-bit signed LE, scaled by 256)
        - Byte 33: Filter type (1=LSQ, 2=PK, 3=HSQ)
        - Bytes 34-35: [0x00, 0x07] (peqIndex marker)
        - Bytes 36-62: Padding zeros
        """
        packet = [0] * 63

        # Header
        packet[0] = self.COMMAND_WRITE
        packet[1] = self.COMMAND_UPDATE_EQ
        packet[2] = 0x18
        packet[3] = 0x00
        packet[4] = filter_index
        packet[5] = 0x00
        packet[6] = 0x00

        # Calculate and encode biquad coefficients
        biquad_coeffs = self._encode_biquad(filter_def.freq, filter_def.gain, filter_def.q)
        offset = 7
        for coeff in biquad_coeffs:
            coeff_bytes = self._encode_int32_le(coeff)
            packet[offset:offset + 4] = coeff_bytes
            offset += 4

        # Frequency (16-bit unsigned LE)
        packet[27:29] = self._encode_int16_le(filter_def.freq)

        # Q value (16-bit unsigned LE, scaled by 256)
        q_scaled = int(round(filter_def.q * self.VALUE_SCALE))
        packet[29:31] = self._encode_int16_le(q_scaled)

        # Gain (16-bit signed LE, scaled by 256)
        gain_scaled = int(round(filter_def.gain * self.VALUE_SCALE))
        packet[31:33] = self._encode_int16_le(gain_scaled)

        # Filter type
        packet[33] = self.FILTER_TYPE_MAP.get(filter_def.type, 2)

        # peqIndex marker
        packet[34] = 0x00
        packet[35] = 0x07

        # Remaining bytes already zeroed

        return bytes(packet)

    def _build_enable_packet(self, filter_index: int) -> bytes:
        """Build enable packet to commit coefficient to register (63 bytes)

        Format: [0x01, 0x0A, filterIndex, 0xFF, 0xFF, 0xFF, ...]
        """
        packet = [0xFF] * 63
        packet[0] = self.COMMAND_WRITE
        packet[1] = self.COMMAND_UPDATE_EQ_COEFF_TO_REG
        packet[2] = filter_index

        return bytes(packet)

    def _build_save_packet(self) -> bytes:
        """Build save packet to persist settings to flash (63 bytes)

        Format: [0x01, 0x01, padding...]
        """
        packet = [0x00] * 63
        packet[0] = self.COMMAND_WRITE
        packet[1] = self.COMMAND_SAVE_EQ_TO_FLASH

        return bytes(packet)

    def _build_write_pregain_packet(self, pregain: float) -> bytes:
        """Build write packet for pregain (63 bytes)

        Format: [0x01, 0x23, 0x00, pregain_lo, pregain_hi, padding...]
        """
        packet = [0x00] * 63
        packet[0] = self.COMMAND_WRITE
        packet[1] = self.COMMAND_PRE_GAIN
        packet[2] = 0x00

        # Pregain scaled by 256
        pregain_scaled = int(round(pregain * self.VALUE_SCALE))
        pregain_bytes = self._encode_int16_le(pregain_scaled)
        packet[3:5] = pregain_bytes

        return bytes(packet)

    def _decode_filter_response(self, response: bytes) -> Optional[FilterDefinition]:
        """Decode filter from 64-byte read response

        Response structure:
        - Bytes 0-6: Status/Header
        - Bytes 7-26: Biquad coefficients (not used in decode)
        - Bytes 27-28: Frequency (16-bit unsigned LE)
        - Bytes 29-30: Q value (16-bit unsigned LE, scaled by 256)
        - Bytes 31-32: Gain (16-bit signed LE, scaled by 256)
        - Byte 33: Filter type (1=LSQ, 2=PK, 3=HSQ)
        """
        if len(response) < 34:
            return None

        # Extract frequency
        freq = response[27] | (response[28] << 8)

        # Extract Q value (scaled by 256)
        q_raw = response[29] | (response[30] << 8)
        q = q_raw / self.VALUE_SCALE

        # Extract gain (scaled by 256, signed)
        gain_raw = self._decode_int16_le(response, 31)
        gain = gain_raw / self.VALUE_SCALE

        # Extract filter type
        filter_type_code = response[33]
        filter_type = self.FILTER_TYPE_REVERSE.get(filter_type_code, "PK")

        if self.debug:
            print(f"  DEBUG decode: freq={freq}Hz, gain={gain:.2f}dB, q={q:.3f}, type={filter_type}")

        return FilterDefinition(freq=freq, gain=gain, q=q, type=filter_type)

    def _decode_pregain_response(self, response: bytes) -> float:
        """Decode pregain from read response

        Pregain is at bytes 3-4, signed 16-bit LE, scaled by 256
        """
        if len(response) < 5:
            return 0.0

        pregain_raw = self._decode_int16_le(response, 3)
        pregain = pregain_raw / self.VALUE_SCALE

        if self.debug:
            print(f"  DEBUG pregain: raw={pregain_raw}, value={pregain:.2f}dB")

        return pregain

    def read_peq(self) -> PEQProfile:
        """Read current PEQ settings from device"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        filters = []

        # Read all 8 filters
        for i in range(self.capabilities.max_filters):
            packet = self._build_read_packet(i)
            response = self._send_and_receive(packet)

            if response:
                filter_def = self._decode_filter_response(response)
                if filter_def:
                    filters.append(filter_def)
                    if self.debug:
                        print(f"  Filter {i}: {filter_def.freq}Hz, {filter_def.gain:+.1f}dB, "
                              f"Q={filter_def.q:.2f}, {filter_def.type}")

            time.sleep(0.01)  # Small delay between reads

        # Read pregain
        pregain_packet = self._build_read_pregain_packet()
        pregain_response = self._send_and_receive(pregain_packet)
        pregain = self._decode_pregain_response(pregain_response) if pregain_response else 0.0

        if self.debug:
            print(f"  Pregain: {pregain:.2f}dB")

        return PEQProfile(filters=filters, pregain=pregain)

    def write_peq(self, profile: PEQProfile) -> None:
        """Write PEQ settings to device"""
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        # Validate profile first
        self.validate_profile(profile)

        # Write pregain first
        pregain_packet = self._build_write_pregain_packet(profile.pregain)
        self.hid_device.write([self.REPORT_ID] + list(pregain_packet))
        time.sleep(self.WRITE_DELAY)

        if self.debug:
            print(f"  Pregain: {profile.pregain:.2f}dB")

        # Write each filter with enable sequence
        for i, filter_def in enumerate(profile.filters):
            # Write filter coefficient packet
            write_packet = self._build_write_packet(i, filter_def)
            self.hid_device.write([self.REPORT_ID] + list(write_packet))
            time.sleep(self.WRITE_DELAY)

            # Send enable packet to commit to register
            enable_packet = self._build_enable_packet(i)
            self.hid_device.write([self.REPORT_ID] + list(enable_packet))
            time.sleep(self.WRITE_DELAY)

            if self.debug:
                print(f"  Filter {i}: {filter_def.freq}Hz, {filter_def.gain:+.1f}dB, "
                      f"Q={filter_def.q:.2f}, {filter_def.type}")

        # Save to flash
        save_packet = self._build_save_packet()
        self.hid_device.write([self.REPORT_ID] + list(save_packet))
        time.sleep(self.SAVE_DELAY)

        if self.debug:
            print("  Settings saved to device!")
