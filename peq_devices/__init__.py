"""DSP Device Abstraction Layer

Provides a unified interface for controlling multiple DSP devices (Tanchjim, Qudelix, etc.)
through a handler-based architecture.
"""

from .base import (
    DeviceHandler,
    PEQProfile,
    FilterDefinition,
    DeviceCapabilities,
    DeviceError,
    DeviceNotConnectedError,
    DeviceNotFoundError,
    DeviceCommunicationError,
    ProfileValidationError,
)
from .registry import DeviceRegistry

__all__ = [
    'DeviceHandler',
    'DeviceRegistry',
    'PEQProfile',
    'FilterDefinition',
    'DeviceCapabilities',
    'DeviceError',
    'DeviceNotConnectedError',
    'DeviceNotFoundError',
    'DeviceCommunicationError',
    'ProfileValidationError',
]
