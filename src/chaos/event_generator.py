"""
Random event generator for chaos injection.

Provides probability-based dice rolling to determine if and what type of
chaos event occurs each simulation tick.
"""

import random
from typing import Optional
import pendulum

from .models import RandomEvent, ChaosConfig, ChaosEventType


class RandomEventGenerator:
    """
    Generates random chaos events based on configured probabilities.

    Uses two-stage process:
    1. Roll against base_event_chance to determine IF event occurs
    2. Use weighted selection to determine WHICH event type
    """

    def __init__(self, config: ChaosConfig, seed: Optional[int] = None):
        """
        Initialize generator with configuration and optional seed.

        Args:
            config: Chaos configuration with probabilities
            seed: Random seed for deterministic testing (None = non-deterministic)
        """
        self.config = config
        self.rng = random.Random(seed)

    def roll_for_event(
        self,
        current_tickets: list[str],
        current_agents: list[str]
    ) -> Optional[RandomEvent]:
        """
        Roll dice to determine if chaos event occurs this tick.

        Two-stage process:
        1. Roll against base_event_chance (e.g., 0.1 = 10% chance)
        2. If triggered, use weighted random.choices() to select event type
        3. Create event with appropriate details

        Args:
            current_tickets: Available ticket keys for event targeting
            current_agents: Available agent IDs for event targeting

        Returns:
            RandomEvent if triggered, None otherwise
        """
        # Stage 1: Check if chaos is enabled
        if not self.config.enabled:
            return None

        # Stage 2: Roll against base event chance
        roll = self.rng.random()
        if roll > self.config.base_event_chance:
            return None  # Roll failed, no event this tick

        # Stage 3: Filter to enabled events (probability > 0)
        enabled_events = {
            event_type: prob
            for event_type, prob in self.config.event_probabilities.items()
            if prob > 0.0
        }

        if not enabled_events:
            return None  # No events configured

        # Stage 4: Weighted random selection
        event_types = list(enabled_events.keys())
        weights = list(enabled_events.values())

        selected_type_str = self.rng.choices(event_types, weights=weights, k=1)[0]
        selected_type = ChaosEventType[selected_type_str]

        # Stage 5: Create event with details
        return self._create_event(selected_type, current_tickets, current_agents)

    def _create_event(
        self,
        event_type: ChaosEventType,
        tickets: list[str],
        agents: list[str]
    ) -> RandomEvent:
        """
        Create RandomEvent with event-type-specific details.

        Each event type has different targeting and severity rules:
        - production_outage: 2-3 tickets, always critical
        - urgent_bug: 1-2 tickets, high severity
        - team_absence: 1 agent, 2-4 tick duration
        - external_blocker: 1 ticket, medium severity
        - priority_shift: 1-2 tickets, medium severity
        - scope_change: 1 ticket, high severity

        Args:
            event_type: Type of chaos event
            tickets: Available tickets for targeting
            agents: Available agents for targeting

        Returns:
            Fully populated RandomEvent
        """
        affected_tickets = []
        affected_agents = []
        severity = "medium"
        duration_ticks = 1
        details = {}

        if event_type == ChaosEventType.production_outage:
            # Critical severity, affects 2-3 tickets
            num_tickets = self.rng.randint(2, 3)
            affected_tickets = self.rng.sample(tickets, min(num_tickets, len(tickets)))
            severity = "critical"
            description = f"Production outage detected affecting {len(affected_tickets)} ticket(s)"
            details = {
                "impact": "high",
                "requires_immediate_action": True
            }

        elif event_type == ChaosEventType.urgent_bug:
            # High severity, affects 1-2 tickets
            num_tickets = self.rng.randint(1, 2)
            affected_tickets = self.rng.sample(tickets, min(num_tickets, len(tickets)))
            severity = "high"
            description = f"Urgent bug discovered in {len(affected_tickets)} ticket(s)"
            details = {
                "impact": "medium-high",
                "requires_prioritization": True
            }

        elif event_type == ChaosEventType.team_absence:
            # Affects 1 agent, lasts 2-4 ticks
            if agents:
                affected_agents = [self.rng.choice(agents)]
                duration_ticks = self.rng.randint(2, 4)
                severity = "medium"
                description = f"Team member {affected_agents[0]} unexpectedly unavailable for {duration_ticks} tick(s)"
                details = {
                    "absence_reason": "unplanned",
                    "duration": duration_ticks
                }
            else:
                # Fallback if no agents available
                description = "Team absence event triggered but no agents available"

        elif event_type == ChaosEventType.external_blocker:
            # Affects 1 ticket
            if tickets:
                affected_tickets = [self.rng.choice(tickets)]
                severity = "medium"
                description = f"External blocker identified for ticket {affected_tickets[0]}"
                details = {
                    "blocker_type": "external_dependency",
                    "estimated_resolution": "unknown"
                }
            else:
                description = "External blocker event triggered but no tickets available"

        elif event_type == ChaosEventType.priority_shift:
            # Affects 1-2 tickets
            num_tickets = self.rng.randint(1, 2)
            affected_tickets = self.rng.sample(tickets, min(num_tickets, len(tickets)))
            severity = "medium"
            description = f"Priority shift requested for {len(affected_tickets)} ticket(s)"
            details = {
                "reason": "stakeholder_request",
                "urgency": "high"
            }

        elif event_type == ChaosEventType.scope_change:
            # Affects 1 ticket
            if tickets:
                affected_tickets = [self.rng.choice(tickets)]
                severity = "high"
                description = f"Scope change requested for ticket {affected_tickets[0]}"
                details = {
                    "change_type": "requirements_update",
                    "impact": "high"
                }
            else:
                description = "Scope change event triggered but no tickets available"

        return RandomEvent(
            event_type=event_type,
            triggered_at=pendulum.now("UTC"),
            affected_tickets=affected_tickets,
            affected_agents=affected_agents,
            description=description,
            severity=severity,
            details=details,
            duration_ticks=duration_ticks
        )
