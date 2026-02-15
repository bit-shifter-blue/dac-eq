#!/usr/bin/env python3
"""
Tanchjim Probe MCP Server: Low-level protocol testing for Tanchjim DSP devices

Provides raw field read/write tools for protocol debugging and verification.
Based on official Tanchjim protocol (DSPCommand.java).
"""
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from tools.peq_devices import DeviceRegistry
    import hid
except ImportError:
    DeviceRegistry = None
    hid = None

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("tanchjim-probe")


def _connect_tanchjim():
    """Connect to first Tanchjim device found"""
    if not DeviceRegistry:
        raise RuntimeError("dsp_devices package not found")

    registry = DeviceRegistry(debug=False)
    devices = registry.discover_devices()

    # Find Tanchjim device
    tanchjim_device = None
    for dev in devices:
        if dev['handler'].name == "Tanchjim":
            tanchjim_device = dev
            break

    if not tanchjim_device:
        raise RuntimeError("No Tanchjim device found")

    handler = registry.connect_device(tanchjim_device['id'])
    return handler, tanchjim_device


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available probe tools"""
    return [
        Tool(
            name="read_pregain",
            description="Read pregain from device (field 0x65)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="read_filter",
            description="Read a specific filter from device",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_index": {
                        "type": "integer",
                        "description": "Filter index (0-4)"
                    }
                },
                "required": ["filter_index"]
            }
        ),
        Tool(
            name="write_pregain",
            description="Write pregain value. Does not commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pregain": {
                        "type": "number",
                        "description": "Pregain in dB"
                    }
                },
                "required": ["pregain"]
            }
        ),
        Tool(
            name="write_filter",
            description="Write a single filter. Does not commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter_index": {
                        "type": "integer",
                        "description": "Filter index (0-4)"
                    },
                    "freq": {
                        "type": "integer",
                        "description": "Frequency in Hz"
                    },
                    "gain": {
                        "type": "number",
                        "description": "Gain in dB"
                    },
                    "q": {
                        "type": "number",
                        "description": "Q factor"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["PK", "LSQ", "HSQ"],
                        "description": "Filter type"
                    }
                },
                "required": ["filter_index", "freq", "gain", "q", "type"]
            }
        ),
        Tool(
            name="commit",
            description="Send COMMIT command to save changes to flash. Waits 1 second.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="read_full_profile",
            description="Read complete EQ profile (pregain + all 5 filters)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="read_field",
            description="Read raw data from any field ID. Returns raw response bytes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "field_id": {
                        "type": "integer",
                        "description": "Field ID (0x00-0xFF, e.g., 0x65, 0x26)"
                    }
                },
                "required": ["field_id"]
            }
        ),
        Tool(
            name="write_field",
            description="Write raw data to any field ID. Does not commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "field_id": {
                        "type": "integer",
                        "description": "Field ID (0x00-0xFF)"
                    },
                    "data": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Data bytes to write (up to 4 bytes)"
                    }
                },
                "required": ["field_id", "data"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""

    try:
        handler, device_info = _connect_tanchjim()

        try:
            if name == "read_pregain":
                pregain = handler._read_pregain()
                result = {
                    "pregain_db": pregain
                }

            elif name == "read_filter":
                filter_index = arguments["filter_index"]
                filter_def = handler._read_filter(filter_index)
                if filter_def:
                    result = {
                        "filter_index": filter_index,
                        "freq_hz": filter_def.freq,
                        "gain_db": filter_def.gain,
                        "q": filter_def.q,
                        "type": filter_def.type
                    }
                else:
                    result = {
                        "filter_index": filter_index,
                        "status": "empty or bypassed"
                    }

            elif name == "write_pregain":
                pregain = arguments["pregain"]
                handler._write_pregain(pregain)
                result = {
                    "status": "success",
                    "message": f"Wrote pregain {pregain} dB",
                    "note": "Change not committed (call commit to save)"
                }

            elif name == "write_filter":
                from dsp_devices import FilterDefinition
                filter_index = arguments["filter_index"]
                filter_def = FilterDefinition(
                    freq=arguments["freq"],
                    gain=arguments["gain"],
                    q=arguments["q"],
                    type=arguments["type"]
                )
                handler._write_filter(filter_index, filter_def)
                result = {
                    "status": "success",
                    "message": f"Wrote filter {filter_index}",
                    "filter": {
                        "freq_hz": filter_def.freq,
                        "gain_db": filter_def.gain,
                        "q": filter_def.q,
                        "type": filter_def.type
                    },
                    "note": "Change not committed (call commit to save)"
                }

            elif name == "commit":
                handler._commit()
                result = {
                    "status": "success",
                    "message": "COMMIT executed (waited 1s)"
                }

            elif name == "read_full_profile":
                pregain = handler._read_pregain()
                filters = []
                for i in range(5):
                    f = handler._read_filter(i)
                    if f:
                        filters.append({
                            "index": i,
                            "freq_hz": f.freq,
                            "gain_db": f.gain,
                            "q": f.q,
                            "type": f.type
                        })

                result = {
                    "pregain_db": pregain,
                    "filter_count": len(filters),
                    "filters": filters
                }

            elif name == "read_field":
                field_id = arguments["field_id"]
                # Build read packet
                packet = bytes([field_id, 0x00, 0x00, 0x00, 0x52, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                response = handler._send_and_receive(packet)

                if response:
                    result = {
                        "field_id": f"0x{field_id:02X}",
                        "response_hex": " ".join(f"{b:02X}" for b in response[:16]),
                        "response_bytes": list(response[:16]),
                        "byte_7": response[7] if len(response) > 7 else None,
                        "byte_8": response[8] if len(response) > 8 else None,
                        "byte_9": response[9] if len(response) > 9 else None,
                        "byte_10": response[10] if len(response) > 10 else None
                    }
                else:
                    result = {
                        "field_id": f"0x{field_id:02X}",
                        "error": "No response from device"
                    }

            elif name == "write_field":
                field_id = arguments["field_id"]
                data = arguments["data"]

                # Build write packet (pad data to 4 bytes)
                data_bytes = (list(data) + [0x00, 0x00, 0x00, 0x00])[:4]
                packet = bytes([field_id, 0x00, 0x00, 0x00, 0x57, 0x00] + data_bytes + [0x00])

                # Write (fire-and-forget)
                handler.hid_device.write([0x4B] + list(packet))
                import time
                time.sleep(0.02)

                result = {
                    "status": "success",
                    "field_id": f"0x{field_id:02X}",
                    "data_written": data_bytes,
                    "note": "Change not committed (call commit to save)"
                }

            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        finally:
            handler.disconnect()

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
