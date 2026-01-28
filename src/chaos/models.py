"""
Chaos event models and configuration.

Defines data structures for chaos injection including event types,
random events, and configuration loading from settings.yaml.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid
import yaml
import pendulum


class ChaosEventType(Enum):
    """Types of chaos events that can be injected."""
    production_outage = "production_outage"
    urgent_bug = "urgent_bug"
    team_absence = "team_absence"
    external_blocker = "external_blocker"
    priority_shift = "priority_shift"
    scope_change = "scope_change"


@dataclass
class RandomEvent:
    """
    Represents a chaos event injected into the simulation.

    Chaos events disrupt normal workflow and require adaptive responses.
    """
    event_type: ChaosEventType
    triggered_at: pendulum.DateTime
    affected_tickets: list[str]
    affected_agents: list[str]
    description: str
    severity: str
    details: dict[str, Any]
    duration_ticks: int = 1
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def __post_init__(self):
        """Validate fields after initialization."""
        valid_severities = ["low", "medium", "high", "critical"]
        if self.severity not in valid_severities:
            raise ValueError(
                f"severity must be one of {valid_severities}, got '{self.severity}'"
            )

        if not isinstance(self.triggered_at, pendulum.DateTime):
            raise TypeError("triggered_at must be a pendulum.DateTime instance")


@dataclass
class ChaosConfig:
    """
    Configuration for chaos event injection.

    Loads event probabilities and settings from config/settings.yaml.
    """
    enabled: bool
    base_event_chance: float
    event_probabilities: dict[str, float]

    def __post_init__(self):
        """Validate probability ranges."""
        if not 0.0 <= self.base_event_chance <= 1.0:
            raise ValueError(
                f"base_event_chance must be between 0.0 and 1.0, "
                f"got {self.base_event_chance}"
            )

        for event_type, prob in self.event_probabilities.items():
            if not 0.0 <= prob <= 1.0:
                raise ValueError(
                    f"{event_type} probability must be between 0.0 and 1.0, "
                    f"got {prob}"
                )

    @classmethod
    def load_from_settings(cls, settings_path: str = "config/settings.yaml") -> "ChaosConfig":
        """
        Load chaos configuration from settings.yaml.

        Returns default values if random_events section is missing.
        """
        try:
            with open(settings_path, "r") as f:
                settings = yaml.safe_load(f)
        except FileNotFoundError:
            # Return defaults if file doesn't exist
            return cls._get_defaults()

        # Get random_events section with defaults if missing
        random_events = settings.get("random_events", {})

        if not random_events:
            # Section missing, use defaults
            return cls._get_defaults()

        return cls(
            enabled=random_events.get("enabled", True),
            base_event_chance=random_events.get("base_event_chance", 0.1),
            event_probabilities=random_events.get("event_probabilities", cls._default_probabilities())
        )

    @staticmethod
    def _default_probabilities() -> dict[str, float]:
        """Default event type probabilities."""
        return {
            "production_outage": 0.05,
            "urgent_bug": 0.10,
            "team_absence": 0.03,
            "external_blocker": 0.15,
            "priority_shift": 0.12,
            "scope_change": 0.05
        }

    @classmethod
    def _get_defaults(cls) -> "ChaosConfig":
        """Return default configuration."""
        return cls(
            enabled=True,
            base_event_chance=0.1,
            event_probabilities=cls._default_probabilities()
        )
