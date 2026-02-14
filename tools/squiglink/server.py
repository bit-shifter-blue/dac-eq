#!/usr/bin/env python3
"""
Squiglink MCP Server - Fetch IEM frequency response data from squig.link databases
"""

import asyncio
import json
import os
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx

# Project root (eq-advisor/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# FR cache directory (persistent, not temp)
FR_CACHE_DIR = PROJECT_ROOT / "cache" / "fr"


def normalize_iem_name(name: str) -> str:
    """
    Normalize IEM name to cache-friendly format.

    Examples:
        "Moondrop Blessing 3" -> "moondrop-blessing-3"
        "KZ ZSN Pro X" -> "kz-zsn-pro-x"
        "7Hz Salnotes Zero" -> "7hz-salnotes-zero"
    """
    return name.lower().replace(" ", "-").replace("_", "-")


def _ensure_cache_dir():
    """Create cache directory if it doesn't exist."""
    FR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Popular squig.link databases
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

server = Server("squiglink")

# Cache for phone books
_phone_book_cache: dict[str, list] = {}


def get_cache_path(iem_name: str, variant: str = "default") -> Path:
    """
    Get cache file path for an IEM name and variant.

    Args:
        iem_name: IEM name (will be normalized)
        variant: Variant name (default: "default")

    Returns:
        Path to: cache/fr/{normalized-iem-name}/{variant}.csv
    """
    normalized = normalize_iem_name(iem_name)
    iem_dir = FR_CACHE_DIR / normalized
    return iem_dir / f"{variant}.csv"


def load_from_cache(iem_name: str, variant: str = "default") -> list[dict] | None:
    """
    Load FR data from cache if it exists.

    Args:
        iem_name: IEM name (will be normalized)
        variant: Variant name (default: "default")

    Returns:
        List of {freq, db} dicts or None if not cached
    """
    cache_path = get_cache_path(iem_name, variant)
    if not cache_path.exists():
        return None

    data_points = []
    try:
        with open(cache_path, "r") as f:
            lines = f.readlines()
            for line in lines[1:]:  # Skip header
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    freq = float(parts[0])
                    db = float(parts[1])
                    data_points.append({"freq": freq, "db": db})
        return data_points if data_points else None
    except Exception:
        return None


def save_to_cache(iem_name: str, data_points: list[dict], variant: str = "default") -> Path:
    """
    Save FR data to cache as CSV.

    Args:
        iem_name: IEM name (will be normalized)
        data_points: List of {freq, db} dicts
        variant: Variant name (default: "default")

    Returns:
        Path to cached file
    """
    cache_path = get_cache_path(iem_name, variant)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cache_path, "w") as f:
        f.write("frequency,raw\n")
        for point in data_points:
            f.write(f"{point['freq']},{point['db']}\n")

    return cache_path


def list_cached_fr() -> list[str]:
    """List all cached IEM names (directory names)."""
    if not FR_CACHE_DIR.exists():
        return []
    return sorted([d.name for d in FR_CACHE_DIR.iterdir() if d.is_dir()])


def search_cached_fr(query: str) -> list[dict]:
    """Search cached FR measurements by name. Returns list of matching cached IEMs."""
    cached = list_cached_fr()
    query_lower = query.lower()
    results = []

    for name in cached:
        if query_lower in name.lower():
            results.append({
                "brand": "",  # Not stored in cache filename
                "name": name,
                "file": name,
                "variants": [name],
                "price": "",
                "database": "cached",
                "cached": True,
            })

    return results


async def fetch_phone_book(client: httpx.AsyncClient, db_name: str, base_url: str) -> list:
    """Fetch and cache phone_book.json from a squig.link database."""
    if db_name in _phone_book_cache:
        return _phone_book_cache[db_name]

    try:
        resp = await client.get(f"{base_url}/phone_book.json", timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        _phone_book_cache[db_name] = data
        return data
    except Exception as e:
        return []


def search_in_phone_book(phone_book: list, query: str) -> list:
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
                    variants = file_field
                else:
                    variants = [file_field] if file_field else []

                results.append({
                    "brand": brand_name,
                    "name": phone_name,
                    "file": variants[0] if variants else "",
                    "variants": variants,
                    "price": phone.get("price", ""),
                })

    return results


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_iems",
            description="Search for IEMs by name. Checks local cache first, then searches squig.link databases. Returns matching models with their database and file info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (brand name or model name, e.g. 'Fission', 'Moondrop', 'Blessing')"
                    },
                    "databases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": f"Optional: specific databases to search. Available: {', '.join(DATABASES.keys())}. Defaults to all."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_fr_data",
            description="Fetch frequency response measurement data for a specific IEM. Use search_iems first to find the database and file name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {
                        "type": "string",
                        "description": f"Database name. One of: cached, {', '.join(DATABASES.keys())}. Use 'cached' for locally cached measurements."
                    },
                    "file": {
                        "type": "string",
                        "description": "File name from search results (without .txt extension)"
                    }
                },
                "required": ["database", "file"]
            }
        ),
        Tool(
            name="list_databases",
            description="List all available squig.link databases",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_cached",
            description="List all locally cached FR measurements",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with httpx.AsyncClient() as client:

        if name == "list_databases":
            result = "Available squig.link databases:\n\n"
            for db_name, url in DATABASES.items():
                result += f"- {db_name}: {url}\n"
            return [TextContent(type="text", text=result)]

        elif name == "list_cached":
            cached = list_cached_fr()
            if not cached:
                return [TextContent(type="text", text="No cached FR measurements found.")]
            result = f"Cached FR measurements ({len(cached)}):\n\n"
            for cached_name in cached:
                result += f"- {cached_name}\n"
            return [TextContent(type="text", text=result)]

        elif name == "search_iems":
            query = arguments.get("query", "")
            db_filter = arguments.get("databases", list(DATABASES.keys()))

            all_results = []

            # Check local cache first
            cached_matches = search_cached_fr(query)
            all_results.extend(cached_matches)

            # Then search web databases
            for db_name in db_filter:
                if db_name not in DATABASES:
                    continue

                base_url = DATABASES[db_name]
                phone_book = await fetch_phone_book(client, db_name, base_url)
                matches = search_in_phone_book(phone_book, query)

                for match in matches:
                    match["database"] = db_name
                    all_results.append(match)

            if not all_results:
                return [TextContent(type="text", text=f"No IEMs found matching '{query}'")]

            result = f"Found {len(all_results)} IEM(s) matching '{query}':\n\n"
            for i, item in enumerate(all_results, 1):
                is_cached = item.get("cached", False)
                if is_cached:
                    result += f"{i}. **{item['name']}** (CACHED)\n"
                    result += f"   Source: Local cache\n"
                else:
                    result += f"{i}. **{item['brand']} {item['name']}**\n"
                    result += f"   Database: {item['database']}\n"

                    variants = item.get('variants', [])
                    if len(variants) > 1:
                        result += f"   Variants ({len(variants)}):\n"
                        for v in variants:
                            result += f"     - {v}\n"
                    else:
                        result += f"   File: {item['file']}\n"

                    if item.get('price'):
                        result += f"   Price: {item['price']}\n"
                result += "\n"

            return [TextContent(type="text", text=result)]

        elif name == "get_fr_data":
            database = arguments.get("database", "")
            file_name = arguments.get("file", "")

            # Handle "cached" as a special database that only checks local cache
            if database == "cached":
                cached_data = load_from_cache(file_name)
                if not cached_data:
                    return [TextContent(type="text", text=f"No cached data found for '{file_name}'. Use search_iems to find and fetch it first.")]
            elif database not in DATABASES:
                return [TextContent(type="text", text=f"Unknown database: {database}. Use list_databases to see available options.")]
            else:
                # Check cache first for web databases too
                cached_data = load_from_cache(file_name)
            if cached_data:
                # Save to temp file for cross-MCP passing
                fr_path = _save_fr_to_temp(file_name, cached_data)

                result = f"## Frequency Response Data: {file_name}\n"
                result += f"Source: **CACHED** ({get_cache_path(file_name)})\n\n"
                result += f"Total data points: {len(cached_data)}\n"
                result += f"fr_file: {fr_path}\n\n"

                # Extract key frequencies for summary
                key_freqs = {}
                target_freqs = [20, 50, 100, 250, 500, 1000, 2000, 4000, 8000, 10000, 12000, 16000]
                for point in cached_data:
                    freq = point["freq"]
                    for target in target_freqs:
                        if target * 0.9 <= freq <= target * 1.1:
                            if target not in key_freqs:
                                key_freqs[target] = point["db"]

                result += "### Key Frequencies:\n"
                result += "| Frequency | SPL (dB) |\n"
                result += "|-----------|----------|\n"
                for freq in sorted(key_freqs.keys()):
                    result += f"| {freq} Hz | {key_freqs[freq]:.1f} |\n"

                return [TextContent(type="text", text=result)]

            base_url = DATABASES[database]
            import urllib.parse

            # Try multiple common patterns used across squig.link instances
            patterns = [
                f"{file_name}.txt",
                f"{file_name} L.txt",
                f"{file_name} R.txt",
                f"{file_name}L.txt",
                f"{file_name}R.txt",
            ]

            found_files = {}
            for pattern in patterns:
                url = f"{base_url}/{urllib.parse.quote(pattern)}"
                try:
                    resp = await client.get(url, timeout=10.0)
                    if resp.status_code == 200:
                        found_files[pattern] = resp.text
                except Exception:
                    continue

            if not found_files:
                return [TextContent(type="text", text=f"Could not fetch FR data for '{file_name}' from {database}.\n\nTried patterns: {', '.join(patterns)}\n\nThe file name may be different - check search results for exact variant names.")]

            # Use first found file (prefer L channel or single file)
            chosen_file = None
            for pattern in patterns:
                if pattern in found_files:
                    chosen_file = pattern
                    break

            fr_data = found_files[chosen_file]
            successful_url = f"{base_url}/{urllib.parse.quote(chosen_file)}"

            # Report all found files
            files_found_msg = f"Found files: {', '.join(found_files.keys())}\nUsing: {chosen_file}\n\n"

            # Parse and summarize the FR data
            lines = fr_data.strip().split('\n')

            # Extract key frequency points for summary
            key_freqs = {}
            target_freqs = [20, 50, 100, 250, 500, 1000, 2000, 4000, 8000, 10000, 12000, 16000]

            for line in lines:
                try:
                    parts = line.replace('→', '\t').replace(',', '\t').split('\t')
                    if len(parts) >= 2:
                        freq = float(parts[-2].strip())
                        db = float(parts[-1].strip())

                        # Find closest target frequency
                        for target in target_freqs:
                            if target * 0.9 <= freq <= target * 1.1:
                                if target not in key_freqs:
                                    key_freqs[target] = db
                except Exception:
                    continue

            # Parse all data points into structured format
            data_points = []
            for line in lines:
                # Skip comment lines
                if line.strip().startswith('*') or line.strip().startswith('#'):
                    continue
                try:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        freq = float(parts[0].strip())
                        db = float(parts[1].strip())
                        data_points.append({"freq": freq, "db": db})
                except Exception:
                    continue

            # Save to cache and temp file
            if data_points:
                cache_path = save_to_cache(file_name, data_points)
                cache_msg = f"Cached to: {cache_path}\n"
                fr_path = _save_fr_to_temp(file_name, data_points)
                fr_file_msg = f"fr_file: {fr_path}\n"
            else:
                cache_msg = ""
                fr_file_msg = ""

            result = f"## Frequency Response Data: {file_name}\n"
            result += f"Source: {successful_url}\n"
            result += cache_msg
            result += fr_file_msg
            result += files_found_msg
            result += f"Total data points: {len(data_points)}\n\n"

            result += "### Key Frequencies:\n"
            result += "| Frequency | SPL (dB) |\n"
            result += "|-----------|----------|\n"

            for freq in sorted(key_freqs.keys()):
                result += f"| {freq} Hz | {key_freqs[freq]:.1f} |\n"

            return [TextContent(type="text", text=result)]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
