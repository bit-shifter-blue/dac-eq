"""Qudelix 5K DSP device handler - V3 Protocol

Supports reading and writing PEQ to USR, SPK, and B20 EQ groups.
Also supports preset management (load/save to device storage), EQ mode switching,
and preset naming for advanced workflows.

Protocol reverse-engineered from official Qudelix Chrome extension v3.2.3.0.
"""

import hid
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


class QudelixHandler(DeviceHandler):
    """Handler for Qudelix 5K DSP device (V3 Protocol)"""

    # USB identifiers
    VENDOR_ID = 0x0A12   # CSR/Qualcomm
    PRODUCT_ID = 0x4125  # Qudelix-5K
    REPORT_ID_OUT = 8    # Host to device
    REPORT_ID_IN = 9     # Device to host
    REPORT_SIZE = 64

    # Commands
    CMD_REQ_INIT_DATA = 0x0100
    CMD_SET_EQ_ENABLE = 0x0700
    CMD_SET_EQ_TYPE = 0x0701
    CMD_SET_EQ_PREGAIN = 0x0703
    CMD_SET_EQ_BAND_PARAM = 0x070F
    CMD_REQ_EQ_PRESET = 0x0123
    CMD_RSP_EQ_PRESET = 0x0128
    CMD_SAVE_EQ_PRESET = 0x0708      # Save to preset slot
    CMD_LOAD_EQ_PRESET = 0x0709      # Load from preset slot
    CMD_SET_EQ_PRESET_NAME = 0x070A  # Set custom preset name
    CMD_REQ_EQ_PRESET_NAME = 0x070B  # Request preset name
    CMD_RSP_EQ_PRESET_NAME = 0x070C  # Preset name response
    CMD_SET_EQ_MODE = 0x070E         # Switch EQ mode (usr_spk/b20)

    # EQ Groups: (group_id, max_bands, channel_mask)
    EQ_GROUPS = {
        "USR": (0, 10, 0x01),  # User EQ, 10 bands, mono
        "SPK": (1, 10, 0x03),  # Speaker EQ, 10 bands, stereo (Both/L/R selector)
        "B20": (2, 20, 0x01),  # 20-band EQ, mono (higher resolution, no L/R split)
    }

    # Preset indices
    PRESET_FLAT = 0
    PRESET_FACTORY_START = 1
    PRESET_FACTORY_END = 21
    PRESET_CUSTOM_START = 22
    PRESET_CUSTOM_END = 41
    PRESET_QXOVER_START = 42  # SPK group only
    PRESET_QXOVER_END = 52

    # EQ Modes
    EQ_MODE_USR_SPK = 0  # USR + SPK groups active
    EQ_MODE_B20 = 1      # B20 group active

    # V3 filter types
    FILTER_BYPASS = 0
    FILTER_LPF = 1
    FILTER_HPF = 2
    FILTER_LS = 3
    FILTER_HS = 4
    FILTER_PEAK = 5

    FILTER_TO_V3 = {"PK": 5, "LSQ": 3, "HSQ": 4, "LPF": 1, "HPF": 2}
    FILTER_FROM_V3 = {0: "PK", 1: "LPF", 2: "HPF", 3: "LSQ", 4: "HSQ", 5: "PK"}

    # Timing
    CMD_DELAY = 0.05       # 50ms after sending a command
    SETTLE_DELAY = 0.1     # 100ms for device to settle after operations
    INIT_DELAY = 0.3       # 300ms after init handshake
    POLL_INTERVAL = 0.01   # 10ms polling interval when draining/collecting
    CHUNK_TIMEOUT = 2.0    # 2s timeout for collecting chunked responses

    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.hid_device: Optional[hid.device] = None
        self._is_open = False
        self._initialized = False
        self._group = "USR"

    @property
    def name(self) -> str:
        return "Qudelix"

    @property
    def vendor_id(self) -> int:
        return self.VENDOR_ID

    @property
    def product_ids(self) -> Optional[List[int]]:
        return [self.PRODUCT_ID]

    @property
    def capabilities(self) -> DeviceCapabilities:
        _, max_bands, _ = self.EQ_GROUPS.get(self._group, (0, 10, 0x01))
        return DeviceCapabilities(
            max_filters=max_bands,
            gain_range=(-20.0, 20.0),
            pregain_range=(-12.0, 12.0),
            supported_filter_types={'PK', 'LSQ', 'HSQ', 'LPF', 'HPF'},
            freq_range=(20, 20000),
            q_range=(0.1, 10.0),
            supports_read=True,
            supports_write=True,
        )

    def connect(self, device_dict: dict) -> None:
        # Check if already connected and open
        if self.hid_device and self._is_open:
            if self.debug:
                print(f"[DEBUG] Qudelix: Already connected, reusing connection")
            return

        # Open new connection only if needed
        if not self.hid_device:
            self.hid_device = hid.device()

        # Use open_path to open the specific control interface, not the audio interface
        self.hid_device.open_path(device_dict['path'])
        self.hid_device.set_nonblocking(False)
        self._is_open = True
        self._initialized = False
        if self.debug:
            print(f"[DEBUG] Qudelix: Connected to {device_dict.get('product_string', 'Unknown')}")

    def disconnect(self) -> None:
        if self.hid_device and self._is_open:
            try:
                self.hid_device.close()
            except Exception:
                pass
            self._is_open = False
            self._initialized = False

    def matches_device(self, device_dict: dict) -> bool:
        if device_dict['vendor_id'] != self.VENDOR_ID:
            return False
        product = device_dict.get('product_string', '').upper()
        if not ('QUDELIX' in product or '5K' in product):
            return False
        # Must be vendor-defined HID interface (0xFF00), not audio (0x000C)
        if device_dict.get('usage_page', 0) != 0xFF00:
            if self.debug:
                print(f"[DEBUG] Qudelix: Skipping interface with usage_page 0x{device_dict.get('usage_page', 0):04X}")
            return False
        return True

    def read_peq(self, group: str = "USR") -> PEQProfile:
        """Read current PEQ settings from device.

        LIMITATION: For stereo groups (SPK, B20), this only reads the LEFT channel
        frequencies and assumes R channel is identical. If you manually set different
        L/R frequencies in the official Qudelix app, only the left channel will be
        read. Independent L/R channel EQ is not currently supported.
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        group_id, max_bands, _ = self._get_group(group)
        self._ensure_init()

        # Request preset
        self._send_cmd(self.CMD_REQ_EQ_PRESET, [1 << group_id], drain=False)
        time.sleep(self.SETTLE_DELAY)

        # Collect chunked response
        preset_data = self._collect_chunks(group_id)
        if not preset_data:
            raise DeviceCommunicationError(f"No preset data received for group {group}")

        return self._parse_preset(preset_data, group, max_bands)

    def write_peq(self, profile: PEQProfile, group: str = "USR") -> None:
        """Write PEQ settings to device.

        LIMITATION: For stereo groups (SPK, B20), this writes identical filters to
        both L and R channels (chan_mask=0x03). Independent L/R channel EQ is not
        currently supported. If you have custom L/R settings, they will be overwritten
        with identical values on both channels.
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        group_id, max_bands, chan_mask = self._get_group(group)
        if len(profile.filters) > max_bands:
            raise ValueError(f"Group {group} supports max {max_bands} filters")

        self.validate_profile(profile)
        self._ensure_init()

        if self.debug:
            print(f"  Writing to {group} EQ ({len(profile.filters)} filters)")

        # Enable EQ and set PEQ mode
        self._send_cmd(self.CMD_SET_EQ_ENABLE, [group_id, 1])
        self._send_cmd(self.CMD_SET_EQ_TYPE, [group_id, 1])

        # Set pregain
        pregain = self._to_signed16(round(profile.pregain * 10))
        self._send_cmd(self.CMD_SET_EQ_PREGAIN, [group_id, chan_mask, 0, pregain[0], pregain[1]])

        # Set filters
        for i, f in enumerate(profile.filters):
            if i >= max_bands:
                break
            self._send_band(group_id, chan_mask, i, f)

        # Bypass unused bands
        for i in range(len(profile.filters), max_bands):
            self._send_cmd(self.CMD_SET_EQ_BAND_PARAM, [group_id, chan_mask, i, 0, 0, 0, 0, 0, 0, 0])

        time.sleep(self.SETTLE_DELAY)

    def load_preset(self, group: str = "USR", preset_index: int = 0) -> None:
        """Load preset from device storage.

        Args:
            group: EQ group ("USR", "SPK", or "B20")
            preset_index: Preset slot (0=Flat, 1-21=Factory, 22-41=Custom, 42-52=QxOver)

        Raises:
            ValueError: If preset_index is out of range
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        group_id, _, _ = self._get_group(group)

        # Validate preset index
        if not (0 <= preset_index <= 58):  # T71 has up to 58
            raise ValueError(f"Preset index must be 0-58, got {preset_index}")

        if group == "SPK" and 42 <= preset_index <= 52:
            # QxOver presets valid for SPK only
            pass
        elif preset_index > 41:
            raise ValueError(f"Preset {preset_index} not valid for group {group}")

        self._ensure_init()

        if self.debug:
            print(f"  Loading preset {preset_index} for {group} group")

        self._send_cmd(self.CMD_LOAD_EQ_PRESET, [group_id, preset_index])
        time.sleep(self.SETTLE_DELAY)

    def save_preset(self, group: str = "USR", preset_index: int = 22) -> None:
        """Save current EQ settings to device preset slot.

        Args:
            group: EQ group ("USR", "SPK", or "B20")
            preset_index: Custom preset slot (22-41 only, factory presets are read-only)

        Raises:
            ValueError: If preset_index is not in custom range (22-41)
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        group_id, _, _ = self._get_group(group)

        # Only allow saving to custom preset slots
        if not (self.PRESET_CUSTOM_START <= preset_index <= self.PRESET_CUSTOM_END):
            raise ValueError(
                f"Can only save to custom presets ({self.PRESET_CUSTOM_START}-{self.PRESET_CUSTOM_END}), "
                f"got {preset_index}"
            )

        self._ensure_init()

        if self.debug:
            print(f"  Saving to preset {preset_index} for {group} group")

        self._send_cmd(self.CMD_SAVE_EQ_PRESET, [group_id, preset_index])
        time.sleep(self.SETTLE_DELAY)

    def set_eq_mode(self, mode: str) -> None:
        """Switch EQ mode (determines which groups are active).

        Args:
            mode: Either "usr_spk" (USR+SPK active) or "b20" (B20 active)

        Raises:
            ValueError: If mode is invalid
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        mode_map = {
            "usr_spk": self.EQ_MODE_USR_SPK,
            "b20": self.EQ_MODE_B20
        }

        if mode not in mode_map:
            raise ValueError(f"Invalid mode '{mode}'. Valid: usr_spk, b20")

        self._ensure_init()

        if self.debug:
            print(f"  Setting EQ mode to {mode}")

        self._send_cmd(self.CMD_SET_EQ_MODE, [mode_map[mode]])
        time.sleep(self.SETTLE_DELAY)

    def get_preset_name(self, preset_index: int, group: str = "USR") -> str:
        """Get custom preset name from device.

        Args:
            preset_index: Custom preset slot (22-41 only)
            group: EQ group ("USR", "SPK", or "B20")

        Returns:
            Preset name string (may be empty for unnamed presets)

        Raises:
            ValueError: If preset_index is not in custom range
            DeviceNotConnectedError: If device not connected
            DeviceCommunicationError: If no response received
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        if not (self.PRESET_CUSTOM_START <= preset_index <= self.PRESET_CUSTOM_END):
            raise ValueError(
                f"Can only get names for custom presets ({self.PRESET_CUSTOM_START}-{self.PRESET_CUSTOM_END}), "
                f"got {preset_index}"
            )

        self._ensure_init()

        group_id, _, _ = self._get_group(group)

        if self.debug:
            print(f"  Requesting name for preset {preset_index}")

        # Request preset name using custom index (0-19)
        # V3 protocol: [group, custom_index]
        custom_index = preset_index - self.PRESET_CUSTOM_START
        self._send_cmd(self.CMD_REQ_EQ_PRESET_NAME, [group_id, custom_index], drain=False)
        time.sleep(self.SETTLE_DELAY)

        # Read response
        self.hid_device.set_nonblocking(True)
        start = time.time()
        while (time.time() - start) < 1.0:  # 1s timeout
            raw = self.hid_device.read(64)
            if not raw:
                time.sleep(self.POLL_INTERVAL)
                continue

            data = raw[1:] if raw[0] == self.REPORT_ID_IN else raw
            if len(data) < 4:
                continue

            cmd = (data[1] << 8) | data[2]
            if cmd != self.CMD_RSP_EQ_PRESET_NAME:
                continue

            # V3 Response format: [length][cmd_hi][cmd_lo][group][custom_idx][name_length][name_bytes...]
            if len(data) < 6:
                continue

            resp_group = data[3]
            resp_custom_idx = data[4]

            # Verify this response is for our request
            if resp_group != group_id or resp_custom_idx != custom_index:
                continue

            # Extract name length and name bytes
            name_length = data[5]
            name_bytes = bytes(data[6:6 + name_length])
            name = name_bytes.decode('utf-8', errors='replace')

            if self.debug:
                print(f"  Preset {preset_index} name: '{name}'")

            return name

        raise DeviceCommunicationError(f"No preset name response for index {preset_index}")

    def set_preset_name(self, preset_index: int, name: str, group: str = "USR") -> None:
        """Set custom preset name on device.

        Args:
            preset_index: Custom preset slot (22-41 only)
            name: Preset name (max length ~20 chars, will be truncated)
            group: EQ group ("USR", "SPK", or "B20")

        Raises:
            ValueError: If preset_index is not in custom range
            DeviceNotConnectedError: If device not connected
        """
        if not self.hid_device:
            raise DeviceNotConnectedError("Device not connected")

        if not (self.PRESET_CUSTOM_START <= preset_index <= self.PRESET_CUSTOM_END):
            raise ValueError(
                f"Can only set names for custom presets ({self.PRESET_CUSTOM_START}-{self.PRESET_CUSTOM_END}), "
                f"got {preset_index}"
            )

        self._ensure_init()

        group_id, _, _ = self._get_group(group)

        # Truncate name to fit in packet (max ~20 chars to be safe)
        name_bytes = name.encode('utf-8')[:20]

        if self.debug:
            print(f"  Setting name for preset {preset_index}: '{name}'")

        # V3 protocol payload: [group, custom_index (0-19), name_length, name_bytes...]
        # Preset 22-41 maps to custom index 0-19
        custom_index = preset_index - self.PRESET_CUSTOM_START
        payload = [group_id, custom_index, len(name_bytes)] + list(name_bytes)
        self._send_cmd(self.CMD_SET_EQ_PRESET_NAME, payload)
        time.sleep(self.SETTLE_DELAY)

    # --- Private helpers ---

    def _get_group(self, group: str) -> Tuple[int, int, int]:
        if group not in self.EQ_GROUPS:
            raise ValueError(f"Unknown group '{group}'. Valid: USR, SPK, B20")
        self._group = group
        return self.EQ_GROUPS[group]

    def _ensure_init(self) -> None:
        if self._initialized:
            return
        if self.debug:
            print("  Sending init handshake...")
        self._send_cmd(self.CMD_REQ_INIT_DATA, [0x00, 0x00, 0x04], drain=False)
        time.sleep(self.INIT_DELAY)
        self._drain_responses()
        self._initialized = True

    def _send_cmd(self, cmd: int, payload: List[int], drain: bool = True) -> None:
        """Send HID command."""
        pkt = [0] * self.REPORT_SIZE
        pkt[0] = len(payload) + 3  # length
        pkt[1] = 0x80              # HID marker
        pkt[2] = (cmd >> 8) & 0xFF
        pkt[3] = cmd & 0xFF
        pkt[4:4 + len(payload)] = payload

        if self.debug:
            print(f"  CMD 0x{cmd:04X}: {' '.join(f'{b:02X}' for b in pkt[:pkt[0]+1])}")

        self.hid_device.write([self.REPORT_ID_OUT] + pkt)
        time.sleep(self.CMD_DELAY)

        if drain:
            self._drain_responses()

    def _send_band(self, group_id: int, chan_mask: int, band: int, f: FilterDefinition) -> None:
        """Send a single band parameter."""
        ftype = self.FILTER_TO_V3.get(f.type, self.FILTER_PEAK)
        freq = self._to_uint16(round(f.freq))
        gain = self._to_signed16(round(f.gain * 10))
        q = self._to_uint16(round(f.q * 1024))
        self._send_cmd(self.CMD_SET_EQ_BAND_PARAM, [
            group_id, chan_mask, band, ftype,
            freq[0], freq[1], gain[0], gain[1], q[0], q[1]
        ])

    def _drain_responses(self) -> None:
        """Drain response buffer."""
        self.hid_device.set_nonblocking(True)
        for _ in range(20):
            if not self.hid_device.read(64):
                break
            time.sleep(self.POLL_INTERVAL)

    def _collect_chunks(self, group_id: int, timeout: float = CHUNK_TIMEOUT) -> bytearray:
        """Collect chunked preset response."""
        chunks = {}
        self.hid_device.set_nonblocking(True)
        start = time.time()

        while (time.time() - start) < timeout:
            raw = self.hid_device.read(64)
            if not raw:
                time.sleep(self.POLL_INTERVAL)
                continue

            # Skip report ID
            data = raw[1:] if raw[0] == self.REPORT_ID_IN else raw
            if len(data) < 9 or data[0] < 3:
                continue

            cmd = (data[1] << 8) | data[2]
            if cmd != self.CMD_RSP_EQ_PRESET or data[3] != group_id:
                continue

            idx_byte = data[4]
            last_idx = (idx_byte >> 4) & 0x0F
            chunk_idx = idx_byte & 0x0F
            chunk_size = (data[5] << 8) | data[6]
            offset = (data[7] << 8) | data[8]

            if self.debug:
                print(f"  Chunk {chunk_idx}/{last_idx}: {chunk_size}B at offset {offset}")

            chunks[chunk_idx] = (offset, data[9:9 + chunk_size])
            if len(chunks) == last_idx + 1:
                break

        # Reassemble
        result = bytearray()
        for idx in sorted(chunks.keys()):
            offset, chunk = chunks[idx]
            while len(result) < offset + len(chunk):
                result.append(0)
            result[offset:offset + len(chunk)] = chunk
        return result

    def _parse_preset(self, data: bytearray, group: str, max_bands: int) -> PEQProfile:
        """Parse preset data into PEQProfile.

        Data structures vary by group:
        - USR/SPK: Header(4) + Pregain(4) + FreqL(2×bands) + FreqR(2×bands) + Params(4×bands)
        - B20: Header(4) + Pregain(4) + Freq(2×bands) + Params(4×bands)  [no FreqR, more compact]

        Band param: [rsv:4][q:14][gain:10][filter:4] as 32-bit LE
        """
        if len(data) < 8:
            raise DeviceCommunicationError(f"Preset data too short: {len(data)} bytes")

        offset = 4  # Skip header
        pregain = self._read_i16(data, offset) / 10.0
        offset += 4  # Skip L+R pregain

        # Read L frequencies
        freqs = [self._read_u16(data, offset + i*2) for i in range(max_bands)]
        offset += max_bands * 2

        # Skip R frequencies for USR/SPK (they have redundant/stereo FreqR data)
        # B20 has no FreqR array - it's pure mono, more compact structure
        if group in ("USR", "SPK"):
            offset += max_bands * 2

        # Parse band params
        filters = []
        for i in range(max_bands):
            if offset + 4 > len(data):
                break
            packed = self._read_u32(data, offset)
            offset += 4

            ftype = packed & 0x0F
            gain_raw = (packed >> 4) & 0x3FF
            if gain_raw & 0x200:
                gain_raw -= 0x400
            q_raw = (packed >> 14) & 0x3FFF

            # Skip bypass with zero gain
            if ftype == self.FILTER_BYPASS and abs(gain_raw) < 1:
                continue

            filters.append(FilterDefinition(
                freq=freqs[i] if i < len(freqs) else 1000,
                gain=round(gain_raw / 10.0, 1),
                q=round(q_raw / 1024.0, 2),
                type=self.FILTER_FROM_V3.get(ftype, "PK")
            ))

        return PEQProfile(pregain=round(pregain, 1), filters=filters)

    # --- Byte helpers ---

    def _to_uint16(self, v: int) -> List[int]:
        return [(v >> 8) & 0xFF, v & 0xFF]

    def _to_signed16(self, v: int) -> List[int]:
        if v < 0:
            v += 0x10000
        return self._to_uint16(v)

    def _read_u16(self, data: bytearray, off: int) -> int:
        return data[off] | (data[off + 1] << 8)

    def _read_i16(self, data: bytearray, off: int) -> int:
        v = self._read_u16(data, off)
        return v - 0x10000 if v & 0x8000 else v

    def _read_u32(self, data: bytearray, off: int) -> int:
        return data[off] | (data[off+1] << 8) | (data[off+2] << 16) | (data[off+3] << 24)
