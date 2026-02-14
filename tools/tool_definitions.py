"""
Claude API tool definitions for EQ Advisor
Matches the schema expected by anthropic.messages.create(tools=...)
"""

TOOLS = [
    # Squiglink tools - IEM frequency response data
    {
        "name": "search_iems",
        "description": "Search for IEM (In-Ear Monitor) models by brand or model name. Returns matching models with their database and file information. Use this to find the measurement data needed for EQ tuning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term - brand name (e.g., 'Moondrop') or model name (e.g., 'Blessing 3')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_fr_data",
        "description": "Fetch frequency response measurement data for a specific IEM. Returns array of {freq, db} points. Use the database and file name from search_iems results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name from search results (e.g., 'crinacle', 'super_review')"
                },
                "file": {
                    "type": "string",
                    "description": "File name from search results (without .txt extension)"
                }
            },
            "required": ["database", "file"]
        }
    },

    # AutoEQ tools - EQ computation
    {
        "name": "compute_peq",
        "description": "Compute optimal PEQ (parametric EQ) filters to match a target curve. Returns pregain and filter settings. Use FR data from get_fr_data as input.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fr_file": {
                    "type": "string",
                    "description": "Path to FR data JSON file from get_fr_data output"
                },
                "target": {
                    "type": "string",
                    "description": "Target curve name (e.g., 'harman_ie_2019', 'diffuse_field')"
                },
                "constraints": {
                    "type": "object",
                    "description": "Optional device constraints (max_filters, gain_range, etc.)",
                    "properties": {
                        "max_filters": {"type": "integer"},
                        "gain_range": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2
                        },
                        "q_range": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2
                        }
                    }
                }
            },
            "required": ["fr_file", "target"]
        }
    },

    # PEQ-Devices tools - Device control
    {
        "name": "list_devices",
        "description": "List all connected DSP/DAC devices (Qudelix, Tanchjim, Moondrop, etc.). Returns device IDs, names, and capabilities. Use this to check what's connected before writing EQ.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "read_peq",
        "description": "Read current PEQ settings from a connected device. Returns pregain and filters. Use device_id from list_devices (optional if only one device connected).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "integer",
                    "description": "Device ID from list_devices (0-based index). Optional if only one device connected."
                }
            }
        }
    },
    {
        "name": "write_peq",
        "description": "Write PEQ settings to a connected device. Applies the EQ immediately. Use filters from compute_peq output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "array",
                    "description": "Array of filter objects with freq, gain, q, type",
                    "items": {
                        "type": "object",
                        "properties": {
                            "freq": {"type": "number", "description": "Frequency in Hz"},
                            "gain": {"type": "number", "description": "Gain in dB"},
                            "q": {"type": "number", "description": "Q factor"},
                            "type": {"type": "string", "enum": ["PK", "LSQ", "HSQ"]}
                        },
                        "required": ["freq", "gain", "q", "type"]
                    }
                },
                "pregain": {
                    "type": "number",
                    "description": "Pregain in dB (optional)"
                },
                "device_id": {
                    "type": "integer",
                    "description": "Device ID from list_devices (optional if only one device connected)"
                }
            },
            "required": ["filters"]
        }
    }
]
