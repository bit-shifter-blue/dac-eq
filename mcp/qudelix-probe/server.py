#!/usr/bin/env python3
"""
Qudelix Probe - Debug tool for testing individual HID commands
Temporary scaffolding - delete when debugging complete
"""
import json
import sys
import os
import hid
import time
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("qudelix-probe")

# Device constants
VENDOR_ID = 0x0A12
USAGE_PAGE = 0xFF00
REPORT_ID = 8

# Persistent device connection
_device: Optional[hid.device] = None
_device_info: Optional[dict] = None

def find_qudelix() -> Optional[dict]:
    """Find Qudelix device"""
    for dev in hid.enumerate():
        if dev['vendor_id'] == VENDOR_ID:
            name = dev.get('product_string', '').upper()
            if 'QUDELIX' in name or '5K' in name:
                if dev.get('usage_page') == USAGE_PAGE:
                    return dev
    return None

def send_command(cmd: int, payload: list, report_id: int = REPORT_ID) -> dict:
    """Send a single command and capture response"""
    global _device, _device_info

    # Find device if not already found
    if not _device_info:
        _device_info = find_qudelix()

    if not _device_info:
        return {"error": "Qudelix not found"}

    result = {
        "device": _device_info.get('product_string'),
        "command": f"0x{cmd:04X}",
        "payload": payload,
        "report_id": report_id,
        "packet_hex": "",
        "write_result": None,
        "responses": []
    }

    # Reuse existing device if open, otherwise create new one
    device = None

    try:
        if _device is None:
            device = hid.device()
            device.open(_device_info['vendor_id'], _device_info['product_id'])
            device.set_nonblocking(False)
            _device = device
        else:
            device = _device
            device.set_nonblocking(False)

        # Build packet: [report_id, length, 0x80, cmd_hi, cmd_lo, ...payload]
        cmd_hi = (cmd >> 8) & 0xFF
        cmd_lo = cmd & 0xFF
        cmd_payload = [cmd_hi, cmd_lo] + payload

        packet = [0] * 64
        packet[0] = len(cmd_payload) + 1  # length includes 0x80
        packet[1] = 0x80  # HID command marker
        packet[2:2 + len(cmd_payload)] = cmd_payload

        full_packet = [report_id] + packet
        result["packet_hex"] = ' '.join(f'{b:02X}' for b in full_packet[:16])

        # Send
        write_result = device.write(full_packet)
        result["write_result"] = write_result

        # Wait and read responses
        time.sleep(0.2)
        device.set_nonblocking(True)

        start = time.time()
        while (time.time() - start) < 2.0:
            data = device.read(64)
            if data:
                hex_str = ' '.join(f'{b:02X}' for b in data)
                result["responses"].append(hex_str)
            else:
                if result["responses"]:  # Got some responses, wait a bit more
                    time.sleep(0.1)
                    data = device.read(64)
                    if not data:
                        break
            time.sleep(0.01)

        if not result["responses"]:
            result["responses"] = ["(no response)"]

    except Exception as e:
        result["error"] = str(e)
        # On error, close and reset persistent connection
        if device:
            try:
                device.close()
            except Exception:
                pass
            _device = None

    return result


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="probe_send",
            description="Send a single HID command to Qudelix. Use to test what each command does.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Command code in hex (e.g., '0x0700' for SetEqEnable)"
                    },
                    "payload": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Payload bytes as integers (e.g., [1] to enable)"
                    },
                    "report_id": {
                        "type": "integer",
                        "description": "HID report ID (default 8, can try 7)",
                        "default": 8
                    }
                },
                "required": ["cmd", "payload"]
            }
        ),
        Tool(
            name="probe_status",
            description="Just connect to device and report info, send nothing",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="probe_sequence",
            description="Send multiple commands in sequence with delays between",
            inputSchema={
                "type": "object",
                "properties": {
                    "commands": {
                        "type": "array",
                        "description": "Array of {cmd, payload} objects to send in order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cmd": {"type": "string"},
                                "payload": {"type": "array", "items": {"type": "integer"}}
                            }
                        }
                    },
                    "delay_ms": {
                        "type": "integer",
                        "description": "Delay between commands in ms (default 200)",
                        "default": 200
                    }
                },
                "required": ["commands"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:

    if name == "probe_status":
        dev_info = find_qudelix()
        if not dev_info:
            return [TextContent(type="text", text="Qudelix not found")]

        result = {
            "device": dev_info.get('product_string'),
            "vendor_id": f"0x{dev_info['vendor_id']:04X}",
            "product_id": f"0x{dev_info['product_id']:04X}",
            "usage_page": f"0x{dev_info.get('usage_page', 0):04X}",
            "status": "ready"
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "probe_send":
        cmd_str = arguments.get("cmd", "0x0000")
        cmd = int(cmd_str, 16) if isinstance(cmd_str, str) else cmd_str
        payload = arguments.get("payload", [])
        report_id = arguments.get("report_id", REPORT_ID)

        result = send_command(cmd, payload, report_id)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "probe_sequence":
        commands = arguments.get("commands", [])
        delay_ms = arguments.get("delay_ms", 200)

        results = []
        for i, c in enumerate(commands):
            cmd_str = c.get("cmd", "0x0000")
            cmd = int(cmd_str, 16) if isinstance(cmd_str, str) else cmd_str
            payload = c.get("payload", [])

            result = send_command(cmd, payload)
            result["step"] = i + 1
            results.append(result)

            if i < len(commands) - 1:
                time.sleep(delay_ms / 1000.0)

        return [TextContent(type="text", text=json.dumps(results, indent=2))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    global _device
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Cleanup: close persistent device on exit
        if _device:
            try:
                _device.close()
            except Exception:
                pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
