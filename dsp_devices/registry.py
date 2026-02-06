"""Device discovery and connection registry"""

import hid
from typing import List, Optional, Dict, Any
from .base import DeviceHandler


class DeviceRegistry:
    """Manages device discovery and connection"""

    def __init__(self, debug: bool = False):
        """Initialize registry with available handlers

        Args:
            debug: Enable debug output
        """
        self.debug = debug
        self.discovered_devices: List[Dict[str, Any]] = []

        # Import handlers here to avoid circular imports
        from .handlers.tanchjim import TanchjimHandler
        from .handlers.qudelix import QudelixHandler

        # Create handler instances
        self.handlers: List[DeviceHandler] = [
            TanchjimHandler(),
            QudelixHandler(),
        ]

        # Set debug flag on all handlers
        for handler in self.handlers:
            handler.debug = debug

    def discover_devices(self) -> List[Dict[str, Any]]:
        """Discover all connected DSP devices

        Returns:
            List of device info dicts with keys:
                - id: Device index for selection
                - vendor_id: USB vendor ID
                - product_id: USB product ID
                - product_string: Product name
                - manufacturer_string: Manufacturer name
                - serial_number: Device serial number
                - path: HID device path
                - handler: DeviceHandler instance that can handle this device
        """
        self.discovered_devices = []

        # Get all HID devices
        all_devices = hid.enumerate()

        # Match devices to handlers
        matched_devices = []
        for device_dict in all_devices:
            for handler in self.handlers:
                if handler.matches_device(device_dict):
                    # Store matched device with handler
                    matched_devices.append((device_dict, handler))

                    if self.debug:
                        print(f"[DEBUG] Found {handler.name} device: {device_dict['product_string']}")

                    # Only match one handler per device
                    break

        # Sort matched devices by product string (stable ordering) then path for consistency
        matched_devices.sort(key=lambda x: (x[0]['product_string'], str(x[0]['path'])))

        # Assign IDs to sorted devices
        for device_dict, handler in matched_devices:
            device_info = {
                'id': len(self.discovered_devices),
                'vendor_id': device_dict['vendor_id'],
                'product_id': device_dict['product_id'],
                'product_string': device_dict['product_string'],
                'manufacturer_string': device_dict['manufacturer_string'],
                'serial_number': device_dict['serial_number'],
                'path': device_dict['path'],
                'handler': handler,
                '_device_dict': device_dict,  # Store original dict
            }
            self.discovered_devices.append(device_info)

        return self.discovered_devices

    def select_device(self, device_id: Optional[int] = None) -> Dict[str, Any]:
        """Select a device from discovered devices

        Args:
            device_id: Device index (0-based), or None to auto-select if only one device

        Returns:
            Device info dict

        Raises:
            ValueError: If device_id is invalid or multiple devices found without selection
        """
        if not self.discovered_devices:
            raise ValueError("No DSP devices found. Connect a device and try again.")

        # Auto-select if only one device
        if device_id is None:
            if len(self.discovered_devices) == 1:
                return self.discovered_devices[0]
            else:
                # Multiple devices, require selection
                device_list = "\n".join(
                    f"  {d['id']}: {d['product_string']} ({d['handler'].name})"
                    for d in self.discovered_devices
                )
                raise ValueError(
                    f"Multiple devices found. Specify device_id:\n{device_list}"
                )

        # Validate device_id
        if device_id < 0 or device_id >= len(self.discovered_devices):
            raise ValueError(
                f"Invalid device_id {device_id}. "
                f"Valid range: 0-{len(self.discovered_devices) - 1}"
            )

        return self.discovered_devices[device_id]

    def connect_device(self, device_id: Optional[int] = None) -> DeviceHandler:
        """Connect to a device and return its handler

        Args:
            device_id: Device index (0-based), or None to auto-select if only one device

        Returns:
            DeviceHandler: Connected handler instance

        Raises:
            ValueError: If device selection fails
            Exception: If connection fails
        """
        # Select device
        device_info = self.select_device(device_id)

        # Create a fresh handler instance of the same type
        handler_class = type(device_info['handler'])
        handler = handler_class()
        handler.debug = self.debug

        # Connect
        handler.connect(device_info['_device_dict'])

        if self.debug:
            print(f"[DEBUG] Connected to {device_info['product_string']} via {handler.name}")

        return handler

    def get_device_info(self, device_id: int) -> Dict[str, Any]:
        """Get information about a discovered device

        Args:
            device_id: Device index (0-based)

        Returns:
            Device info dict (without _device_dict)

        Raises:
            ValueError: If device_id is invalid
        """
        if device_id < 0 or device_id >= len(self.discovered_devices):
            raise ValueError(
                f"Invalid device_id {device_id}. "
                f"Valid range: 0-{len(self.discovered_devices) - 1}"
            )

        device_info = self.discovered_devices[device_id].copy()
        # Remove internal fields
        device_info.pop('_device_dict', None)
        # Add capabilities
        device_info['capabilities'] = device_info['handler'].capabilities

        return device_info
