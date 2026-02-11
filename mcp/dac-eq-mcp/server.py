#!/usr/bin/env python3
"""
DAC-EQ MCP Server: Universal DSP/DAC Parametric EQ Control

Supports multiple devices: Tanchjim, Qudelix, Moondrop, and more
Exposes PEQ control functionality as MCP tools using stdio transport.
Part of the DAC-EQ project.
"""
import json
import sys
import os
from typing import Any, Callable

# Add project root to path for dsp_devices import
# server.py is at mcp/dac-eq-mcp/server.py, so go up 3 levels to dac-eq/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from dsp_devices import DeviceRegistry, PEQProfile, FilterDefinition, DeviceError, ProfileValidationError
except ImportError:
    DeviceRegistry = None

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create the MCP server
server = Server("dac-eq")


def _with_device(device_id, callback: Callable, debug: bool = False) -> list[TextContent]:
    """Connect to a device, run callback, disconnect, and handle errors.

    Args:
        device_id: Device index (0-based) or None for auto-select
        callback: Function(handler, device_info) -> result dict
        debug: Enable debug output

    Returns:
        list[TextContent] with JSON result or error message
    """
    if not DeviceRegistry:
        return [TextContent(type="text", text="Error: dsp_devices package not found.")]

    try:
        registry = DeviceRegistry(debug=debug)
        registry.discover_devices()
        device_info = registry.select_device(device_id)
        handler = registry.connect_device(device_id)

        try:
            result = callback(handler, device_info)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        finally:
            handler.disconnect()

    except ProfileValidationError as e:
        return [TextContent(type="text", text=f"Validation error: {str(e)}")]
    except DeviceError as e:
        return [TextContent(type="text", text=f"Device error: {str(e)}")]
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="list_devices",
            description="List all connected DSP devices (Tanchjim, Qudelix, Moondrop, etc.) with their capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_device_capabilities",
            description="Get detailed capabilities of a specific DSP device (max filters, supported types, ranges)",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Device ID (0-based index from list_devices)"
                    }
                },
                "required": ["device_id"]
            }
        ),
        Tool(
            name="read_peq",
            description="Read current PEQ settings (pregain and filters) from a DSP device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID (0-based index). If not specified, auto-selects if only one device connected."
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="write_peq",
            description="Write PEQ settings (filters and optional pregain) to a DSP device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID (0-based index). If not specified, auto-selects if only one device connected."
                    },
                    "filters": {
                        "type": "array",
                        "description": "Array of filter objects. Each filter has: freq (Hz), gain (dB), q (Q factor), type (PK/LSQ/HSQ/LPF/HPF). Max filters depends on device.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number", "description": "Frequency in Hz"},
                                "gain": {"type": "number", "description": "Gain in dB"},
                                "q": {"type": "number", "description": "Q factor"},
                                "type": {"type": "string", "enum": ["PK", "LSQ", "HSQ", "LPF", "HPF"], "description": "Filter type"}
                            },
                            "required": ["freq", "gain", "q", "type"]
                        }
                    },
                    "pregain": {
                        "type": "number",
                        "description": "Optional pregain in dB"
                    }
                },
                "required": ["filters"]
            }
        ),
        Tool(
            name="set_pregain",
            description="Set only the pregain value on a DSP device (without modifying filters). Note: For devices that don't support read (like Qudelix), this will write pregain with no filter changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID (0-based index). If not specified, auto-selects if only one device connected."
                    },
                    "pregain": {
                        "type": "number",
                        "description": "Pregain value in dB"
                    }
                },
                "required": ["pregain"]
            }
        ),
        Tool(
            name="diagnose",
            description="Run HID diagnostics on a device. Sends a simple command and captures raw responses to debug communication issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "integer",
                        "description": "Optional device ID (0-based index). If not specified, auto-selects if only one device connected."
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls"""

    if name == "list_devices":
        if not DeviceRegistry:
            return [TextContent(
                type="text",
                text="Error: dsp_devices package not found. Make sure dependencies are installed."
            )]

        try:
            registry = DeviceRegistry(debug=False)
            devices = registry.discover_devices()

            if not devices:
                return [TextContent(
                    type="text",
                    text="No DSP devices found. Connect a device and try again."
                )]

            result = {"devices": []}
            for d in devices:
                caps = d['handler'].capabilities
                result["devices"].append({
                    "id": d['id'],
                    "product": d['product_string'],
                    "handler": d['handler'].name,
                    "vendor_id": f"0x{d['vendor_id']:04X}",
                    "product_id": f"0x{d['product_id']:04X}",
                    "max_filters": caps.max_filters,
                    "supported_types": sorted(list(caps.supported_filter_types)),
                    "supports_read": caps.supports_read,
                    "supports_write": caps.supports_write
                })

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "get_device_capabilities":
        if not DeviceRegistry:
            return [TextContent(
                type="text",
                text="Error: dsp_devices package not found."
            )]

        device_id = arguments.get("device_id")
        if device_id is None:
            return [TextContent(type="text", text="Error: device_id is required")]

        try:
            registry = DeviceRegistry(debug=False)
            registry.discover_devices()
            device_info = registry.get_device_info(device_id)

            caps = device_info['capabilities']
            result = {
                "device": device_info['product_string'],
                "handler": device_info['handler'].name,
                "capabilities": {
                    "max_filters": caps.max_filters,
                    "gain_range": {"min": caps.gain_range[0], "max": caps.gain_range[1]},
                    "pregain_range": {"min": caps.pregain_range[0], "max": caps.pregain_range[1]},
                    "freq_range": {"min": caps.freq_range[0], "max": caps.freq_range[1]},
                    "q_range": {"min": caps.q_range[0], "max": caps.q_range[1]},
                    "supported_filter_types": sorted(list(caps.supported_filter_types)),
                    "supports_read": caps.supports_read,
                    "supports_write": caps.supports_write
                }
            }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "read_peq":
        device_id = arguments.get("device_id")

        def _read(handler, device_info):
            profile = handler.read_peq()

            return {
                "device": device_info['product_string'],
                "handler": handler.name,
                "pregain": profile.pregain,
                "filters": [
                    {
                        "index": i + 1,
                        "freq": f.freq,
                        "gain": f.gain,
                        "q": f.q,
                        "type": f.type
                    }
                    for i, f in enumerate(profile.filters)
                ]
            }

        return _with_device(device_id, _read)

    elif name == "write_peq":
        device_id = arguments.get("device_id")
        filter_data = arguments.get("filters", [])
        pregain = arguments.get("pregain", 0.0)

        if not filter_data:
            return [TextContent(type="text", text="Error: No filters provided")]

        try:
            filters = [
                FilterDefinition(
                    freq=int(f['freq']),
                    gain=float(f['gain']),
                    q=float(f['q']),
                    type=f['type']
                )
                for f in filter_data
            ]
            profile = PEQProfile(filters=filters, pregain=pregain)
        except (KeyError, ValueError) as e:
            return [TextContent(type="text", text=f"Error building profile: {str(e)}")]

        def _write(handler, device_info):
            handler.write_peq(profile)
            return {
                "device": device_info['product_string'],
                "handler": handler.name,
                "status": "success",
                "filters_written": len(filters),
                "pregain": pregain
            }

        return _with_device(device_id, _write)

    elif name == "set_pregain":
        device_id = arguments.get("device_id")
        pregain = arguments.get("pregain")

        if pregain is None:
            return [TextContent(type="text", text="Error: pregain value required")]

        def _set_pregain(handler, device_info):
            # Use set_pregain if available (Tanchjim), otherwise read+write
            if hasattr(handler, 'set_pregain'):
                handler.set_pregain(pregain)
            else:
                try:
                    profile = handler.read_peq()
                    profile.pregain = pregain
                except (NotImplementedError, Exception):
                    profile = PEQProfile(filters=[], pregain=pregain)
                handler.write_peq(profile)

            return {
                "device": device_info['product_string'],
                "handler": handler.name,
                "status": "success",
                "pregain": pregain
            }

        return _with_device(device_id, _set_pregain)

    elif name == "diagnose":
        device_id = arguments.get("device_id")

        def _diagnose(handler, device_info):
            if hasattr(handler, 'diagnose'):
                result = handler.diagnose()
                result['device'] = device_info['product_string']
                return result
            else:
                return {"error": "Handler does not support diagnose()"}

        return _with_device(device_id, _diagnose, debug=True)

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server using stdio transport"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
