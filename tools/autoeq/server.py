#!/usr/bin/env python3
"""
MCP Server for AutoEQ PEQ Optimization

Exposes AutoEQ functionality as MCP tools for computing optimal PEQ filters
from frequency response data with device constraints.
"""
import json
import os
import tempfile
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .optimizer import (
    compute_peq,
    list_available_targets,
    export_target,
    export_fr,
    export_peq,
    apply_peq_to_fr,
    compute_peq_from_fr,
    interpolate_fr,
    compare_fr_curves,
    DEFAULT_CONSTRAINTS
)


def _load_fr_from_file(fr_file: str) -> list[dict]:
    """
    Load FR data from file path. FILE-ONLY (no arrays).

    Args:
        fr_file: Path to FR data file (CSV or JSON)

    Returns:
        List of {freq, db} dicts

    Raises:
        ValueError: If file doesn't exist or is invalid
    """
    if not fr_file:
        raise ValueError("fr_file is required (array passing not supported)")

    from pathlib import Path
    file_path = Path(fr_file)
    if not file_path.exists():
        raise ValueError(f"FR file not found: {fr_file}")

    # Support both CSV and JSON formats
    if file_path.suffix == ".csv":
        # Parse CSV format (frequency,raw)
        data = []
        with open(file_path) as f:
            lines = f.readlines()
            for line in lines[1:]:  # Skip header
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    data.append({"freq": float(parts[0]), "db": float(parts[1])})
        return data
    else:
        # JSON format
        with open(file_path) as f:
            return json.load(f)


def _fr_summary(data: list[dict], path: str, label: str = "FR Data") -> str:
    """Compact summary: point count + key freqs + file path."""
    result = f"## {label}\n"
    result += f"Total data points: {len(data)}\n"
    result += f"fr_file: {path}\n\n"

    key_freqs = {}
    target_freqs = [20, 50, 100, 250, 500, 1000, 2000, 4000, 8000, 10000, 12000, 16000]
    for point in data:
        freq = point["freq"]
        for target in target_freqs:
            if target * 0.9 <= freq <= target * 1.1:
                if target not in key_freqs:
                    key_freqs[target] = point["db"]

    if key_freqs:
        result += "### Key Frequencies:\n"
        result += "| Frequency | SPL (dB) |\n"
        result += "|-----------|----------|\n"
        for freq in sorted(key_freqs.keys()):
            result += f"| {freq} Hz | {key_freqs[freq]:.1f} |\n"

    return result


# Create the MCP server
server = Server("autoeq")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="compute_peq",
            description="Compute optimal PEQ filters from FR data file to match a target curve. FILE-ONLY (no data arrays).",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_file": {
                        "type": "string",
                        "description": "Path to FR data file (CSV or JSON). Use the fr_file path from get_fr_data output."
                    },
                    "target": {
                        "type": "string",
                        "description": "Target curve name (e.g., 'harman_ie_2019', 'diffuse_field')"
                    },
                    "constraints": {
                        "type": "object",
                        "description": "Device constraints (optional)",
                        "properties": {
                            "max_filters": {
                                "type": "integer",
                                "description": "Maximum number of filters (default: 5)"
                            },
                            "gain_range": {
                                "type": "array",
                                "description": "Min/max gain in dB (default: [-12, 12])",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 2
                            },
                            "q_range": {
                                "type": "array",
                                "description": "Min/max Q factor (default: [0.5, 10])",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 2
                            },
                            "freq_range": {
                                "type": "array",
                                "description": "Min/max frequency in Hz (default: [20, 20000])",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 2
                            },
                            "filter_types": {
                                "type": "array",
                                "description": "Allowed filter types (default: ['PK', 'LSQ', 'HSQ'])",
                                "items": {"type": "string", "enum": ["PK", "LSQ", "HSQ"]}
                            }
                        }
                    }
                },
                "required": ["fr_file", "target"]
            }
        ),
        Tool(
            name="list_targets",
            description="List available target curves for EQ optimization",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="export_target",
            description="Export a target curve as frequency/dB pairs",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Target curve name (e.g., 'harman_ie_2019')"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="export_fr",
            description="Export FR data as tab-separated text (squig.link format)",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_data": {
                        "type": "array",
                        "description": "Frequency response data as array of {freq, db} objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file": {
                        "type": "string",
                        "description": "Path to FR data JSON file (alternative to fr_data)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="export_peq",
            description="Export PEQ settings as JSON (compatible with eq-advisor write_peq)",
            inputSchema={
                "type": "object",
                "properties": {
                    "pregain": {
                        "type": "number",
                        "description": "Pregain in dB"
                    },
                    "filters": {
                        "type": "array",
                        "description": "Array of filter objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "gain": {"type": "number"},
                                "q": {"type": "number"},
                                "type": {"type": "string", "enum": ["PK", "LSQ", "HSQ"]}
                            },
                            "required": ["freq", "gain", "q"]
                        }
                    }
                },
                "required": ["pregain", "filters"]
            }
        ),
        Tool(
            name="apply_peq_to_fr",
            description="Apply PEQ filters to FR data and return the resulting FR curve",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_data": {
                        "type": "array",
                        "description": "Frequency response data as array of {freq, db} objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number", "description": "Frequency in Hz"},
                                "db": {"type": "number", "description": "SPL in dB"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file": {
                        "type": "string",
                        "description": "Path to FR data JSON file (alternative to fr_data)"
                    },
                    "filters": {
                        "type": "array",
                        "description": "Array of filter objects to apply",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "gain": {"type": "number"},
                                "q": {"type": "number"},
                                "type": {"type": "string", "enum": ["PK", "LSQ", "HSQ"]}
                            },
                            "required": ["freq", "gain", "q", "type"]
                        }
                    },
                    "pregain": {
                        "type": "number",
                        "description": "Pregain in dB (optional, default 0)"
                    }
                },
                "required": ["filters"]
            }
        ),
        Tool(
            name="compute_peq_from_fr",
            description="Compute optimal PEQ filters to match measured FR to target FR. IMPORTANT: Use complete FR datasets (all measurement points) for best optimization results. Sparse sampling loses critical information for accurate filter computation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_data_measured": {
                        "type": "array",
                        "description": "Measured frequency response. Use complete dataset (all points) for accurate optimization - do not sample or approximate.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file_measured": {
                        "type": "string",
                        "description": "Path to measured FR data JSON file (alternative to fr_data_measured)"
                    },
                    "fr_data_target": {
                        "type": "array",
                        "description": "Target frequency response. Use complete dataset (all points) for accurate optimization - do not sample or approximate.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file_target": {
                        "type": "string",
                        "description": "Path to target FR data JSON file (alternative to fr_data_target)"
                    },
                    "constraints": {
                        "type": "object",
                        "description": "Device constraints (optional)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="interpolate_fr",
            description="Interpolate/smooth FR data",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_data": {
                        "type": "array",
                        "description": "Frequency response data",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file": {
                        "type": "string",
                        "description": "Path to FR data JSON file (alternative to fr_data)"
                    },
                    "target_points": {
                        "type": "integer",
                        "description": "Number of interpolation points (optional, default 1000)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="compare_fr_curves",
            description="Compare two FR curves and return statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "fr_data1": {
                        "type": "array",
                        "description": "First FR curve",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file1": {
                        "type": "string",
                        "description": "Path to first FR data JSON file (alternative to fr_data1)"
                    },
                    "fr_data2": {
                        "type": "array",
                        "description": "Second FR curve",
                        "items": {
                            "type": "object",
                            "properties": {
                                "freq": {"type": "number"},
                                "db": {"type": "number"}
                            },
                            "required": ["freq", "db"]
                        }
                    },
                    "fr_file2": {
                        "type": "string",
                        "description": "Path to second FR data JSON file (alternative to fr_data2)"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if name == "compute_peq":
        fr_file = arguments.get("fr_file")
        target = arguments.get("target")
        constraints = arguments.get("constraints", DEFAULT_CONSTRAINTS.copy())

        if not fr_file:
            return [TextContent(type="text", text="Error: fr_file is required (array passing not supported).")]

        try:
            fr_data = _load_fr_from_file(fr_file)
        except ValueError as e:
            return [TextContent(type="text", text=f"Error loading FR file: {e}")]

        if not target:
            return [TextContent(type="text", text="Error: No target curve specified")]

        try:
            result = compute_peq(fr_data, target, constraints)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "list_targets":
        targets = list_available_targets()
        if not targets:
            return [TextContent(
                type="text",
                text="No target curves found. Add CSV files to the targets/ directory."
            )]
        result = {
            "targets": targets,
            "default_constraints": DEFAULT_CONSTRAINTS
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "export_target":
        target_name = arguments.get("name")
        if not target_name:
            return [TextContent(type="text", text="Error: No target name provided")]

        try:
            data = export_target(target_name)
            path = _save_fr(data, f"target_{target_name}.json")
            summary = _fr_summary(data, path, label=f"Target: {target_name}")
            return [TextContent(type="text", text=summary)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "export_fr":
        fr_data = _load_fr(arguments.get("fr_data"), arguments.get("fr_file"))
        if not fr_data:
            return [TextContent(type="text", text="Error: No FR data provided. Pass fr_data array or fr_file path.")]

        result = export_fr(fr_data)
        # Save tab-separated output to file
        path = _save_fr(fr_data, "export_fr.json")
        return [TextContent(type="text", text=f"Exported {len(fr_data)} points.\nfr_file: {path}\n\n{result}")]

    elif name == "export_peq":
        pregain = arguments.get("pregain", 0)
        filters = arguments.get("filters", [])

        result = export_peq(pregain, filters)
        return [TextContent(type="text", text=result)]

    elif name == "apply_peq_to_fr":
        fr_data = _load_fr(arguments.get("fr_data"), arguments.get("fr_file"))
        filters = arguments.get("filters", [])
        pregain = arguments.get("pregain", 0)

        if not fr_data:
            return [TextContent(type="text", text="Error: No FR data provided. Pass fr_data array or fr_file path.")]
        if not filters:
            return [TextContent(type="text", text="Error: No filters provided")]

        try:
            result = apply_peq_to_fr(fr_data, filters, pregain)
            path = _save_fr(result, "result_apply_peq.json")
            summary = _fr_summary(result, path, label="EQ'd FR Data")
            return [TextContent(type="text", text=summary)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "compute_peq_from_fr":
        fr_measured = _load_fr(arguments.get("fr_data_measured"), arguments.get("fr_file_measured"))
        fr_target = _load_fr(arguments.get("fr_data_target"), arguments.get("fr_file_target"))
        constraints = arguments.get("constraints", DEFAULT_CONSTRAINTS.copy())

        if not fr_measured:
            return [TextContent(type="text", text="Error: No measured FR data provided. Pass fr_data_measured array or fr_file_measured path.")]
        if not fr_target:
            return [TextContent(type="text", text="Error: No target FR data provided. Pass fr_data_target array or fr_file_target path.")]

        try:
            result = compute_peq_from_fr(fr_measured, fr_target, constraints)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "interpolate_fr":
        fr_data = _load_fr(arguments.get("fr_data"), arguments.get("fr_file"))
        target_points = arguments.get("target_points", 1000)

        if not fr_data:
            return [TextContent(type="text", text="Error: No FR data provided. Pass fr_data array or fr_file path.")]

        try:
            result = interpolate_fr(fr_data, target_points)
            path = _save_fr(result, "result_interpolate.json")
            summary = _fr_summary(result, path, label="Interpolated FR Data")
            return [TextContent(type="text", text=summary)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "compare_fr_curves":
        fr_data1 = _load_fr(arguments.get("fr_data1"), arguments.get("fr_file1"))
        fr_data2 = _load_fr(arguments.get("fr_data2"), arguments.get("fr_file2"))

        if not fr_data1:
            return [TextContent(type="text", text="Error: No first FR curve provided. Pass fr_data1 array or fr_file1 path.")]
        if not fr_data2:
            return [TextContent(type="text", text="Error: No second FR curve provided. Pass fr_data2 array or fr_file2 path.")]

        try:
            result = compare_fr_curves(fr_data1, fr_data2)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server using stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
