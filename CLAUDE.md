# CLAUDE.md - DAC EQ

This file provides guidance to Claude Code when working with the DAC EQ project.

## Project Overview

**DAC EQ** is a Python CLI tool and MCP server ecosystem for controlling Parametric EQ (PEQ) on USB DSP/DAC devices via HID protocol on macOS.

**Key capabilities:**
- Read/write PEQ settings to DSP devices (Tanchjim, Qudelix, Moondrop, etc.)
- Apply EQ profiles stored as JSON
- Integrate with IEM frequency response data (squiglink) and AutoEQ optimization
- Expose functionality via MCP servers for Claude Code workflows

**Based on:** devicePEQ by Pragmatic Audio (jeromeof)

---

## Architecture

### Core CLI Tool

```
dac-eq.py (CLI entry point)
    │
    └── dsp_devices/
        ├── registry.py          # Device discovery and management
        ├── base.py              # Base classes (PEQProfile, FilterDefinition, DeviceCapabilities)
        └── handlers/
            ├── tanchjim.py      # Tanchjim Fission/Bunny/One DSP handler
            ├── qudelix.py       # Qudelix 5K handler
            └── moondrop.py      # Moondrop FreeDSP/Rays/Marigold/MAY DSP handler
```

**Handler Pattern:**
- Each device handler implements: `read_peq()`, `write_peq()`, `set_pregain()`
- Handlers define device capabilities (max filters, supported types, gain/Q/freq ranges)
- Registry auto-discovers connected USB HID devices and matches them to handlers

### MCP Server Ecosystem

Three interconnected MCP servers provide a complete EQ workflow:

```
┌─────────────────┐
│  squiglink-mcp  │  Fetch IEM frequency response measurements
│  (server.py)    │  Sources: Crinacle, Super Review, manufacturer databases
└────────┬────────┘
         │ FR data [{freq, db}, ...]
         ▼
┌─────────────────┐
│   autoeq-mcp    │  Compute optimal PEQ filters to match target curves
│  (server.py)    │  Uses scipy optimization, supports Harman IE 2019, etc.
│  optimizer.py   │
└────────┬────────┘
         │ {pregain, filters}
         ▼
┌─────────────────┐
│   dac-eq-mcp    │  Write PEQ to connected DSP device
│  (server.py)    │  Wraps dsp_devices package as MCP tools
└─────────────────┘
```

**MCP Configuration:** `.mcp.json` in project root
- All 3 servers use unified Python virtual environment in `venv/`
- Servers are project-scoped (only available when working in `dac-eq/` directory)

---

## Development Setup

### Prerequisites

**Installation via `install.sh` (recommended):**
```bash
./install.sh
```
This automatically sets up the unified virtual environment with all dependencies.

**Manual setup (advanced):**
```bash
# Create unified virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -r requirements-all.txt

# Verify device detection
python3 dac-eq.py --list
```

### Project Structure

```
dac-eq/
├── dac-eq.py                 # CLI entry point
├── requirements.txt          # Python dependencies
├── .mcp.json                 # MCP server configuration
│
├── dsp_devices/              # Device control library
│   ├── __init__.py
│   ├── base.py               # Core data structures
│   ├── registry.py           # Device discovery
│   └── handlers/             # Device-specific implementations
│       ├── tanchjim.py       # Tanchjim devices
│       ├── qudelix.py        # Qudelix 5K
│       └── moondrop.py       # Moondrop DSP devices
│
├── mcp/                      # MCP servers
│   ├── dac-eq-mcp/           # DSP device control
│   │   └── server.py
│   ├── squiglink-mcp/        # IEM FR data
│   │   └── server.py
│   └── autoeq-mcp/           # EQ optimization
│       ├── server.py
│       └── optimizer.py
│
├── eq/                       # Stored EQ profiles (JSON)
│   ├── tanchjim-fission/
│   ├── qudelix-5k/
│   └── moondrop/
│
├── .claude/skills/           # Claude Code skills
│   └── eq-advisor/           # Structured EQ adjustment workflow
│       └── SKILL.md
│
└── claude-self-dialog/       # Development notes and documentation
    ├── MULTI_DEVICE_GUIDE.md
    ├── QUDELIX_STATUS.md
    └── ...
```

---

## CLI Usage

### Basic Commands

```bash
# Read current PEQ settings from device
python3 dac-eq.py --read

# Write PEQ from JSON profile
python3 dac-eq.py --json eq/tanchjim-fission/example_eq.json

# Write AutoEQ txt file (legacy format)
python3 dac-eq.py --write eq_profile.txt

# Set pregain only (no filter changes)
python3 dac-eq.py --pregain -6

# List all connected devices
python3 dac-eq.py --list

# Select specific device by ID
python3 dac-eq.py --device 0 --json profile.json

# Debug mode (show raw HID data)
python3 dac-eq.py --debug
```

### Multi-Device Workflows

When multiple DSP devices are connected:
1. Run `--list` to see device IDs
2. Use `--device <ID>` to target specific device
3. Device IDs are 0-based indices

---

## PEQ Profile Format

**Primary format: JSON** (stored in `eq/` directory)

```json
{
  "name": "Example EQ Profile",
  "pregain": -3.0,
  "filters": [
    {"freq": 100, "gain": -2.5, "q": 1.41, "type": "PK"},
    {"freq": 1000, "gain": 3.0, "q": 0.7, "type": "LSQ"},
    {"freq": 8000, "gain": -1.5, "q": 2.0, "type": "HSQ"}
  ]
}
```

**Filter types:**
- `PK` - Peaking filter (bell curve)
- `LSQ` - Low shelf
- `HSQ` - High shelf

**Naming convention:**
- Store profiles in `eq/<device-name>/` subdirectories
- Use descriptive names: `harman_target.json`, `bass_boost.json`, etc.

**Legacy AutoEQ txt format:**
- CLI supports reading AutoEQ txt files with `--write`
- If you have txt files, convert to JSON and save to `eq/` directory
- MCP workflow uses JSON exclusively

---

## MCP Workflow

### Complete Auto-EQ Pipeline

The 3 MCP servers work together seamlessly:

```python
# 1. Search for IEM and get FR data
mcp__squiglink__search_iems(query="Blessing 3")
mcp__squiglink__get_fr_data(database="crinacle", file="Moondrop_Blessing_3")
# Returns: [{freq: 20, db: 105.3}, {freq: 21, db: 106.1}, ...]

# 2. Compute optimal EQ to match target
mcp__autoeq__compute_peq(
    fr_data=<from step 1>,
    target="harman_ie_2019",
    constraints={"max_filters": 5}
)
# Returns: {pregain: -3.2, filters: [{freq: 100, gain: 2.5, q: 1.41, type: "PK"}, ...]}

# 3. Write to device
mcp__dac_eq__write_peq(
    filters=<from step 2>,
    pregain=-3.2
)
```

### MCP Tools Reference

**squiglink-mcp:**
- `search_iems(query)` - Search by brand/model name
- `get_fr_data(database, file)` - Fetch measurement data
- `list_databases()` - Show available databases
- `list_cached()` - Show locally cached measurements

**autoeq-mcp:**
- `compute_peq(fr_data, target, constraints)` - Generate optimal filters
- `compute_peq_from_fr(fr_data_measured, fr_data_target, constraints)` - Compute filters to match arbitrary FR curve. **IMPORTANT: Use complete FR datasets (all measurement points) for best optimization - sparse sampling loses critical information**
- `apply_peq_to_fr(fr_data, filters, pregain)` - Apply PEQ filters to FR data and return resulting curve
- `interpolate_fr(fr_data, target_points)` - Smooth/interpolate FR data
- `compare_fr_curves(fr_data1, fr_data2)` - Compare two FR curves with statistics
- `list_targets()` - Show available target curves
- `export_target(name)` - Export target as FR data
- `export_peq(pregain, filters)` - Export as JSON

**dac-eq-mcp:**
- `list_devices()` - List connected DSP devices
- `get_device_capabilities(device_id)` - Get device specs
- `read_peq(device_id?)` - Read current settings (if supported)
- `write_peq(filters, pregain?, device_id?)` - Write EQ to device
- `set_pregain(pregain, device_id?)` - Set pregain only
- `load_preset(preset_index, group?, device_id?)` - Load preset from Qudelix device storage *(Qudelix only)*
- `save_preset(preset_index, group?, device_id?)` - Save current EQ to Qudelix preset slot *(Qudelix only)*
- `set_eq_mode(mode, device_id?)` - Switch Qudelix EQ mode (usr_spk/b20) *(Qudelix only)*
- `get_preset_name(preset_index, device_id?)` - Get Qudelix preset name *(Qudelix only)*
- `set_preset_name(preset_index, name, device_id?)` - Set Qudelix preset name *(Qudelix only)*

**Auto-selection:** If only one device is connected, `device_id` parameter is optional.

---

## Supported Devices

### Currently Implemented

| Device | Handler | Read | Write | Max Filters | Notes |
|--------|---------|------|-------|-------------|-------|
| Tanchjim Fission | `tanchjim.py` | ✓ | ✓ | 5 | Fully supported |
| Tanchjim Bunny DSP | `tanchjim.py` | ✓ | ✓ | 5 | Fully supported |
| Tanchjim One DSP | `tanchjim.py` | ✓ | ✓ | 5 | Fully supported |
| Qudelix 5K | `qudelix.py` | ✓ | ✓ | 10 | V3 protocol, USR EQ group (see below) |
| Moondrop FreeDSP Pro | `moondrop.py` | ✓ | ✓ | 8 | DSP cable, Conexant protocol |
| Moondrop FreeDSP Mini | `moondrop.py` | ✓ | ✓ | 8 | DSP cable, Conexant protocol |
| Moondrop Rays | `moondrop.py` | ✓ | ✓ | 8 | Gaming IEM with DSP |
| Moondrop Marigold | `moondrop.py` | ✓ | ✓ | 8 | IEM with DSP |
| Moondrop MAY DSP | `moondrop.py` | ✓ | ✓ | 8 | IEM with DSP |
| ddHiFi DSP IEM - Memory | `moondrop.py` | ✓ | ✓ | 8 | Uses Moondrop protocol |

**Vendor IDs:**
- Tanchjim: `0x31B2`
- Qudelix: `0x0A12` (CSR/Qualcomm)
- Moondrop: `0x3302`, `0x0762`, `0x35D8`, `0x2FC6`, `0x0104`, `0xB445`, `0x0661`, `0x0666`, `0x0D8C` (WalkPlay/Conexant ecosystem)

### Qudelix 5K Notes

The Qudelix 5K has three independent EQ groups:
- **USR** (default): 10 bands, mono - user preference EQ
- **SPK**: 10 bands, stereo - speaker/IEM correction
- **B20**: 20 bands - extended parametric EQ

The handler defaults to USR EQ. Protocol uses V3 format (Q×1024, group-based commands).
Band params are bit-packed as 32-bit LE: `[rsv:4][Q:14][gain:10][filter:4]`

### Qudelix Preset Management

The Qudelix 5K has **on-device preset storage** with 20 custom slots per EQ group:

**Preset Index Ranges:**
- `0` - Flat (default)
- `1-21` - Factory presets (Acoustic, Bass Booster, Classical, etc.)
- `22-41` - Custom user presets (editable, 20 slots per group)
- `42-52` - QxOver target curves (Harman IE 2019, Diffuse Field, etc.) - SPK group only
- `53-58` - T71 device-specific presets

**Handler Methods:**
```python
# Load preset from device storage
handler.load_preset(group="USR", preset_index=22)

# Save current settings to preset slot
handler.save_preset(group="USR", preset_index=22)

# Switch EQ mode
handler.set_eq_mode(mode="usr_spk")  # or "b20"

# Preset naming
name = handler.get_preset_name(preset_index=22)
handler.set_preset_name(preset_index=22, name="Bass Boost")
```

**MCP Tools:**
```python
# Load/save presets
mcp__dac_eq__load_preset(group="USR", preset_index=22)
mcp__dac_eq__save_preset(group="USR", preset_index=22)

# Mode switching
mcp__dac_eq__set_eq_mode(mode="usr_spk")

# Preset naming
mcp__dac_eq__get_preset_name(preset_index=22)
mcp__dac_eq__set_preset_name(preset_index=22, name="My EQ")
```

**EQ Modes:**
- `usr_spk`: USR and SPK groups active simultaneously
- `b20`: B20 group active (20-band or 10×2 stereo)

**Typical Workflow:**
1. Write EQ profile using `write_peq()`
2. Save to device slot using `save_preset(group, slot)`
3. Optionally set a name using `set_preset_name(slot, name)`
4. Later, load from slot using `load_preset(group, slot)`

**Note:** Direct `read_peq()`/`write_peq()` remain the primary interface for consistency with other handlers. Preset operations are optional advanced features.

### Moondrop DSP Notes

Moondrop DSP devices use the modern Conexant-based protocol:
- **Packet size:** 63 bytes (write), 64 bytes (read response)
- **Biquad encoding:** 5 coefficients × 32-bit signed integers, scaled by 2^30
- **Sample rate:** 96 kHz (assumed for biquad calculation)
- **Value scaling:** 256x for gain/Q/pregain (different from Tanchjim's 10x/1000x)
- **Filter types:** PK=2, LSQ=1, HSQ=3 (different codes than Tanchjim!)
- **Write sequence:** Write coefficient packet → Enable packet → Save to flash

**Protocol commands:**
- `0x80` - READ
- `0x01` - WRITE
- `0x09` - UPDATE_EQ (sub-command for filter write)
- `0x0A` - UPDATE_EQ_COEFF_TO_REG (enable filter)
- `0x23` - PRE_GAIN
- `0x03` - SET_DAC_OFFSET (read pregain)

**Device detection:** Multiple vendor IDs due to WalkPlay/Conexant chipset manufacturers. Handler matches by vendor ID + product name keywords (MOONDROP, RAYS, MARIGOLD, FREEDSP, etc.).

**Test fixtures:** Located in `eq/moondrop/` including flat_eq.json, bass_boost.json, treble_adjust.json, comprehensive_test.json

### Adding New Devices

To add support for a new device:

1. **Create handler** in `dsp_devices/handlers/<device>.py`:
   ```python
   from ..base import BaseDeviceHandler, DeviceCapabilities, PEQProfile

   class MyDeviceHandler(BaseDeviceHandler):
       name = "MyDevice Model"

       @property
       def capabilities(self) -> DeviceCapabilities:
           return DeviceCapabilities(
               max_filters=10,
               supports_read=True,
               supports_write=True,
               supported_filter_types={"PK", "LSQ", "HSQ"},
               gain_range=(-12.0, 12.0),
               q_range=(0.5, 10.0),
               freq_range=(20, 20000)
           )

       def read_peq(self, device) -> PEQProfile:
           # Implement HID read logic
           pass

       def write_peq(self, device, profile: PEQProfile) -> None:
           # Implement HID write logic
           pass
   ```

2. **Register handler** in `dsp_devices/handlers/__init__.py`:
   ```python
   from .mydevice import MyDeviceHandler

   HANDLERS = [
       TanchijimHandler,
       QudelixHandler,
       MyDeviceHandler,  # Add here
   ]
   ```

3. **Test detection**:
   ```bash
   python3 dac-eq.py --list --debug
   ```

---

## HID Protocol Notes

### Command Structure

**Common commands:**
- `0x52` - READ (read current settings)
- `0x57` - WRITE (write filter data)
- `0x53` - SAVE/COMMIT (persist to device memory)
- `0x43` - CLEAR (reset filters)

**Report format:**
- Report ID: `0x4B`
- Packet size: 64 bytes
- Multi-packet transactions for reading/writing multiple filters

**Encoding:**
- Frequency: 16-bit unsigned integer (Hz)
- Gain: 16-bit signed integer (dB * 10, e.g., -25 = -2.5dB)
- Q factor: 16-bit unsigned integer (Q * 1000, e.g., 1410 = 1.41)
- Filter type: Single byte (`0x00` = PK, `0x01` = LSQ, `0x02` = HSQ)

**Timing:**
- COMMIT command requires ~1 second wait for device to save settings
- Use time.sleep(1.0) after COMMIT before disconnecting

---

## Skills

### eq-advisor

Located in `.claude/skills/eq-advisor/SKILL.md`

**Purpose:** Structured reasoning framework for IEM EQ adjustments

**When to use:**
- User wants to adjust sound presentation
- User asks to tune their IEMs
- User wants to achieve specific sound signature

**Workflow:**
1. Identify the IEM model
2. Fetch stock frequency response
3. Classify user intent (setting-based, mood-based, technical, relative)
4. Determine if adjustment is relative to current state or absolute target
5. Use MCP tools to compute and apply EQ

**IMPORTANT:** ALWAYS invoke the `eq-advisor` skill FIRST before using dac-eq MCP tools directly when the user wants to adjust sound.

---

## Testing and Debugging

### Debug Mode

```bash
python3 dac-eq.py --debug --list
```

Shows:
- Raw HID enumeration data
- Device matching logic
- Handler selection process
- Packet payloads (hex dumps)

### Testing MCP Servers

MCP servers run as stdio processes. To test manually:

```bash
# Test dac-eq-mcp
cd mcp/dac-eq-mcp
python server.py

# Send JSON-RPC request (stdin)
{"jsonrpc": "2.0", "method": "tools/list", "id": 1}
```

**Note:** MCP servers are designed for Claude Code integration, not direct CLI use.

### Common Issues

**Device not detected:**
- Ensure device is plugged in via USB
- Check `python3 dac-eq.py --list --debug` for HID enumeration
- Verify device VID/PID matches handler definition

**"No preset data received":**
- Qudelix may need a brief delay between operations
- Try running the command again after 1 second

**MCP server not available:**
- Ensure you're in the `dac-eq/` directory (project-scoped servers)
- Check `.mcp.json` has correct Python paths
- Restart Claude Code if servers were just added

---

## Development Guidelines

### Code Style

**Follow existing patterns:**
- Handler classes extend `BaseDeviceHandler`
- Use dataclasses for structured data (`PEQProfile`, `FilterDefinition`)
- Type hints for all function signatures

**HID communication:**
- Always use try/except for device.write() and device.read()
- Add time.sleep() after COMMIT commands
- Log raw packets in debug mode

### Adding Features

**Before implementing:**
1. Check `claude-self-dialog/` for existing design notes
2. Review `MULTI_DEVICE_GUIDE.md` for device architecture
3. Test with real hardware if possible

**When modifying handlers:**
- Update device capabilities if changing supported features
- Test read/write round-trip to verify encoding
- Add example profile to `eq/<device>/` directory

### Documentation

**Update when:**
- Adding new device support (update Supported Devices section)
- Adding MCP tools (update MCP Tools Reference)
- Changing CLI arguments (update CLI Usage)

---

## Known Limitations

- **macOS only** (uses hidapi, not tested on Windows/Linux)
- **USB HID only** (no Bluetooth support)
- **Qudelix defaults to USR EQ** (SPK and B20 groups accessible via handler API)
- **No GUI** (CLI and MCP only)

---

## File Naming Conventions

**EQ profiles:**
- `eq/<device-name>/<descriptive-name>.json`
- Use lowercase with underscores: `harman_target.json`, `v_shaped.json`

**Documentation:**
- Claude development notes go in `claude-self-dialog/` (not shown to users)
- User-facing docs are README files or inline comments

**Handler files:**
- `dsp_devices/handlers/<manufacturer>.py`
- One file per manufacturer, handle multiple models in same class if protocol is shared

---

## Quick Reference

### Common Workflows

**Apply stored profile:**
```bash
python3 dac-eq.py --json eq/tanchjim-fission/harman_target.json
```

**Read current settings:**
```bash
python3 dac-eq.py --read
```

**Auto-EQ for specific IEM:**
```
1. Invoke /eq-advisor skill
2. Follow structured reasoning process
3. MCP tools handle the rest
```

**Create new profile:**
```json
{
  "name": "My Custom EQ",
  "pregain": -3,
  "filters": [
    {"freq": 100, "gain": 2, "q": 1.0, "type": "LSQ"}
  ]
}
```

### Environment

**All Components (unified environment):**
- Python: 3.11 (in `venv/`)
- HID library: hidapi>=0.14.0
- MCP: mcp>=1.0.0
- Optimization: scipy>=1.11.0 (for autoeq-mcp, autoeq, squiglink)
- HTTP: httpx (for squiglink-mcp API calls)

All packages installed once in unified `venv/lib/python3.11/site-packages/`

### Support

- Check `claude-self-dialog/` for implementation notes
- Tanchjim protocol is well-documented in `tanchjim.py` handler
