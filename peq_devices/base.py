"""Base classes and data structures for DSP device handlers"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple


# Custom exception hierarchy

class DeviceError(Exception):
    """Base exception for DSP device errors"""


class DeviceNotConnectedError(DeviceError):
    """Device is not connected"""


class DeviceNotFoundError(DeviceError):
    """Device not found during discovery"""


class DeviceCommunicationError(DeviceError):
    """HID communication failed"""


class ProfileValidationError(DeviceError):
    """PEQ profile validation failed"""


@dataclass
class FilterDefinition:
    """Represents a single PEQ filter"""
    freq: int  # Frequency in Hz
    gain: float  # Gain in dB
    q: float  # Q factor
    type: str  # Filter type: PK, LSQ, HSQ, LPF, HPF, etc.

    def __post_init__(self):
        """Validate filter parameters"""
        if self.freq <= 0:
            raise ValueError(f"Frequency must be positive, got {self.freq}")
        if self.q <= 0:
            raise ValueError(f"Q must be positive, got {self.q}")
        if self.type not in {'PK', 'LSQ', 'HSQ', 'LPF', 'HPF'}:
            raise ValueError(f"Unknown filter type: {self.type}")


@dataclass
class PEQProfile:
    """Represents a complete PEQ profile with filters and pregain"""
    filters: List[FilterDefinition]
    pregain: float = 0.0  # Pregain in dB

    def __post_init__(self):
        """Validate profile"""
        if not isinstance(self.filters, list):
            raise ValueError("Filters must be a list")
        for i, f in enumerate(self.filters):
            if not isinstance(f, FilterDefinition):
                raise ValueError(f"Filter {i} is not a FilterDefinition instance")


@dataclass
class DeviceCapabilities:
    """Describes the capabilities and constraints of a DSP device"""
    max_filters: int
    gain_range: Tuple[float, float]  # (min_db, max_db)
    pregain_range: Tuple[float, float]  # (min_db, max_db)
    supported_filter_types: Set[str]  # {'PK', 'LSQ', 'HSQ', ...}
    freq_range: Tuple[int, int]  # (min_hz, max_hz)
    q_range: Tuple[float, float]  # (min_q, max_q)
    supports_read: bool = True
    supports_write: bool = True


class DeviceHandler(ABC):
    """Abstract base class for DSP device protocol handlers"""

    def __init__(self):
        self.device = None
        self.debug = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable handler name (e.g., 'Tanchjim', 'Qudelix')"""
        pass

    @property
    @abstractmethod
    def vendor_id(self) -> int:
        """USB vendor ID (e.g., 0x31B2)"""
        pass

    @property
    @abstractmethod
    def product_ids(self) -> Optional[List[int]]:
        """USB product IDs this handler supports, or None for any product"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> DeviceCapabilities:
        """Device capabilities and constraints"""
        pass

    @abstractmethod
    def connect(self, device_dict: dict) -> None:
        """Connect to the device

        Args:
            device_dict: HID device dict from hid.enumerate()

        Raises:
            Exception: If connection fails
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the device"""
        pass

    @abstractmethod
    def read_peq(self) -> PEQProfile:
        """Read current PEQ settings from device

        Returns:
            PEQProfile: Current device settings

        Raises:
            NotImplementedError: If device doesn't support reading
            Exception: If read fails
        """
        pass

    @abstractmethod
    def write_peq(self, profile: PEQProfile) -> None:
        """Write PEQ settings to device

        Args:
            profile: PEQ profile to write

        Raises:
            ValueError: If profile validation fails
            Exception: If write fails
        """
        pass

    def validate_profile(self, profile: PEQProfile) -> None:
        """Validate a PEQ profile against device capabilities

        Args:
            profile: PEQ profile to validate

        Raises:
            ProfileValidationError: If profile is invalid for this device
        """
        caps = self.capabilities

        # Check filter count
        if len(profile.filters) > caps.max_filters:
            raise ProfileValidationError(
                f"{self.name} supports max {caps.max_filters} filters, "
                f"got {len(profile.filters)}"
            )

        # Check pregain range
        if not (caps.pregain_range[0] <= profile.pregain <= caps.pregain_range[1]):
            raise ProfileValidationError(
                f"Pregain {profile.pregain}dB out of range "
                f"{caps.pregain_range[0]}dB to {caps.pregain_range[1]}dB"
            )

        # Check each filter
        for i, f in enumerate(profile.filters):
            # Check filter type
            if f.type not in caps.supported_filter_types:
                raise ProfileValidationError(
                    f"Filter {i}: {self.name} doesn't support type '{f.type}'. "
                    f"Supported types: {', '.join(sorted(caps.supported_filter_types))}"
                )

            # Check gain range
            if not (caps.gain_range[0] <= f.gain <= caps.gain_range[1]):
                raise ProfileValidationError(
                    f"Filter {i}: gain {f.gain}dB out of range "
                    f"{caps.gain_range[0]}dB to {caps.gain_range[1]}dB"
                )

            # Check frequency range
            if not (caps.freq_range[0] <= f.freq <= caps.freq_range[1]):
                raise ProfileValidationError(
                    f"Filter {i}: frequency {f.freq}Hz out of range "
                    f"{caps.freq_range[0]}Hz to {caps.freq_range[1]}Hz"
                )

            # Check Q range
            if not (caps.q_range[0] <= f.q <= caps.q_range[1]):
                raise ProfileValidationError(
                    f"Filter {i}: Q {f.q} out of range "
                    f"{caps.q_range[0]} to {caps.q_range[1]}"
                )

    def matches_device(self, device_dict: dict) -> bool:
        """Check if this handler can handle the given device

        Default implementation checks vendor_id and product_ids.
        Subclasses can override for custom matching logic (e.g., product name).

        Args:
            device_dict: HID device dict from hid.enumerate()

        Returns:
            bool: True if this handler can handle the device
        """
        # Check vendor ID
        if device_dict['vendor_id'] != self.vendor_id:
            return False

        # If handler specifies product IDs, check them
        if self.product_ids is not None:
            return device_dict['product_id'] in self.product_ids

        # Otherwise accept any product from this vendor
        return True
