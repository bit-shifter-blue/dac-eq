#!/usr/bin/env python3
"""
DAC-EQ: Universal DSP/DAC Parametric EQ Tool
Supports multiple devices: Tanchjim, Qudelix, and more
Based on devicePEQ by Pragmatic Audio (jeromeof)

Requires: pip install hidapi
"""
import argparse
import json
import os
from dsp_devices import DeviceRegistry, PEQProfile, FilterDefinition, DeviceError, ProfileValidationError


def parse_autoeq(filepath):
    """Parse AutoEQ txt format"""
    filters = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line.startswith('Filter') and ':' in line:
                # Format: Filter 1: ON PK Fc 100 Hz Gain -3.5 dB Q 1.41
                parts = line.split()
                try:
                    fc_idx = parts.index('Fc') + 1
                    gain_idx = parts.index('Gain') + 1
                    q_idx = parts.index('Q') + 1

                    freq = int(float(parts[fc_idx]))
                    gain = float(parts[gain_idx])
                    q = float(parts[q_idx])

                    # Detect filter type
                    ftype = "PK"
                    if "LSC" in line or "LSQ" in line or "LS" in parts:
                        ftype = "LSQ"
                    elif "HSC" in line or "HSQ" in line or "HS" in parts:
                        ftype = "HSQ"

                    filters.append(FilterDefinition(freq=freq, gain=gain, q=q, type=ftype))
                except (ValueError, IndexError):
                    continue
    return filters


def _do_read(handler):
    """Read and display current PEQ settings from device"""
    print("Reading current PEQ settings...\n")
    profile = handler.read_peq()

    print(f"Pregain: {profile.pregain} dB\n")
    print("Filters:")
    for i, f in enumerate(profile.filters):
        print(f"  {i+1}: {f.freq:5.0f} Hz, {f.gain:+5.1f} dB, Q={f.q:.3f}, Type={f.type}")


def _do_write(handler, filepath):
    """Write PEQ from AutoEQ txt file to device"""
    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}")
        return
    print(f"Loading PEQ from: {filepath}")
    filters = parse_autoeq(filepath)
    if not filters:
        print("No valid filters found in file!")
        return

    pregain = 0.0  # AutoEQ files determine their own pregain
    profile = PEQProfile(filters=filters, pregain=pregain)

    print(f"Found {len(filters)} filters, pregain: {pregain} dB\n")
    print("Writing to device...")
    handler.write_peq(profile)
    print("Success!")


def _do_json(handler, filepath):
    """Write PEQ from JSON file to device"""
    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}")
        return
    print(f"Loading PEQ from JSON: {filepath}")
    with open(filepath) as f:
        data = json.load(f)

    # Parse filters
    filter_data = data.get('filters', data)
    if isinstance(filter_data, dict):
        filter_data = [filter_data]

    filters = [
        FilterDefinition(
            freq=int(f['freq']),
            gain=float(f['gain']),
            q=float(f['q']),
            type=f.get('type', 'PK')
        )
        for f in filter_data
    ]

    # Use pregain from JSON (required in JSON format)
    pregain = data.get('pregain', 0.0)
    profile = PEQProfile(filters=filters, pregain=pregain)

    print(f"Found {len(filters)} filters, pregain: {pregain} dB\n")
    print("Writing to device...")
    handler.write_peq(profile)
    print("Success!")


def main():
    parser = argparse.ArgumentParser(
        description='DAC-EQ: Universal DSP/DAC Parametric EQ Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                         Read current PEQ settings (default)
  %(prog)s --read                  Read current PEQ settings (explicit)
  %(prog)s --json profile.json     Write PEQ from JSON file
  %(prog)s --write eq.txt          Write PEQ from AutoEQ txt file
  %(prog)s --list                  List available devices
  %(prog)s --device 0 --json file  Select device 0 and write JSON

Device Selection:
  If multiple devices are connected, use --device to select one.
  Device IDs are shown in --list output (0-based index).
  If only one device is connected, it will be auto-selected.

Profile Format:
  Pregain and filter parameters should be set in JSON or AutoEQ files.
  Set pregain by editing your profile file directly.

Supported Devices:
  Tanchjim (Fission, Bunny, One DSP), Qudelix 5K, and more
        """
    )

    # Create mutually exclusive group for actions
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--read', '-r', action='store_true',
        help='Read current PEQ settings (default action)')
    action_group.add_argument('--write', '-w', type=str, metavar='FILE',
        help='Write PEQ from AutoEQ txt file')
    action_group.add_argument('--json', '-j', type=str, metavar='FILE',
        help='Write PEQ from JSON file')
    action_group.add_argument('--list', '-l', action='store_true',
        help='List available DSP devices and exit')

    # Modifier arguments
    parser.add_argument('--device', '-d', type=int, metavar='ID',
        help='Device ID to use (0-based index from --list). Auto-selects if only one device.')
    parser.add_argument('--debug', action='store_true',
        help='Show debug output including HID packets')

    args = parser.parse_args()

    # Create registry
    registry = DeviceRegistry(debug=args.debug)

    try:
        # Discover devices
        devices = registry.discover_devices()

        # Handle --list action (standalone, no device connection needed)
        if args.list:
            print("Searching for DSP devices...\n")
            if devices:
                for d in devices:
                    print(f"  [{d['id']}] {d['product_string']}")
                    print(f"      Handler: {d['handler'].name}")
                    print(f"      VID: 0x{d['vendor_id']:04X}, PID: 0x{d['product_id']:04X}")
                    caps = d['handler'].capabilities
                    print(f"      Max filters: {caps.max_filters}, Supports: {', '.join(sorted(caps.supported_filter_types))}")
                    print(f"      Read: {'Yes' if caps.supports_read else 'No'}, Write: {'Yes' if caps.supports_write else 'No'}")
                    print()
            else:
                print("  No DSP devices found. Is your device plugged in?")
            return

        # Check for devices before any other action
        if not devices:
            print("No DSP/DAC devices found. Connect a device and try again.")
            print("\nTroubleshooting:")
            print("  1. Make sure your device is plugged in")
            print("  2. Try: python dac-eq.py --list")
            print("  3. You may need to grant terminal USB access in System Preferences")
            return

        # Determine action (default to read)
        action = None
        if args.write:
            action = 'write'
        elif args.json:
            action = 'json'
        elif args.read:
            action = 'read'
        else:
            action = 'read'  # default action

        # Connect to device (only once)
        handler = None
        try:
            device_info = registry.select_device(args.device)
            handler = registry.connect_device(args.device)

            print(f"Connected: {device_info['product_string']} ({handler.name})")
            print()

            # Execute action
            if action == 'read':
                _do_read(handler)

            elif action == 'write':
                _do_write(handler, args.write)

            elif action == 'json':
                _do_json(handler, args.json)

        except ProfileValidationError as e:
            print(f"\nValidation error: {e}")
            return

        except ValueError as e:
            # Device selection error (multiple devices, invalid ID, etc.)
            print(f"\n{e}")
            return

        except NotImplementedError as e:
            print(f"\nOperation not supported: {e}")
            return

        except DeviceError as e:
            print(f"\nDevice error: {e}")
            return

        finally:
            if handler:
                handler.disconnect()

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        if args.debug:
            traceback.print_exc()


if __name__ == '__main__':
    main()
