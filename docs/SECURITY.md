# Security & Trust

## What You're Installing

DAC EQ is a Python tool that:
- **CLI Tool (eq-advisor.py):** Communicates with USB DSP/DAC devices (Tanchjim, Qudelix, Moondrop) via HID protocol
- **MCP Servers (3 Python processes):**
  - `eq-advisor-mcp`: Wraps CLI functions for Claude Code
  - `squiglink-mcp`: Fetches public IEM frequency response data
  - `autoeq-mcp`: Computes EQ filter settings using scipy

All source code is open on GitHub at: https://github.com/bit-shifter-blue/eq-advisor

## What Changes on Your System

**install.sh does:**
- Creates `eq-advisor/venv/` directory (~300MB, Python dependencies)
- Creates `eq-advisor/.mcp.json` file (MCP server configuration, generated)
- Installs Python packages: hidapi, mcp, scipy, numpy, httpx

**Does NOT modify:**
- System Python or global packages
- Home directory (all changes are within `eq-advisor/` folder)
- System files or permissions
- Your git config (unless you explicitly run `git config`)

**USB/HID Access:**
- The tool requires permission to communicate with USB HID devices
- On macOS, this works automatically via hidapi (no special setup needed)
- No drivers are installed or modified

## Uninstalling

  ./uninstall.sh

**This completely removes:**
- All eq-advisor source code
- Virtual environment (`venv/`)
- MCP configuration (`.mcp.json`)
- EQ profiles (`eq/` folder)
- Everything else in the eq-advisor directory

**The uninstall script will:**
1. Warn you that EQ profiles will be deleted
2. Ask if you've backed them up (gives you a chance to cancel and backup first)
3. Ask for final confirmation
4. Remove the entire eq-advisor directory

**To keep your EQ profiles:** When prompted, cancel the script and run:
```
cp -r eq/ ~/my-backup-location/
```
Then run uninstall again.

## Security Considerations

**Low Risk:**
- Python dependencies are from PyPI (official package repository)
- No system-wide modifications
- All code runs in sandboxed virtual environment
- MCP servers only run when you explicitly use Claude Code

**USB Device Access:**
- The tool can read/write settings on connected USB DSP devices
- Only communicates with devices you explicitly connect
- Protocol is documented in source code (`peq_devices/handlers/`)
- No network access (except squiglink-mcp fetches public IEM data)

**Data:**
- EQ profiles are stored locally in JSON files
- No telemetry or data transmission (except squiglink public API calls)
- Your git config (name/email) is not modified unless you explicitly set it

## Review Before Installing

- Source code: https://github.com/bit-shifter-blue/eq-advisor
- Main entry point: `eq-advisor.py`
- Device handlers: `peq_devices/handlers/`
- MCP servers: `mcp/*/server.py`

## If You Have Security Concerns

- Review the source code on GitHub
- Run `install.sh` with `--help` to see all options (if available)
- Check `python3 eq-advisor.py --help` for CLI options before using
- Examine `eq-advisor/.mcp.json` after install to see what commands Claude Code can access

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Contact the maintainer directly
3. Allow time for a fix before public disclosure

For now, please email or open a private security advisory through GitHub if available.
