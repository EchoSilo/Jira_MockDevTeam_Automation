"""
Tests for chaos event generator.

Verifies probability-based event rolling and event creation logic.
"""

import pytest
import pendulum
from src.chaos.models import RandomEvent, ChaosConfig, ChaosEventType
from src.chaos.event_generator import RandomEventGenerator


@pytest.fixture
def basic_config():
    """Basic chaos configuration for testing."""
    return ChaosConfig(
        enabled=True,
        base_event_chance=0.5,  # 50% chance for testing
        event_probabilities={
            "production_outage": 0.1,
            "urgent_bug": 0.2,
            "team_absence": 0.1,
            "external_blocker": 0.3,
            "priority_shift": 0.2,
            "scope_change": 0.1
        }
    )


@pytest.fixture
def disabled_config():
    """Configuration with chaos disabled."""
    return ChaosConfig(
        enabled=False,
        base_event_chance=0.5,
        event_probabilities={
            "production_outage": 0.1,
            "urgent_bug": 0.2,
            "team_absence": 0.1,
            "external_blocker": 0.3,
            "priority_shift": 0.2,
            "scope_change": 0.1
        }
    )


@pytest.fixture
def sample_tickets():
    """Sample ticket keys for testing."""
    return ["PROJ-1", "PROJ-2", "PROJ-3", "PROJ-4", "PROJ-5"]


@pytest.fixture
def sample_agents():
    """Sample agent IDs for testing."""
    return ["agent_1", "agent_2", "agent_3", "agent_4"]


class TestRandomEventGenerator:
    """Test suite for RandomEventGenerator."""

    def test_init_with_seed(self, basic_config):
        """Generator initializes with deterministic seed."""
        gen1 = RandomEventGenerator(basic_config, seed=42)
        gen2 = RandomEventGenerator(basic_config, seed=42)

        assert gen1.config == basic_config
        assert gen2.config == basic_config
        # Both should have same internal rng state
        assert gen1.rng.random() == gen2.rng.random()

    def test_roll_returns_none_when_disabled(self, disabled_config, sample_tickets, sample_agents):
        """roll_for_event returns None when chaos is disabled."""
        generator = RandomEventGenerator(disabled_config, seed=42)
        event = generator.roll_for_event(sample_tickets, sample_agents)
        assert event is None

    def test_roll_returns_none_when_roll_fails(self, basic_config, sample_tickets, sample_agents):
        """roll_for_event returns None when dice roll exceeds base_event_chance."""
        # Use a seed that produces a high roll value
        generator = RandomEventGenerator(basic_config, seed=999)

        # Try multiple times to ensure at least some failures
        none_count = 0
        for _ in range(100):
            event = generator.roll_for_event(sample_tickets, sample_agents)
            if event is None:
                none_count += 1

        # With 50% chance, we should see some None results
        assert none_count > 0, "Expected some failed rolls"

    def test_roll_returns_event_when_roll_succeeds(self, basic_config, sample_tickets, sample_agents):
        """roll_for_event returns RandomEvent when dice roll succeeds."""
        # Use a seed that produces a low roll value
        generator = RandomEventGenerator(basic_config, seed=42)

        # Try multiple times to ensure at least some successes
        event_count = 0
        for _ in range(100):
            event = generator.roll_for_event(sample_tickets, sample_agents)
            if event is not None:
                event_count += 1
                # Verify it's a valid RandomEvent
                assert isinstance(event, RandomEvent)
                assert event.event_type in ChaosEventType
                assert len(event.affected_tickets) > 0
                assert event.severity in ["low", "medium", "high", "critical"]

        # With 50% chance, we should see some events
        assert event_count > 0, "Expected some successful rolls"

    def test_zero_probability_events_never_selected(self, sample_tickets, sample_agents):
        """Events with 0.0 probability are never selected."""
        config = ChaosConfig(
            enabled=True,
            base_event_chance=1.0,  # Always trigger
            event_probabilities={
                "production_outage": 0.0,  # Zero probability
                "urgent_bug": 0.5,
                "team_absence": 0.0,  # Zero probability
                "external_blocker": 0.5,
                "priority_shift": 0.0,  # Zero probability
                "scope_change": 0.0  # Zero probability
            }
        )

        generator = RandomEventGenerator(config, seed=42)

        # Run many iterations
        event_types = []
        for _ in range(100):
            event = generator.roll_for_event(sample_tickets, sample_agents)
            if event:
                event_types.append(event.event_type)

        # Should only see urgent_bug and external_blocker
        seen_types = set(event_types)
        assert ChaosEventType.production_outage not in seen_types
        assert ChaosEventType.team_absence not in seen_types
        assert ChaosEventType.priority_shift not in seen_types
        assert ChaosEventType.scope_change not in seen_types

    def test_weighted_selection_favors_higher_probabilities(self, sample_tickets, sample_agents):
        """Higher probability events are selected more frequently."""
        config = ChaosConfig(
            enabled=True,
            base_event_chance=1.0,  # Always trigger
            event_probabilities={
                "production_outage": 0.01,  # Very low
                "urgent_bug": 0.5,  # High
                "team_absence": 0.01,  # Very low
                "external_blocker": 0.01,  # Very low
                "priority_shift": 0.01,  # Very low
                "scope_change": 0.01  # Very low
            }
        )

        generator = RandomEventGenerator(config, seed=42)

        # Count event types over many iterations
        event_counts = {event_type: 0 for event_type in ChaosEventType}
        for _ in range(200):
            event = generator.roll_for_event(sample_tickets, sample_agents)
            if event:
                event_counts[event.event_type] += 1

        # urgent_bug should be most common
        assert event_counts[ChaosEventType.urgent_bug] > event_counts[ChaosEventType.production_outage]
        assert event_counts[ChaosEventType.urgent_bug] > event_counts[ChaosEventType.team_absence]

    def test_create_event_generates_valid_event(self, basic_config, sample_tickets, sample_agents):
        """_create_event generates RandomEvent with all required fields."""
        generator = RandomEventGenerator(basic_config, seed=42)

        event = generator._create_event(
            ChaosEventType.urgent_bug,
            sample_tickets,
            sample_agents
        )

        assert isinstance(event, RandomEvent)
        assert event.event_type == ChaosEventType.urgent_bug
        assert isinstance(event.triggered_at, pendulum.DateTime)
        assert len(event.affected_tickets) in [1, 2]  # urgent_bug affects 1-2 tickets
        assert all(ticket in sample_tickets for ticket in event.affected_tickets)
        assert event.severity in ["low", "medium", "high", "critical"]
        assert isinstance(event.description, str)
        assert len(event.description) > 0
        assert isinstance(event.details, dict)

    def test_production_outage_always_critical_severity(self, basic_config, sample_tickets, sample_agents):
        """production_outage events always have 'critical' severity."""
        generator = RandomEventGenerator(basic_config, seed=42)

        # Generate multiple production outage events
        for _ in range(10):
            event = generator._create_event(
                ChaosEventType.production_outage,
                sample_tickets,
                sample_agents
            )
            assert event.severity == "critical"
            assert len(event.affected_tickets) in [2, 3]  # 2-3 tickets

    def test_team_absence_has_duration(self, basic_config, sample_tickets, sample_agents):
        """team_absence events have duration_ticks > 1."""
        generator = RandomEventGenerator(basic_config, seed=42)

        # Generate multiple team absence events
        for _ in range(10):
            event = generator._create_event(
                ChaosEventType.team_absence,
                sample_tickets,
                sample_agents
            )
            assert event.duration_ticks > 1
            assert 2 <= event.duration_ticks <= 4
            assert len(event.affected_agents) == 1  # Affects one agent
            assert event.affected_agents[0] in sample_agents

    def test_external_blocker_affects_one_ticket(self, basic_config, sample_tickets, sample_agents):
        """external_blocker events affect exactly one ticket."""
        generator = RandomEventGenerator(basic_config, seed=42)

        event = generator._create_event(
            ChaosEventType.external_blocker,
            sample_tickets,
            sample_agents
        )
        assert len(event.affected_tickets) == 1
        assert event.affected_tickets[0] in sample_tickets

    def test_priority_shift_affects_tickets(self, basic_config, sample_tickets, sample_agents):
        """priority_shift events affect 1-2 tickets."""
        generator = RandomEventGenerator(basic_config, seed=42)

        event = generator._create_event(
            ChaosEventType.priority_shift,
            sample_tickets,
            sample_agents
        )
        assert len(event.affected_tickets) in [1, 2]
        assert all(ticket in sample_tickets for ticket in event.affected_tickets)

    def test_scope_change_affects_one_ticket(self, basic_config, sample_tickets, sample_agents):
        """scope_change events affect exactly one ticket."""
        generator = RandomEventGenerator(basic_config, seed=42)

        event = generator._create_event(
            ChaosEventType.scope_change,
            sample_tickets,
            sample_agents
        )
        assert len(event.affected_tickets) == 1
        assert event.affected_tickets[0] in sample_tickets

    def test_deterministic_with_same_seed(self, basic_config, sample_tickets, sample_agents):
        """Same seed produces same sequence of events."""
        gen1 = RandomEventGenerator(basic_config, seed=12345)
        gen2 = RandomEventGenerator(basic_config, seed=12345)

        events1 = []
        events2 = []

        for _ in range(50):
            e1 = gen1.roll_for_event(sample_tickets, sample_agents)
            e2 = gen2.roll_for_event(sample_tickets, sample_agents)

            # Both should produce same result (None or event type)
            if e1 is None:
                assert e2 is None
            else:
                assert e2 is not None
                assert e1.event_type == e2.event_type
                assert e1.affected_tickets == e2.affected_tickets
                assert e1.affected_agents == e2.affected_agents
