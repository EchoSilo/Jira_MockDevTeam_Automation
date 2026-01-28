"""
Tests for confidence tracker that measures scenario script fidelity.

RED phase: These tests should fail until we implement the tracker.
"""

import pytest
import pendulum
from src.chaos.confidence_tracker import ConfidenceTracker, ConfidenceScore
from src.scenarios.sprint_scenario import (
    SprintScenario,
    ScenarioArchetype,
    ScriptDay,
    ScriptEvent,
    EventType,
)


@pytest.fixture
def empty_scenario():
    """Scenario with no events."""
    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.SMOOTH_SPRINT,
        archetype_name="Smooth Sprint",
        target_completion_rate=0.8,
        script=[],
        sprint_items=["PROJ-1", "PROJ-2"],
    )


@pytest.fixture
def perfect_execution_scenario():
    """Scenario where all events executed as planned."""
    events = [
        ScriptEvent(
            event_type=EventType.DEV_PICKUP,
            day=1,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.DEV_PROGRESS,
            day=2,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.PUSH_TO_REVIEW,
            day=3,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.QA_APPROVE,
            day=4,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
    ]

    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.SMOOTH_SPRINT,
        archetype_name="Smooth Sprint",
        target_completion_rate=0.8,
        script=[
            ScriptDay(day=1, events=[events[0]]),
            ScriptDay(day=2, events=[events[1]]),
            ScriptDay(day=3, events=[events[2]]),
            ScriptDay(day=4, events=[events[3]]),
        ],
        sprint_items=["PROJ-1"],
    )


@pytest.fixture
def all_adapted_scenario():
    """Scenario where all events were adapted."""
    events = [
        ScriptEvent(
            event_type=EventType.DEV_PICKUP,
            day=1,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.DEV_PROGRESS,
            day=2,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.PUSH_TO_REVIEW,
            day=3,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.QA_APPROVE,
            day=4,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
    ]

    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.BLOCKER_HEAVY,
        archetype_name="Blocker-Heavy Sprint",
        target_completion_rate=0.5,
        script=[
            ScriptDay(day=1, events=[events[0]]),
            ScriptDay(day=2, events=[events[1]]),
            ScriptDay(day=3, events=[events[2]]),
            ScriptDay(day=4, events=[events[3]]),
        ],
        sprint_items=["PROJ-1"],
    )


@pytest.fixture
def mixed_execution_scenario():
    """Scenario with mix of executed and adapted events."""
    events = [
        ScriptEvent(
            event_type=EventType.DEV_PICKUP,
            day=1,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.DEV_PROGRESS,
            day=2,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.PUSH_TO_REVIEW,
            day=3,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.QA_APPROVE,
            day=4,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.SPRINT_COMPLETE,
            day=7,
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
    ]

    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.SMOOTH_SPRINT,
        archetype_name="Smooth Sprint",
        target_completion_rate=0.8,
        script=[
            ScriptDay(day=1, events=[events[0]]),
            ScriptDay(day=2, events=[events[1]]),
            ScriptDay(day=3, events=[events[2]]),
            ScriptDay(day=4, events=[events[3]]),
            ScriptDay(day=7, events=[events[4]]),
        ],
        sprint_items=["PROJ-1"],
    )


@pytest.fixture
def positive_adaptation_scenario():
    """Scenario with early completion (positive adaptation)."""
    events = [
        ScriptEvent(
            event_type=EventType.DEV_PICKUP,
            day=1,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.DEV_PROGRESS,
            day=2,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={"adapted": False, "external_override": False},
        ),
        # This was supposed to take 3 more days, but completed early
        ScriptEvent(
            event_type=EventType.QA_APPROVE,
            day=3,
            ticket_key="PROJ-1",
            executed=True,
            execution_result={
                "adapted": True,
                "external_override": False,
                "positive_adaptation": True,
                "target_status": "Done",
            },
        ),
    ]

    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.SMOOTH_SPRINT,
        archetype_name="Smooth Sprint",
        target_completion_rate=0.9,
        script=[
            ScriptDay(day=1, events=[events[0]]),
            ScriptDay(day=2, events=[events[1]]),
            ScriptDay(day=3, events=[events[2]]),
        ],
        sprint_items=["PROJ-1"],
    )


@pytest.fixture
def accept_reality_trigger_scenario():
    """Scenario that should trigger accept reality mode."""
    # Low fidelity (< 0.7) and 3+ external overrides
    events = [
        ScriptEvent(
            event_type=EventType.DEV_PICKUP,
            day=1,
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.DEV_PROGRESS,
            day=2,
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.PUSH_TO_REVIEW,
            day=3,
            executed=True,
            execution_result={"adapted": True, "external_override": True},
        ),
        ScriptEvent(
            event_type=EventType.QA_APPROVE,
            day=4,
            executed=True,
            execution_result={"adapted": True, "external_override": False},
        ),
        ScriptEvent(
            event_type=EventType.SPRINT_COMPLETE,
            day=7,
            executed=True,
            execution_result={"adapted": True, "external_override": False},
        ),
    ]

    return SprintScenario(
        sprint_id=1,
        sprint_name="Sprint 1",
        archetype=ScenarioArchetype.BLOCKER_HEAVY,
        archetype_name="Blocker-Heavy Sprint",
        target_completion_rate=0.5,
        script=[
            ScriptDay(day=1, events=[events[0]]),
            ScriptDay(day=2, events=[events[1]]),
            ScriptDay(day=3, events=[events[2]]),
            ScriptDay(day=4, events=[events[3]]),
            ScriptDay(day=7, events=[events[4]]),
        ],
        sprint_items=["PROJ-1"],
    )


class TestConfidenceScore:
    """Test ConfidenceScore dataclass."""

    def test_confidence_score_creation(self):
        """Test creating a confidence score."""
        score = ConfidenceScore(
            script_fidelity=0.8,
            total_events=10,
            executed_as_planned=8,
            adapted_events=2,
            external_overrides=1,
            positive_adaptations=0,
            accept_reality=False,
        )

        assert score.script_fidelity == 0.8
        assert score.total_events == 10
        assert score.executed_as_planned == 8
        assert score.adapted_events == 2
        assert score.external_overrides == 1
        assert score.positive_adaptations == 0
        assert score.accept_reality is False


class TestConfidenceTracker:
    """Test ConfidenceTracker confidence calculation."""

    def test_tracker_initialization(self):
        """Test tracker initializes with default thresholds."""
        tracker = ConfidenceTracker()
        assert tracker.threshold == 0.7
        assert tracker.override_limit == 3

    def test_tracker_custom_thresholds(self):
        """Test tracker with custom thresholds."""
        tracker = ConfidenceTracker(threshold=0.8, override_limit=5)
        assert tracker.threshold == 0.8
        assert tracker.override_limit == 5

    def test_perfect_execution_fidelity(self, perfect_execution_scenario):
        """Test perfect execution gives fidelity of 1.0."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(perfect_execution_scenario)

        assert score.script_fidelity == 1.0
        assert score.total_events == 4
        assert score.executed_as_planned == 4
        assert score.adapted_events == 0
        assert score.external_overrides == 0
        assert score.positive_adaptations == 0
        assert score.accept_reality is False

    def test_all_adapted_fidelity(self, all_adapted_scenario):
        """Test all adapted events gives fidelity of 0.0."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(all_adapted_scenario)

        assert score.script_fidelity == 0.0
        assert score.total_events == 4
        assert score.executed_as_planned == 0
        assert score.adapted_events == 4
        assert score.external_overrides == 4
        assert score.positive_adaptations == 0
        assert score.accept_reality is True  # < 0.7 and >= 3 overrides

    def test_mixed_execution_fidelity(self, mixed_execution_scenario):
        """Test mixed execution gives proportional fidelity."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(mixed_execution_scenario)

        # 3 executed as planned, 2 adapted = 3/5 = 0.6
        assert score.script_fidelity == 0.6
        assert score.total_events == 5
        assert score.executed_as_planned == 3
        assert score.adapted_events == 2
        assert score.external_overrides == 1
        assert score.positive_adaptations == 0
        assert score.accept_reality is False  # Only 1 override, need 3

    def test_positive_adaptation_doesnt_hurt_fidelity(self, positive_adaptation_scenario):
        """Test early completion doesn't reduce fidelity."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(positive_adaptation_scenario)

        # 2 executed as planned, 1 positive adaptation = (2+1)/3 = 1.0
        assert score.script_fidelity == 1.0
        assert score.total_events == 3
        assert score.executed_as_planned == 2
        assert score.adapted_events == 1
        assert score.external_overrides == 0
        assert score.positive_adaptations == 1
        assert score.accept_reality is False

    def test_empty_scenario_perfect_fidelity(self, empty_scenario):
        """Test empty scenario has perfect fidelity."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(empty_scenario)

        assert score.script_fidelity == 1.0
        assert score.total_events == 0
        assert score.executed_as_planned == 0
        assert score.adapted_events == 0
        assert score.external_overrides == 0
        assert score.positive_adaptations == 0
        assert score.accept_reality is False

    def test_accept_reality_triggers(self, accept_reality_trigger_scenario):
        """Test accept reality triggers at < 0.7 with 3+ overrides."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(accept_reality_trigger_scenario)

        # All 5 adapted, 3 external overrides
        assert score.script_fidelity == 0.0
        assert score.total_events == 5
        assert score.executed_as_planned == 0
        assert score.adapted_events == 5
        assert score.external_overrides == 3
        assert score.accept_reality is True

    def test_accept_reality_not_triggered_low_fidelity_but_few_overrides(
        self, mixed_execution_scenario
    ):
        """Test accept reality doesn't trigger if < 3 overrides even if low fidelity."""
        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(mixed_execution_scenario)

        # Fidelity is 0.6 (< 0.7) but only 1 override (< 3)
        assert score.script_fidelity == 0.6
        assert score.external_overrides == 1
        assert score.accept_reality is False

    def test_accept_reality_not_triggered_many_overrides_but_high_fidelity(self):
        """Test accept reality doesn't trigger if >= 0.7 fidelity even with 3+ overrides."""
        # 7 executed as planned, 3 adapted with overrides = 7/10 = 0.7
        events = [
            ScriptEvent(
                event_type=EventType.DEV_PICKUP,
                day=i,
                executed=True,
                execution_result={"adapted": False, "external_override": False},
            )
            for i in range(1, 8)
        ] + [
            ScriptEvent(
                event_type=EventType.DEV_PICKUP,
                day=i,
                executed=True,
                execution_result={"adapted": True, "external_override": True},
            )
            for i in range(8, 11)
        ]

        scenario = SprintScenario(
            sprint_id=1,
            sprint_name="Sprint 1",
            archetype=ScenarioArchetype.SMOOTH_SPRINT,
            archetype_name="Smooth Sprint",
            target_completion_rate=0.8,
            script=[ScriptDay(day=1, events=events)],
            sprint_items=["PROJ-1"],
        )

        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(scenario)

        assert score.script_fidelity == 0.7
        assert score.external_overrides == 3
        assert score.accept_reality is False  # Fidelity exactly at threshold

    def test_should_accept_reality_convenience_method(self, accept_reality_trigger_scenario):
        """Test should_accept_reality convenience method."""
        tracker = ConfidenceTracker()
        assert tracker.should_accept_reality(accept_reality_trigger_scenario) is True

    def test_should_accept_reality_false(self, perfect_execution_scenario):
        """Test should_accept_reality returns False for good execution."""
        tracker = ConfidenceTracker()
        assert tracker.should_accept_reality(perfect_execution_scenario) is False

    def test_unexecuted_events_not_counted(self):
        """Test that unexecuted events are included in total but don't affect counts."""
        events = [
            ScriptEvent(
                event_type=EventType.DEV_PICKUP,
                day=1,
                executed=True,
                execution_result={"adapted": False, "external_override": False},
            ),
            ScriptEvent(
                event_type=EventType.DEV_PROGRESS,
                day=2,
                executed=False,  # Not executed yet
            ),
            ScriptEvent(
                event_type=EventType.PUSH_TO_REVIEW,
                day=3,
                executed=False,  # Not executed yet
            ),
        ]

        scenario = SprintScenario(
            sprint_id=1,
            sprint_name="Sprint 1",
            archetype=ScenarioArchetype.SMOOTH_SPRINT,
            archetype_name="Smooth Sprint",
            target_completion_rate=0.8,
            script=[ScriptDay(day=1, events=events)],
            sprint_items=["PROJ-1"],
        )

        tracker = ConfidenceTracker()
        score = tracker.calculate_confidence(scenario)

        # Only 1 executed, but 3 total
        assert score.total_events == 3
        assert score.executed_as_planned == 1
        assert score.adapted_events == 0
        # Fidelity based only on executed events: 1/3
        assert score.script_fidelity == pytest.approx(1.0 / 3.0)
