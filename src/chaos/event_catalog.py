"""Event catalog with templates and archetype-specific weights."""

from pathlib import Path
from typing import Optional
import yaml

from src.scenarios.sprint_scenario import ScenarioArchetype
from .models import ChaosEventType


class EventCatalog:
    """Provides event templates and archetype-specific weight adjustments."""

    def __init__(self, config_path: Optional[Path] = None):
        """Load event catalog from YAML.

        Args:
            config_path: Path to chaos_events.yaml. Defaults to config/chaos_events.yaml
        """
        if config_path is None:
            config_path = Path("config/chaos_events.yaml")

        self._templates = {}
        self._archetype_weights = {}

        if config_path.exists():
            with open(config_path, "r") as f:
                data = yaml.safe_load(f) or {}
            self._templates = data.get("event_templates", {})
            self._archetype_weights = data.get("archetype_weights", {})

    def get_template(self, event_type: ChaosEventType) -> dict:
        """Get template for event type.

        Returns:
            Template dict with description_template, default_severity, etc.
            Returns empty dict if template not found.
        """
        return self._templates.get(event_type.value, {})

    def get_weight_multiplier(
        self,
        archetype: ScenarioArchetype,
        event_type: ChaosEventType
    ) -> float:
        """Get weight multiplier for event type in given archetype.

        Args:
            archetype: The scenario archetype (smooth_sprint, blocker_heavy, etc.)
            event_type: The chaos event type

        Returns:
            Weight multiplier (1.0 = no change, 2.0 = double, 0.5 = half)
            Defaults to 1.0 if archetype or event_type not found.
        """
        archetype_weights = self._archetype_weights.get(archetype.value, {})
        return archetype_weights.get(event_type.value, 1.0)

    def adjust_probabilities(
        self,
        base_probabilities: dict[str, float],
        archetype: ScenarioArchetype
    ) -> dict[str, float]:
        """Adjust base probabilities by archetype weights.

        Args:
            base_probabilities: Dict of event_type -> base probability
            archetype: Current scenario archetype

        Returns:
            Adjusted probabilities (not normalized)
        """
        adjusted = {}
        for event_type_str, base_prob in base_probabilities.items():
            try:
                event_type = ChaosEventType(event_type_str)
                multiplier = self.get_weight_multiplier(archetype, event_type)
                adjusted[event_type_str] = base_prob * multiplier
            except ValueError:
                # Unknown event type, keep base probability
                adjusted[event_type_str] = base_prob
        return adjusted

    def format_description(
        self,
        event_type: ChaosEventType,
        **kwargs
    ) -> str:
        """Format event description from template.

        Args:
            event_type: The event type
            **kwargs: Values to substitute into template

        Returns:
            Formatted description string
        """
        template = self.get_template(event_type)
        desc_template = template.get("description_template", f"{event_type.value} event")
        try:
            return desc_template.format(**kwargs)
        except KeyError:
            return desc_template

    def get_response_action(self, event_type: ChaosEventType) -> Optional[dict]:
        """Get response action details for event type.

        Returns:
            Dict with response_agent_role and response_action_type, or None
        """
        template = self.get_template(event_type)
        if template.get("requires_response_action", False):
            return {
                "agent_role": template.get("response_agent_role"),
                "action_type": template.get("response_action_type"),
            }
        return None
