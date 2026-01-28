"""Business hours validation for simulation endpoints."""
import logging
from dataclasses import dataclass
from typing import Optional

import pendulum
import yaml
from fastapi import HTTPException, Depends

from .clock import Clock, RealClock

logger = logging.getLogger(__name__)


@dataclass
class BusinessHoursConfig:
    """Configuration for business hours validation."""
    timezone: str = "America/New_York"
    days: list[int] = None  # 1=Monday, 7=Sunday
    start_hour: int = 9
    end_hour: int = 17

    def __post_init__(self):
        if self.days is None:
            self.days = [1, 2, 3, 4, 5]  # Monday-Friday


_config_cache: Optional[BusinessHoursConfig] = None


def load_business_hours_config() -> BusinessHoursConfig:
    """Load business hours config from settings.yaml."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    try:
        with open("config/settings.yaml", "r") as f:
            settings = yaml.safe_load(f)

        schedule = settings.get("schedule", {})
        _config_cache = BusinessHoursConfig(
            timezone=settings.get("simulation", {}).get("work_hours", {}).get("timezone", "America/New_York"),
            days=schedule.get("days", [1, 2, 3, 4, 5]),
            start_hour=schedule.get("start_hour", 9),
            end_hour=schedule.get("end_hour", 17),
        )
    except Exception as e:
        logger.warning(f"Failed to load business hours config, using defaults: {e}")
        _config_cache = BusinessHoursConfig()

    return _config_cache


def get_clock() -> Clock:
    """FastAPI dependency to get the clock."""
    return RealClock()


def validate_business_hours(
    clock: Clock = Depends(get_clock),
) -> None:
    """
    FastAPI dependency that rejects requests outside business hours.

    Raises HTTPException 403 if current time is outside configured
    business hours (default M-F 9am-5pm in America/New_York).
    """
    config = load_business_hours_config()
    now_utc = clock.now()

    # Convert to local timezone for business hours check
    local_time = now_utc.in_timezone(config.timezone)

    # Check day of week (Pendulum: 1=Monday, 7=Sunday)
    if local_time.day_of_week not in config.days:
        day_name = local_time.format("dddd")
        raise HTTPException(
            status_code=403,
            detail=f"Simulation runs Monday-Friday only. Today is {day_name}.",
        )

    # Check time range
    if not (config.start_hour <= local_time.hour < config.end_hour):
        current_time = local_time.format("HH:mm")
        raise HTTPException(
            status_code=403,
            detail=f"Simulation runs {config.start_hour}:00-{config.end_hour}:00 only. "
                   f"Current time: {current_time} {config.timezone}.",
        )

    # Log DST status for debugging
    _check_dst_transition(local_time, config.timezone)


# DST tracking for logging transitions
_last_dst_status: Optional[bool] = None


def _check_dst_transition(local_time: pendulum.DateTime, timezone: str) -> None:
    """Check for DST transition and log if detected."""
    global _last_dst_status

    current_dst = local_time.is_dst()

    if _last_dst_status is not None and current_dst != _last_dst_status:
        transition_type = "spring forward" if current_dst else "fall back"
        logger.warning(
            f"DST transition detected ({transition_type}) at "
            f"{local_time.format('YYYY-MM-DD HH:mm:ss ZZ')} in {timezone}"
        )

    _last_dst_status = current_dst


def reset_config_cache() -> None:
    """Reset config cache (for testing)."""
    global _config_cache, _last_dst_status
    _config_cache = None
    _last_dst_status = None
