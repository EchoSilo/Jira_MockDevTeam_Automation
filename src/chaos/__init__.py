"""
Chaos injection module.

Provides models and configuration for injecting chaos events
into the simulation to test adaptive pathfinding.
"""

from .models import RandomEvent, ChaosConfig, ChaosEventType
from .event_catalog import EventCatalog

__all__ = ["RandomEvent", "ChaosConfig", "ChaosEventType", "EventCatalog"]
