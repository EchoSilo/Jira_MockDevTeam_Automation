"""
Release Manager Agent - Coordinates release planning and version compliance.

The Release Manager operates at the organizational level, ensuring:
1. Fix versions exist for upcoming releases
2. All tickets in progress have fix versions assigned
3. Release schedules align with sprint cadence
4. PMs are notified of compliance issues

This agent does NOT directly access Jira. All actions are performed through
directives that get converted into PM actions during the planning phase.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
import pendulum

logger = logging.getLogger(__name__)

from .coordinator_agent import CoordinatorAgent
from ..services.llm_service import LLMService
from ..state import (
    SimulationState,
    ReleaseDirective,
    ReleaseVersion,
    ReleaseState,
)


class ReleaseManagerAgent(CoordinatorAgent):
    """
    Release Manager - coordinates version planning and compliance.

    Responsibilities:
    - Plan release versions based on sprint cadence
    - Detect tickets missing fix versions
    - Generate directives for PMs to create/assign versions
    - Track release health and compliance metrics
    """

    def __init__(
        self,
        agent_id: str,
        config: dict,
        llm_service: LLMService,
        settings: dict,
    ):
        """
        Initialize the Release Manager agent.

        Args:
            agent_id: Unique identifier (typically 'release_manager')
            config: Agent config from personas.yaml
            llm_service: LLM service for communications
            settings: Application settings (for release_management config)
        """
        super().__init__(agent_id, config, llm_service)
        self.settings = settings
        self.rm_settings = settings.get("release_management", {})

    async def analyze(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> dict:
        """
        Analyze release health and compliance.

        Checks:
        - Version coverage (% of in-progress items with fix version)
        - Unversioned tickets that need versions
        - Release schedule health
        - Upcoming releases

        Args:
            state: Current simulation state
            board_snapshot: Current Jira board state

        Returns:
            Analysis dict with compliance metrics and issues
        """
        analysis = {
            "planned_releases": [],
            "compliance_issues": [],
            "upcoming_releases": [],
            "version_coverage": 0.0,
            "unversioned_tickets": [],
            "metrics": {},
        }

        # Get current release state
        release_state = state.release_state

        # Sync existing Jira versions with internal state
        self._sync_jira_versions(state, board_snapshot.get("jira_versions", []))

        # Calculate version coverage
        total_tracked = 0
        versioned = 0
        unversioned = []

        # Check tickets in work statuses
        for status_key in ["in_progress", "code_review", "testing"]:
            for ticket in board_snapshot.get(status_key, []):
                # Skip Epics
                if ticket.get("type") == "Epic":
                    continue

                total_tracked += 1

                if ticket.get("fix_version"):
                    versioned += 1
                else:
                    unversioned.append(ticket)

        if total_tracked > 0:
            analysis["version_coverage"] = round(versioned / total_tracked * 100, 1)

        analysis["unversioned_tickets"] = unversioned
        analysis["planned_releases"] = [
            {
                "name": r.name,
                "target_date": r.target_date.isoformat() if r.target_date else None,
                "status": r.status,
                "created_in_jira": r.created_in_jira,
                "assigned_count": len(r.assigned_tickets),
            }
            for r in release_state.planned_releases
        ]

        # Calculate metrics
        analysis["metrics"] = {
            "total_tracked": total_tracked,
            "versioned": versioned,
            "unversioned": len(unversioned),
            "coverage_percent": analysis["version_coverage"],
            "planned_release_count": len(release_state.planned_releases),
            "sprint_day": state.sprint.sprint_day,
            "sprint_number": state.sprint.sprint_number,
        }

        # Check for releases that need to be created in Jira
        analysis["releases_needing_jira_creation"] = [
            r for r in release_state.planned_releases
            if not r.created_in_jira and r.status != "released"
        ]

        return analysis

    async def generate_directives(
        self,
        analysis: dict,
        state: SimulationState,
    ) -> list[ReleaseDirective]:
        """
        Generate directives for PMs based on release analysis.

        Directive types:
        - create_fix_version: PM should create a version in Jira
        - assign_fix_version: PM should assign version to a ticket
        - release_reminder: Notify PM of upcoming release

        Args:
            analysis: Results from analyze()
            state: Current simulation state

        Returns:
            List of directives for PM agents
        """
        directives = []

        # Get directive limits
        max_per_tick = self.rm_settings.get("directives", {}).get("max_per_tick", 3)

        # Priority 0: Release execution (highest priority - rollover + release)
        release_directives = self._generate_release_execution_directives(analysis, state)
        directives.extend(release_directives)

        # If release directives filled slots, return early
        if len(directives) >= max_per_tick:
            return directives[:max_per_tick]

        # Priority 1: Create missing versions in Jira
        directives.extend(
            self._generate_version_creation_directives(analysis, state)
        )

        # Priority 2: Assign versions to unversioned tickets
        remaining_slots = max_per_tick - len(directives)
        if remaining_slots > 0:
            version_directives = self._generate_version_assignment_directives(
                analysis, state, max_count=remaining_slots
            )
            directives.extend(version_directives)

        # Priority 3: Plan new releases if needed
        remaining_slots = max_per_tick - len(directives)
        if remaining_slots > 0:
            planning_directives = self._generate_release_planning_directives(
                analysis, state
            )
            directives.extend(planning_directives[:remaining_slots])

        return directives[:max_per_tick]

    def _generate_version_creation_directives(
        self,
        analysis: dict,
        state: SimulationState,
    ) -> list[ReleaseDirective]:
        """Generate directives to create fix versions in Jira."""
        directives = []

        releases_needing_creation = analysis.get("releases_needing_jira_creation", [])

        for release in releases_needing_creation:
            # Skip if directive already pending for this version
            if self._has_pending_directive(state, "create_fix_version", version_name=release.name):
                continue

            # Alternate between PMs for version creation
            pm_id = self._select_pm_for_version(release, state)

            if pm_id:
                directives.append(self.create_directive(
                    directive_type="create_fix_version",
                    target_pm_id=pm_id,
                    parameters={
                        "version_name": release.name,
                        "target_date": (
                            release.target_date.isoformat()
                            if release.target_date else None
                        ),
                        "reason": f"Release {release.name} planned but not created in Jira",
                    }
                ))

        return directives

    def _generate_version_assignment_directives(
        self,
        analysis: dict,
        state: SimulationState,
        max_count: int = 3,
    ) -> list[ReleaseDirective]:
        """Generate directives to assign versions to unversioned tickets."""
        directives = []

        unversioned = analysis.get("unversioned_tickets", [])
        current_release = state.release_state.get_current_release()

        if not current_release:
            return directives

        # Process unversioned tickets (limited per tick for gradual enforcement)
        for ticket in unversioned[:max_count]:
            # Skip if directive already pending for this ticket
            if self._has_pending_directive(state, "assign_fix_version", ticket_key=ticket["key"]):
                continue

            pm_id = self._get_pm_for_ticket(ticket, state)

            if pm_id:
                directives.append(self.create_directive(
                    directive_type="assign_fix_version",
                    target_pm_id=pm_id,
                    parameters={
                        "ticket_key": ticket["key"],
                        "version_name": current_release.name,
                        "reason": (
                            f"Ensuring release tracking - {ticket['key']} is "
                            f"{ticket['status']} and needs a target release"
                        ),
                    }
                ))

        return directives

    def _generate_release_planning_directives(
        self,
        analysis: dict,
        state: SimulationState,
    ) -> list[ReleaseDirective]:
        """Generate directives for release planning activities."""
        directives = []

        schedule = self.rm_settings.get("schedule", {})
        release_cadence = schedule.get("release_cadence_sprints", 2)
        planning_buffer = schedule.get("planning_buffer_sprints", 1)

        planned_releases = state.release_state.planned_releases
        unreleased_count = len([r for r in planned_releases if r.status != "released"])

        # Need to plan more releases?
        if unreleased_count < planning_buffer + 1:
            # Calculate next release version name
            next_version = self._calculate_next_version(state)

            # Skip if already pending directive for this version
            if self._has_pending_directive(state, "create_fix_version", version_name=next_version):
                return directives

            # Calculate target date based on sprint cadence
            target_date = self._calculate_release_target_date(state, release_cadence)

            # Add the planned release to state (RM's planning)
            new_release = ReleaseVersion(
                name=next_version,
                target_date=target_date,
                status="planned",
                sprint_number=state.sprint.sprint_number + release_cadence,
            )
            state.release_state.add_release(new_release)

            # Create directive for PM to create it in Jira
            pm_id = self._select_pm_for_version(new_release, state)
            if pm_id:
                directives.append(self.create_directive(
                    directive_type="create_fix_version",
                    target_pm_id=pm_id,
                    parameters={
                        "version_name": next_version,
                        "target_date": target_date.isoformat(),
                        "reason": f"Planning release {next_version} for Sprint {state.sprint.sprint_number + release_cadence}",
                    }
                ))

        return directives

    def _generate_release_execution_directives(
        self,
        analysis: dict,
        state: SimulationState,
    ) -> list[ReleaseDirective]:
        """
        Generate directives for releases that are due.

        Checks if any release has passed its target date and:
        1. Generates rollover_items directive for unfinished items
        2. Generates release_version directive to complete the release
        """
        directives = []
        now = pendulum.now("UTC")
        schedule = self.rm_settings.get("schedule", {})
        release_day = schedule.get("release_day", 5)  # Friday

        for release in state.release_state.planned_releases:
            # Skip already released
            if release.status == "released":
                continue

            # Skip if not created in Jira yet
            if not release.created_in_jira:
                continue

            # Check if release is due (past target date or end of target sprint)
            is_due = False
            if release.target_date and now >= release.target_date:
                is_due = True
            elif (release.sprint_number and
                  release.sprint_number <= state.sprint.sprint_number and
                  state.sprint.sprint_day >= release_day):
                is_due = True

            if not is_due:
                continue

            # Skip if we already have pending directives for this release
            if self._has_pending_directive(state, "release_version", version_name=release.name):
                continue
            if self._has_pending_directive(state, "rollover_items", version_name=release.name):
                continue

            # Find next release for rollover
            next_release = self._get_next_release(state, release)
            pm_id = self._select_pm_for_version(release, state)

            if not pm_id:
                continue

            # Generate rollover directive first (if there's a next release)
            if next_release and next_release.created_in_jira:
                directives.append(self.create_directive(
                    directive_type="rollover_items",
                    target_pm_id=pm_id,
                    parameters={
                        "from_version": release.name,
                        "to_version": next_release.name,
                        "reason": f"Rolling over unfinished items from {release.name} to {next_release.name}",
                    }
                ))

            # Generate release directive
            directives.append(self.create_directive(
                directive_type="release_version",
                target_pm_id=pm_id,
                parameters={
                    "version_name": release.name,
                    "transition_done_to_closed": True,
                    "reason": f"Releasing {release.name} - transitioning Done items to Closed",
                }
            ))

            # Only process one release per tick to avoid overwhelming
            break

        return directives

    def _get_next_release(
        self,
        state: SimulationState,
        current_release: ReleaseVersion,
    ) -> Optional[ReleaseVersion]:
        """
        Find the release to roll items into.

        For past-due releases, returns the current month's release.
        For future releases, returns the next in sequence.
        """
        now = pendulum.now("UTC")

        # If current release is past-due, use current month's release
        if current_release.target_date and now >= current_release.target_date:
            current_month = f"Release {now.strftime('%B %Y')}"
            for release in state.release_state.planned_releases:
                if release.name == current_month and release.status != "released":
                    return release
            # Current month's release not found - shouldn't happen if Jira has it
            return None

        # Otherwise find next sequential release
        found_current = False
        for release in state.release_state.planned_releases:
            if release.name == current_release.name:
                found_current = True
                continue
            if found_current and release.status != "released":
                return release
        return None

    def _select_pm_for_version(
        self,
        release: ReleaseVersion,
        state: SimulationState,
    ) -> Optional[str]:
        """
        Select which PM should handle a version.

        Alternates between team PMs based on release count.
        """
        # Count how many releases each PM has created
        # Alternate to balance workload
        release_count = len(state.release_state.planned_releases)

        if release_count % 2 == 0:
            return "alpha_pm"
        else:
            return "beta_pm"

    def _get_pm_for_ticket(
        self,
        ticket: dict,
        state: SimulationState,
    ) -> Optional[str]:
        """
        Determine which PM should handle a ticket based on assignee's team.
        """
        assignee_id = ticket.get("assignee_id")

        if assignee_id:
            # Try to find agent by Jira account ID
            # This would need access to personas, but we can use a simple heuristic
            # For now, alternate based on ticket key hash
            if hash(ticket.get("key", "")) % 2 == 0:
                return "alpha_pm"
            else:
                return "beta_pm"

        return "alpha_pm"  # Default

    def _has_pending_directive(
        self,
        state: SimulationState,
        directive_type: str,
        version_name: Optional[str] = None,
        ticket_key: Optional[str] = None,
    ) -> bool:
        """Check if a similar pending directive already exists."""
        for directive in state.release_state.active_directives:
            if directive.executed:
                continue
            if directive.directive_type != directive_type:
                continue
            # Check version_name match if specified
            if version_name and directive.parameters.get("version_name") != version_name:
                continue
            # Check ticket_key match if specified
            if ticket_key and directive.parameters.get("ticket_key") != ticket_key:
                continue
            return True
        return False

    def _parse_release_date(self, name: str) -> Optional[datetime]:
        """
        Parse a target date from a release name like 'Release October 2025'.

        Returns the last day of the specified month.
        """
        match = re.match(r"Release\s+(\w+)\s+(\d{4})", name)
        if not match:
            return None

        month_name, year = match.groups()
        try:
            # Parse the month name to get month number
            month = datetime.strptime(month_name, "%B").month
            year = int(year)

            # Calculate last day of the month
            if month == 12:
                return datetime(year + 1, 1, 1) - timedelta(days=1)
            return datetime(year, month + 1, 1) - timedelta(days=1)
        except ValueError:
            return None

    def _sync_jira_versions(
        self,
        state: SimulationState,
        jira_versions: list[dict],
    ) -> None:
        """
        Sync Jira versions with internal state.

        - Marks planned releases as created if they exist in Jira
        - Imports legacy named releases (e.g., 'Release October 2025')
        - Marks create_fix_version directives as executed if version exists
        """
        if not jira_versions:
            return

        jira_version_names = {v.get("name") for v in jira_versions if v.get("name")}
        jira_versions_map = {v.get("name"): v for v in jira_versions if v.get("name")}
        tracked_names = {r.name for r in state.release_state.planned_releases}

        # Mark planned releases as created if they exist in Jira
        for release in state.release_state.planned_releases:
            if release.name in jira_version_names:
                release.created_in_jira = True
                # Also update status if version is released in Jira
                jira_v = jira_versions_map.get(release.name, {})
                if jira_v.get("released", False) and release.status != "released":
                    release.status = "released"

        # Import legacy named releases from Jira that aren't tracked yet
        for jira_v in jira_versions:
            name = jira_v.get("name")
            if not name or name in tracked_names:
                continue

            # Parse release date from name (e.g., "Release October 2025")
            target_date = self._parse_release_date(name)
            if target_date:
                state.release_state.planned_releases.append(
                    ReleaseVersion(
                        name=name,
                        target_date=target_date,
                        status="released" if jira_v.get("released") else "planned",
                        created_in_jira=True,
                    )
                )

        # Mark create_fix_version directives as executed if version exists in Jira
        for directive in state.release_state.active_directives:
            if directive.executed:
                continue
            if directive.directive_type != "create_fix_version":
                continue
            version_name = directive.parameters.get("version_name")
            if version_name in jira_version_names:
                state.release_state.mark_directive_executed(
                    directive.directive_id,
                    f"Version {version_name} already exists in Jira (synced)"
                )

    def _calculate_next_version(self, state: SimulationState) -> str:
        """
        Calculate the next version name based on existing versions.

        Uses semantic versioning: vMAJOR.MINOR.PATCH
        """
        initial_version = self.rm_settings.get("initial_version", "1.0.0")
        planned = state.release_state.planned_releases

        if not planned:
            return f"v{initial_version}"

        # Find the highest version
        versions = []
        for release in planned:
            name = release.name
            if name.startswith("v"):
                name = name[1:]
            try:
                parts = name.split(".")
                if len(parts) >= 3:
                    versions.append((int(parts[0]), int(parts[1]), int(parts[2])))
            except (ValueError, IndexError):
                continue

        if not versions:
            return f"v{initial_version}"

        # Increment minor version
        highest = max(versions)
        new_version = (highest[0], highest[1] + 1, 0)

        return f"v{new_version[0]}.{new_version[1]}.{new_version[2]}"

    def _calculate_release_target_date(
        self,
        state: SimulationState,
        sprints_ahead: int,
    ) -> datetime:
        """
        Calculate target release date based on sprint cadence.

        Args:
            state: Current simulation state
            sprints_ahead: How many sprints until release

        Returns:
            Target release datetime
        """
        schedule = self.rm_settings.get("schedule", {})
        release_day = schedule.get("release_day", 5)  # Friday by default

        # Calculate days until release
        days_until_release = (
            (sprints_ahead * state.sprint.total_days) -
            state.sprint.sprint_day +
            release_day
        )

        return pendulum.now("UTC") + timedelta(days=days_until_release)

    async def generate_release_communication(
        self,
        release: ReleaseVersion,
        action: str,
    ) -> str:
        """
        Generate LLM-driven communication about a release.

        Args:
            release: The release being communicated about
            action: Type of communication ('planning', 'reminder', 'released')

        Returns:
            Generated communication text
        """
        prompts = {
            "planning": (
                f"As {self.display_name}, a Release Manager, write a brief "
                f"announcement about planning release {release.name} "
                f"targeting {release.target_date.strftime('%B %d, %Y') if release.target_date else 'TBD'}. "
                f"Keep it professional and concise (2-3 sentences)."
            ),
            "reminder": (
                f"As {self.display_name}, write a friendly reminder that "
                f"release {release.name} is approaching. "
                f"Ask PMs to ensure all tickets have fix versions assigned. "
                f"Keep it brief (2-3 sentences)."
            ),
            "released": (
                f"As {self.display_name}, write a brief announcement that "
                f"release {release.name} has been completed. "
                f"Keep it celebratory but professional (1-2 sentences)."
            ),
        }

        prompt = prompts.get(action, prompts["planning"])

        try:
            response = self.llm.generate_comment(
                agent_name=self.display_name,
                agent_role="Release Manager",
                agent_persona=self.persona,
                action_context=prompt,
                action_type="release_communication",
            )
            return response
        except Exception as e:
            # Fallback to template
            logger.warning(f"LLM release notes generation failed, using template: {e}")
            templates = {
                "planning": f"Planning release {release.name} for upcoming sprint cycle.",
                "reminder": f"Reminder: Release {release.name} is approaching. Please ensure all tickets have fix versions assigned.",
                "released": f"Release {release.name} has been completed successfully.",
            }
            return templates.get(action, templates["planning"])
