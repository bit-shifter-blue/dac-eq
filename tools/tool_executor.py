"""
Tool executor for EQ Advisor
Implements the actual tool logic using local modules
"""

import json
import os
import tempfile
import httpx

# Import from local tools/ subdirectories
from .peq_devices.registry import DeviceRegistry
from .peq_devices.base import PEQProfile, FilterDefinition

# Import autoeq optimizer (optional - only if autoeq library is installed)
try:
    from .autoeq.optimizer import compute_peq as autoeq_compute_peq
    AUTOEQ_AVAILABLE = True
except ImportError:
    AUTOEQ_AVAILABLE = False
    print("Warning: autoeq library not available. PEQ computation will return stubs.")

# Shared temp directory for FR data files
TEMP_DIR = os.path.join(tempfile.gettempdir(), "eq-advisor")

# Squiglink databases
DATABASES = {
    "crinacle": "https://crinacle.com/graphs/iems/graphtool/data",
    "super_review": "https://squig.link/data",
    "tanchjim": "https://tanchjim.squig.link/data",
    "moondrop": "https://moondrop.squig.link/data",
    "hifigo": "https://hifigo.squig.link/data",
    "antdroid": "https://antdroid.squig.link/data",
    "precog": "https://precog.squig.link/data",
    "banbeucmas": "https://banbeucmas.squig.link/data",
}

# Caches
_phone_book_cache = {}

# Singleton device registry (prevents HID cleanup crashes)
_device_registry = None


def _get_registry():
    """Get or create singleton device registry."""
    global _device_registry
    if _device_registry is None:
        _device_registry = DeviceRegistry(debug=False)
    return _device_registry


def _ensure_temp_dir():
    """Create temp directory if it doesn't exist."""
    os.makedirs(TEMP_DIR, exist_ok=True)


# ============================================================================
# Squiglink helper functions
# ============================================================================

def _fetch_phone_book(db_name: str, base_url: str) -> list:
    """Fetch phone_book.json from a squig.link database."""
    if db_name in _phone_book_cache:
        return _phone_book_cache[db_name]

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base_url}/phone_book.json")
            resp.raise_for_status()
            data = resp.json()
            _phone_book_cache[db_name] = data
            return data
    except Exception as e:
        print(f"Error fetching phone_book for {db_name}: {e}")
        return []


def _search_in_phone_book(phone_book: list, query: str) -> list:
    """Search for IEMs matching query in a phone book."""
    query_lower = query.lower()
    results = []

    for brand_entry in phone_book:
        brand_name = brand_entry.get("name", "Unknown")
        phones = brand_entry.get("phones", [])

        for phone in phones:
            phone_name = phone.get("name", "")
            # Match if query is in brand name or phone name
            if query_lower in phone_name.lower() or query_lower in brand_name.lower():
                # Handle file being either a string or array of variants
                file_field = phone.get("file", "")
                if isinstance(file_field, list):
                    # Multiple variants
                    results.append({
                        "brand": brand_name,
                        "name": phone_name,
                        "file": file_field[0] if file_field else "",  # Use first variant
                        "variants": file_field,
                        "price": phone.get("price", "")
                    })
                else:
                    # Single file
                    results.append({
                        "brand": brand_name,
                        "name": phone_name,
                        "file": file_field,
                        "price": phone.get("price", "")
                    })

    return results


def _fetch_fr_data(db_name: str, base_url: str, file_name: str) -> list:
    """Fetch FR data from squig.link database."""
    import urllib.parse

    try:
        with httpx.Client(timeout=10.0) as client:
            # Try multiple common patterns (some files have L/R channel suffixes)
            patterns = [
                f"{file_name}.txt",
                f"{file_name} L.txt",
                f"{file_name} R.txt",
                f"{file_name}L.txt",
                f"{file_name}R.txt",
            ]

            # Try each pattern
            fr_text = None
            for pattern in patterns:
                url = f"{base_url}/{urllib.parse.quote(pattern)}"
                try:
                    resp = client.get(url, timeout=10.0)
                    if resp.status_code == 200:
                        fr_text = resp.text
                        print(f"Successfully fetched: {pattern}")
                        break
                except Exception:
                    continue

            if not fr_text:
                print(f"Failed to fetch any variant of {file_name}")
                print(f"Tried patterns: {patterns}")
                return []

            # Parse tab-separated data
            lines = fr_text.strip().split('\n')
            data = []
            for line in lines:
                parts = line.split('\t')
                if len(parts) >= 2:
                    try:
                        freq = float(parts[0])
                        db = float(parts[1])
                        data.append({"freq": freq, "db": db})
                    except ValueError:
                        continue

            return data
    except Exception as e:
        print(f"Error fetching FR data for {file_name}: {e}")
        return []


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Execute a tool and return results.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        dict: Tool execution result
    """

    # Squiglink tools
    if tool_name == "search_iems":
        return _search_iems(**tool_input)
    elif tool_name == "get_fr_data":
        return _get_fr_data(**tool_input)

    # AutoEQ tools
    elif tool_name == "compute_peq":
        return _compute_peq(**tool_input)

    # DAC-EQ tools
    elif tool_name == "list_devices":
        return _list_devices(**tool_input)
    elif tool_name == "read_peq":
        return _read_peq(**tool_input)
    elif tool_name == "write_peq":
        return _write_peq(**tool_input)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ============================================================================
# Squiglink tools - IEM frequency response data
# ============================================================================

def _search_iems(query: str) -> dict:
    """Search for IEM models by name."""
    try:
        all_results = []

        # Search all databases
        for db_name, base_url in DATABASES.items():
            phone_book = _fetch_phone_book(db_name, base_url)
            if not phone_book:
                continue

            matches = _search_in_phone_book(phone_book, query)

            for match in matches:
                match["database"] = db_name
                all_results.append(match)

        if not all_results:
            return {
                "status": "success",
                "message": f"No IEMs found matching '{query}'",
                "query": query,
                "results": []
            }

        return {
            "status": "success",
            "message": f"Found {len(all_results)} IEM(s) matching '{query}'",
            "query": query,
            "results": all_results
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error searching IEMs: {str(e)}",
            "query": query,
            "results": []
        }


def _get_fr_data(database: str, file: str) -> dict:
    """Fetch frequency response measurement data."""
    try:
        _ensure_temp_dir()

        # Check if database exists
        if database not in DATABASES:
            return {
                "status": "error",
                "message": f"Unknown database: {database}",
                "database": database,
                "file": file
            }

        # Fetch FR data from squig.link
        base_url = DATABASES[database]
        fr_data = _fetch_fr_data(database, base_url, file)

        if not fr_data:
            return {
                "status": "error",
                "message": f"Failed to fetch FR data for {file} from {database}",
                "database": database,
                "file": file
            }

        # Save to temp file for autoeq to use
        fr_file = os.path.join(TEMP_DIR, f"fr_{file}.json")
        with open(fr_file, "w") as f:
            json.dump(fr_data, f)

        return {
            "status": "success",
            "message": f"Fetched {len(fr_data)} data points for {file} from {database}",
            "database": database,
            "file": file,
            "fr_file": fr_file,
            "data_points": len(fr_data)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error fetching FR data: {str(e)}",
            "database": database,
            "file": file
        }


# ============================================================================
# AutoEQ tools - EQ computation
# ============================================================================

def _compute_peq(fr_file: str, target: str, constraints: dict = None) -> dict:
    """Compute optimal PEQ filters."""
    if not AUTOEQ_AVAILABLE:
        # Fallback to stub if autoeq not installed
        stub_filters = [
            {"freq": 100, "gain": 2.5, "q": 1.0, "type": "LSQ"},
            {"freq": 1000, "gain": -1.5, "q": 0.7, "type": "PK"},
            {"freq": 8000, "gain": 3.0, "q": 2.0, "type": "HSQ"}
        ]
        return {
            "status": "stub",
            "message": f"AutoEQ library not available. Install 'autoeq' for real optimization.",
            "target": target,
            "pregain": -2.5,
            "filters": stub_filters
        }

    try:
        # Load FR data from file
        with open(fr_file, 'r') as f:
            fr_data = json.load(f)

        # Use autoeq optimizer
        result = autoeq_compute_peq(fr_data, target, constraints)

        # Convert result to our format (round values for cleaner output)
        filters = []
        for f in result.get("filters", []):
            filters.append({
                "freq": int(round(f["freq"])),
                "gain": round(f["gain"], 1),
                "q": round(f["q"], 2),
                "type": f["type"]
            })

        return {
            "status": "success",
            "message": f"Computed {len(filters)} filters for target '{target}'",
            "target": target,
            "pregain": round(result.get("pregain", 0.0), 2),
            "filters": filters
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error computing PEQ: {str(e)}",
            "target": target
        }


# ============================================================================
# DAC-EQ tools - Device control
# ============================================================================

def _list_devices() -> dict:
    """List connected DSP devices."""
    try:
        # Use singleton registry
        registry = _get_registry()
        devices = registry.discover_devices()

        if not devices:
            return {
                "status": "success",
                "message": "No DSP devices connected",
                "devices": []
            }

        device_list = []
        for dev in devices:
            device_list.append({
                "id": dev["id"],
                "name": dev["product_string"],
                "vendor_id": dev["vendor_id"],
                "product_id": dev["product_id"],
                "handler": dev["handler"].name
            })

        return {
            "status": "success",
            "message": f"Found {len(device_list)} device(s)",
            "devices": device_list
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error listing devices: {str(e)}",
            "devices": []
        }


def _read_peq(device_id: int = None) -> dict:
    """Read current PEQ settings from device."""
    try:
        # Use singleton registry
        registry = _get_registry()
        registry.discover_devices()

        # Connect to device
        handler = registry.connect_device(device_id)

        # Read PEQ profile
        profile = handler.read_peq()

        return {
            "status": "success",
            "message": f"Read PEQ from device",
            "pregain": profile.pregain,
            "filters": [
                {
                    "freq": f.freq,
                    "gain": f.gain,
                    "q": f.q,
                    "type": f.type  # Correct attribute name!
                }
                for f in profile.filters
            ]
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error reading PEQ: {str(e)}"
        }


def _write_peq(filters: list[dict], pregain: float = 0.0, device_id: int = None) -> dict:
    """Write PEQ settings to device."""
    try:
        # Use singleton registry
        registry = _get_registry()
        registry.discover_devices()

        # Connect to device
        handler = registry.connect_device(device_id)

        # Create PEQ profile
        filter_defs = [
            FilterDefinition(
                freq=f["freq"],
                gain=f["gain"],
                q=f["q"],
                filter_type=f["type"]
            )
            for f in filters
        ]

        profile = PEQProfile(
            pregain=pregain,
            filters=filter_defs
        )

        # Write to device
        handler.write_peq(profile)

        return {
            "status": "success",
            "message": f"Wrote {len(filters)} filters to device",
            "pregain": pregain,
            "filter_count": len(filters)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error writing PEQ: {str(e)}"
        }
