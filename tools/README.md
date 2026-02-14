# EQ Advisor Tools

Tool definitions and executors for Claude API integration.

## Files

- **`tool_definitions.py`** - Claude API tool schemas (6 tools)
- **`tool_executor.py`** - Tool execution logic
- **`__init__.py`** - Package exports

## Tools (6 total)

### Squiglink (IEM FR Data)
- ✅ `search_iems` - Search for IEM models *(fully implemented)*
- ✅ `get_fr_data` - Fetch frequency response data *(fully implemented)*

### AutoEQ (EQ Computation)
- ✅ `compute_peq` - Compute optimal PEQ filters *(fully working!)*

### DAC-EQ (Device Control)
- ✅ `list_devices` - List connected DSP devices *(fully implemented)*
- ✅ `read_peq` - Read current PEQ from device *(fully implemented)*
- ✅ `write_peq` - Write PEQ to device *(fully implemented)*

## Implementation Status

**Phase 2.0:** ✅ Complete
- ✅ Tool definitions complete
- ✅ DAC-EQ tools fully working (device control)
- ✅ Framework for squiglink/autoeq

**Phase 2.1:** ✅ Complete!
- ✅ Real squiglink integration (fetches from squig.link databases)
- ✅ AutoEQ integration working (uses autoeq library for real optimization)
  - Computes optimal filters to match target curves
  - Supports harman_ie_2019, diffuse_field, and other targets
  - Configurable constraints (max filters, gain range, Q range)

## Usage

```python
from tools import TOOLS, execute_tool

# Get tool definitions for Claude API
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    tools=TOOLS,  # Pass tool definitions
    messages=[...]
)

# Execute tool when Claude requests it
result = execute_tool("list_devices", {})
```

## Testing

```python
# Test device control
from tools import execute_tool

# List devices
print(execute_tool("list_devices", {}))

# Read current EQ (if device connected)
print(execute_tool("read_peq", {}))
```
