"""
Backlog prioritizer using LLM for business-value ranking.

Uses LLM to rank backlog items by business value and urgency,
with 24-hour caching to reduce costs.
"""

import json
import logging
from typing import List, Optional, TYPE_CHECKING
import pendulum

if TYPE_CHECKING:
    from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class BacklogPrioritizer:
    """Use LLM to prioritize backlog items by business value.

    Caches prioritization results to reduce LLM costs.
    """

    def __init__(
        self,
        llm_service: "LLMService",
        cache_hours: int = 24
    ):
        """Initialize prioritizer with LLM service.

        Args:
            llm_service: LLM service for generating prioritization
            cache_hours: Hours to cache prioritization results (default: 24)
        """
        self.llm = llm_service
        self.cache_hours = cache_hours
        self._cache: Optional[dict] = None
        self._cache_time: Optional[pendulum.DateTime] = None

    def prioritize(
        self,
        backlog: List[dict],
        sprint_goals: Optional[str] = None,
        force_refresh: bool = False
    ) -> List[dict]:
        """Prioritize backlog items using LLM.

        Args:
            backlog: List of items [{"key": "PROJ-100", "summary": "...", "type": "Story", ...}]
            sprint_goals: Optional sprint goals to prioritize towards
            force_refresh: Skip cache and re-prioritize

        Returns:
            Backlog sorted by priority (highest first)
        """
        # Check cache
        cache_key = self._get_cache_key(backlog)
        if not force_refresh and self._is_cache_valid(cache_key):
            logger.debug("Using cached backlog prioritization")
            return self._apply_cached_order(backlog)

        # Build prompt for LLM
        prompt = self._build_prioritization_prompt(backlog, sprint_goals)

        try:
            # Import litellm lazily to avoid import errors in tests
            import litellm

            # Use routine model (Haiku) for cost efficiency
            response = litellm.completion(
                model=self.llm.routine_model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response to get ordered keys
            response_text = response.choices[0].message.content.strip()
            ordered_keys = self._parse_prioritization_response(response_text)

            # Update cache
            self._update_cache(cache_key, ordered_keys)

            # Return backlog sorted by priority
            return self._sort_backlog(backlog, ordered_keys)

        except Exception as e:
            logger.error(f"LLM prioritization failed: {e}")
            # Fall back to type-based priority
            return self._fallback_prioritize(backlog)

    def _build_prioritization_prompt(
        self,
        backlog: List[dict],
        sprint_goals: Optional[str]
    ) -> str:
        """Build prompt for backlog prioritization.

        Args:
            backlog: List of backlog items
            sprint_goals: Optional sprint goals

        Returns:
            Formatted prompt for LLM
        """
        items_text = "\n".join([
            f"- {item['key']}: [{item.get('type', 'Story')}] {item.get('summary', 'No summary')}"
            for item in backlog[:20]  # Limit to 20 items for cost
        ])

        goals_text = f"\nSprint Goals: {sprint_goals}" if sprint_goals else ""

        return f"""You are a Product Manager prioritizing backlog items for the next sprint.

Rank these items by business value and urgency. Consider:
1. Bug fixes and blockers (highest priority)
2. Items aligned with sprint goals
3. Dependencies (items blocking others)
4. Customer impact

{goals_text}

Backlog items:
{items_text}

Return ONLY a JSON array of ticket keys in priority order (highest first):
["PROJ-100", "PROJ-101", ...]"""

    def _parse_prioritization_response(self, response: str) -> List[str]:
        """Parse LLM response to extract ordered keys.

        Args:
            response: LLM response text

        Returns:
            List of ticket keys in priority order (empty list on parse error)
        """
        try:
            # Find JSON array in response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse prioritization response: {e}")
        return []

    def _get_cache_key(self, backlog: List[dict]) -> str:
        """Generate cache key from backlog items.

        Args:
            backlog: List of backlog items

        Returns:
            Cache key string (sorted ticket keys joined with |)
        """
        keys = sorted([item.get("key", "") for item in backlog])
        return "|".join(keys)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is valid for this backlog.

        Args:
            cache_key: Cache key to check

        Returns:
            True if cache is valid and not expired
        """
        if self._cache is None or self._cache_time is None:
            return False
        if self._cache.get("key") != cache_key:
            return False
        age = pendulum.now("UTC") - self._cache_time
        return age.total_seconds() < self.cache_hours * 3600

    def _update_cache(self, cache_key: str, ordered_keys: List[str]) -> None:
        """Update cache with new prioritization.

        Args:
            cache_key: Cache key for this backlog
            ordered_keys: Ordered list of ticket keys
        """
        self._cache = {"key": cache_key, "order": ordered_keys}
        self._cache_time = pendulum.now("UTC")

    def _apply_cached_order(self, backlog: List[dict]) -> List[dict]:
        """Apply cached order to backlog.

        Args:
            backlog: List of backlog items

        Returns:
            Backlog sorted by cached order
        """
        if not self._cache:
            return backlog
        return self._sort_backlog(backlog, self._cache.get("order", []))

    def _sort_backlog(
        self,
        backlog: List[dict],
        ordered_keys: List[str]
    ) -> List[dict]:
        """Sort backlog by ordered keys.

        Args:
            backlog: List of backlog items
            ordered_keys: Ordered list of ticket keys

        Returns:
            Backlog sorted according to ordered_keys
        """
        key_order = {key: i for i, key in enumerate(ordered_keys)}
        max_order = len(ordered_keys)

        return sorted(
            backlog,
            key=lambda item: key_order.get(item.get("key", ""), max_order)
        )

    def _fallback_prioritize(self, backlog: List[dict]) -> List[dict]:
        """Fallback prioritization by type and priority field.

        Used when LLM fails or is unavailable.

        Args:
            backlog: List of backlog items

        Returns:
            Backlog sorted by type (Bug > Task > Story > Feature) then priority
        """
        type_priority = {"Bug": 0, "Task": 1, "Story": 2, "Feature": 3}
        priority_map = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}

        return sorted(
            backlog,
            key=lambda item: (
                type_priority.get(item.get("type", "Story"), 2),
                priority_map.get(item.get("priority", "Medium"), 2),
            )
        )
