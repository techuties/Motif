"""Motif — visual mouse and keyboard recorder."""

__version__ = "1.0.0"

from motif.api import MotifClient
from motif.models import Event, EventType, Script

__all__ = ["Event", "EventType", "MotifClient", "Script", "__version__"]
