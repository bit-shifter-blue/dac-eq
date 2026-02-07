# DAC-EQ

Control Parametric EQ (PEQ) on USB DSP/DAC devices via command-line interface and Claude Code integration.

## What is DAC-EQ?

DAC-EQ is a tool that lets you adjust the sound of your IEMs (In-Ear Monitors) by controlling the built-in equalizer in supported USB DAC devices. You can apply professional tuning profiles, auto-generate EQ settings based on measurements, or create custom sound signatures.

**Key features:**
- Read and write PEQ settings to DSP devices (Tanchjim, Qudelix, Moondrop, etc.)
- Apply EQ profiles stored as JSON files
- Auto-generate optimal EQ from IEM frequency response measurements
- Integrate with Claude Code for conversational EQ adjustment

**Based on:** devicePEQ by Pragmatic Audio (jeromeof)

## Security & Trust

Before installing, review [SECURITY.md](SECURITY.md) to understand:
- What gets installed and what changes on your system
- Security considerations and USB device access
- How to report security issues

## Requirements

- **Operating System:** macOS (required for USB HID device access)
- **Python:** 3.11 or higher
- **Claude Code:** For MCP server integration (requires Claude Pro subscription)
- **Hardware:** Supported DSP/DAC device connected via USB

## Supported Devices

| Device | Read | Write | Max Filters | Notes |
|--------|------|-------|-------------|-------|
| Tanchjim Fission | ✓ | ✓ | 5 | Fully supported |
| Tanchjim Bunny DSP | ✓ | ✓ | 5 | Fully supported |
| Tanchjim One DSP | ✓ | ✓ | 5 | Fully supported |
| Qudelix 5K | ✓ | ✓ | 10 | USR EQ group (user preference EQ) |
| Moondrop FreeDSP Pro | ✓ | ✓ | 8 | DSP cable (0.78mm 2-pin) |
| Moondrop FreeDSP Mini | ✓ | ✓ | 8 | DSP cable (0.78mm 2-pin) |
| Moondrop Rays | ✓ | ✓ | 8 | Gaming IEM with built-in DSP |
| Moondrop Marigold | ✓ | ✓ | 8 | IEM with built-in DSP |
| Moondrop MAY DSP | ✓ | ✓ | 8 | IEM with built-in DSP |
| ddHiFi DSP IEM - Memory | ✓ | ✓ | 8 | Uses Moondrop protocol |

More devices may work but are untested. The tool auto-detects connected devices.

## Installation

### Step 1: Download

```bash
git clone https://github.com/bit-shifter-blue/dac-eq.git
cd dac-eq
```

### Step 2: Run Install Script

```bash
chmod +x install.sh
./install.sh
```

The install script will:
- Check prerequisites (macOS, Python 3.11+)
- Create a virtual environment with all dependencies
- Configure MCP servers for Claude Code
- Test the installation

**Installation size:** ~450 MB (most of it is scipy for EQ optimization)

### Step 3: Verify Installation

After installation completes, test that your device is detected:

```bash
source venv/bin/activate
python dac-eq.py --list
```

You should see your connected DSP device listed.

## Usage

### With Claude Code (Recommended)

Claude Code provides a conversational interface for EQ adjustments.

**Start Claude Code in the dac-eq directory:**

```bash
cd /path/to/dac-eq
claude
```

Claude Code will auto-detect the project-scoped MCP servers. You'll be prompted to approve them on first use.

**Example commands:**

- "Search for Moondrop Blessing 3 measurements"
- "Apply Harman IE 2019 target to my IEMs"
- "/eq-advisor" - Start guided EQ workflow (recommended for beginners)
- "Show me the frequency response of my current EQ"
- "Boost bass by 3dB below 200Hz"
- "Read my current PEQ settings"

**Available MCP servers:**
- **dac-eq:** Read/write PEQ settings to device
- **squiglink:** Fetch IEM frequency response measurements
- **autoeq:** Compute optimal EQ filters to match target curves

**Available skills:**
- **/eq-advisor:** Structured reasoning framework for IEM EQ adjustments (guides you through the process)

### CLI Usage (Advanced)

For direct command-line control:

```bash
# Activate virtual environment
source venv/bin/activate

# Read current PEQ settings
python dac-eq.py --read

# Apply stored EQ profile
python dac-eq.py --json eq/tanchjim-fission/harman_target.json

# Set pregain only (no filter changes)
python dac-eq.py --pregain -6

# List all connected devices
python dac-eq.py --list

# Select specific device (if multiple connected)
python dac-eq.py --device 0 --json profile.json

# Debug mode (show raw HID communication)
python dac-eq.py --debug
```

## EQ Profile Format

EQ profiles are stored as JSON files in the `eq/` directory.

**Example profile:**

```json
{
  "name": "Harman IE 2019 Target",
  "pregain": -3.2,
  "filters": [
    {"freq": 100, "gain": 2.5, "q": 1.41, "type": "PK"},
    {"freq": 1000, "gain": -1.5, "q": 0.7, "type": "LSQ"},
    {"freq": 8000, "gain": 3.0, "q": 2.0, "type": "HSQ"}
  ]
}
```

**Filter types:**
- `PK` - Peaking filter (bell curve)
- `LSQ` - Low shelf (affects frequencies below center)
- `HSQ` - High shelf (affects frequencies above center)

**Creating custom profiles:**

1. Create a JSON file in `eq/` directory
2. Define pregain (negative values reduce overall volume to prevent clipping)
3. Add filters with frequency (Hz), gain (dB), Q factor, and type
4. Apply with: `python dac-eq.py --json eq/my_profile.json`

## Uninstalling

### Remove Virtual Environment and MCP Config

```bash
./uninstall.sh
```

### Fully Remove DAC-EQ

```bash
cd ..
rm -rf dac-eq
```

## What Gets Installed

**Virtual environment (`venv/`):**
- Python interpreter (isolated from system Python)
- Dependencies: hidapi, mcp, scipy, numpy, httpx (~450 MB total)

**MCP configuration (`.mcp.json`):**
- References to MCP server scripts
- Absolute paths to Python interpreter in venv
- Auto-detected by Claude Code when in dac-eq directory

**Source code:**
- CLI tool: `dac-eq.py`
- Device handlers: `dsp_devices/`
- MCP servers: `mcp/dac-eq-mcp/`, `mcp/squiglink-mcp/`, `mcp/autoeq-mcp/`
- Target curves: `mcp/autoeq-mcp/targets/`
- Example profiles: `eq/`

**Nothing is installed system-wide.** All files stay in the dac-eq directory.

## Troubleshooting

### Device not detected

**Check USB connection:**
```bash
python dac-eq.py --list --debug
```

If your device doesn't appear:
- Ensure it's connected via USB (not Bluetooth)
- Try a different USB port or cable
- Check if macOS shows the device in System Information > USB

### Python version error

**Install Python 3.11:**
```bash
brew install python@3.11
```

Then run `./install.sh` again.

### "No preset data received" error

Some devices (like Qudelix 5K) may need a brief delay between operations. Try running the command again.

### MCP servers not appearing in Claude Code

**Ensure you're in the dac-eq directory:**
```bash
cd /path/to/dac-eq
claude
```

MCP servers are project-scoped and only available when Claude Code is running in the dac-eq directory.

**Reset project-specific server approvals (if needed):**
```bash
claude mcp reset-project-choices
```

### Permission denied errors

**Make scripts executable:**
```bash
chmod +x install.sh uninstall.sh
```

### Virtual environment activation fails

**Manual activation:**
```bash
source /path/to/dac-eq/venv/bin/activate
```

If this fails, the venv may be corrupted. Run `./uninstall.sh` then `./install.sh` to recreate it.

## How It Works

### Device Communication

DAC-EQ uses the USB HID protocol to communicate with DSP devices:

1. **Device detection:** Scans USB HID devices for known vendor IDs
2. **Handler selection:** Matches device to appropriate protocol handler
3. **HID commands:** Sends READ/WRITE/COMMIT commands with encoded PEQ data
4. **Protocol encoding:** Converts frequency/gain/Q to device-specific binary format

### MCP Server Workflow

The three MCP servers work together for auto-EQ:

```
1. squiglink → fetch IEM frequency response measurements
2. autoeq → compute optimal PEQ filters to match target
3. dac-eq → write filters to device
```

**Example flow:**
```
User: "Apply Harman IE 2019 to my Blessing 3"
  ↓
squiglink: Search for "Blessing 3" → get FR data
  ↓
autoeq: Compute optimal filters (FR data + Harman target)
  ↓
dac-eq: Write filters to connected device
```

### Why Unified Virtual Environment?

Instead of separate virtual environments for each MCP server (~443 MB with duplicates), we use a single unified `venv/` (~450 MB) where all packages are installed once. All MCP servers use the same Python interpreter and shared dependencies.

**Benefits:**
- Saves ~350 MB of disk space
- Faster installation (packages downloaded once)
- Consistent package versions across all servers
- Simpler for beginners (one `pip install` command)

## Advanced Topics

### Multi-Device Setups

If you have multiple DSP devices connected:

```bash
# List devices with IDs
python dac-eq.py --list

# Target specific device (0-based index)
python dac-eq.py --device 0 --json profile.json
python dac-eq.py --device 1 --json profile.json
```

### Converting AutoEQ Text Files

If you have AutoEQ text files (legacy format), Claude Code can convert them to JSON:

```
"Convert eq_profile.txt to JSON and save to eq/my_profile.json"
```

The MCP workflow uses JSON exclusively.

### Manual MCP Configuration

If you need to configure MCP servers manually, see `.mcp.json.template` for the expected structure. The install script auto-generates `.mcp.json` with correct absolute paths.

### Development Mode

To modify the code and test changes:

```bash
source venv/bin/activate
python dac-eq.py --debug  # Shows HID communication
```

No rebuild needed - Python runs directly from source.

## Contributing

DAC-EQ is based on devicePEQ by Pragmatic Audio (jeromeof).

To report issues or request device support, please include:
- Device name and model
- Output of `python dac-eq.py --list --debug`
- macOS version
- Python version

## License

ISC License - see [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

- **devicePEQ** by Pragmatic Audio (jeromeof) - Original HID protocol implementation
- **squig.link** - IEM frequency response database
- **AutoEQ** - EQ optimization methodology
