"""Centralized NYSE trading calendar utilities.

Uses the exchange-calendars library for accurate NYSE holiday/session data
instead of naive weekend-only checks.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import List

import exchange_calendars as xcals
import pandas as pd


@lru_cache(maxsize=1)
def _get_nyse_calendar() -> xcals.ExchangeCalendar:
    """Return a cached NYSE calendar instance."""
    return xcals.get_calendar("XNYS")


def is_trading_day(date_str: str) -> bool:
    """Check whether *date_str* (YYYY-MM-DD) is an NYSE trading session.

    Returns False for weekends **and** NYSE holidays (e.g. Good Friday,
    MLK Day, etc.).
    """
    cal = _get_nyse_calendar()
    ts = pd.Timestamp(date_str)
    return cal.is_session(ts)


def get_trading_days(start: str, end: str) -> List[str]:
    """Return a list of NYSE trading-day strings between *start* and *end* (inclusive).

    Replaces ``pd.date_range(freq="B")`` which only skips weekends.
    """
    cal = _get_nyse_calendar()
    ts_start = pd.Timestamp(start)
    ts_end = pd.Timestamp(end)

    # Clamp to calendar bounds to avoid out-of-range errors
    if ts_start < cal.first_session:
        ts_start = cal.first_session
    if ts_end > cal.last_session:
        ts_end = cal.last_session

    if ts_start > ts_end:
        return []

    sessions = cal.sessions_in_range(ts_start, ts_end)
    return [s.strftime("%Y-%m-%d") for s in sessions]


def get_previous_trading_day(date_str: str) -> str:
    """Return the NYSE trading day immediately before *date_str*.

    If *date_str* itself is not a session the calendar still finds the
    previous valid session (handles weekends, holidays, etc.).
    """
    cal = _get_nyse_calendar()
    ts = pd.Timestamp(date_str)
    prev = cal.previous_session(ts)
    return prev.strftime("%Y-%m-%d")


def adjust_to_trading_day(date_str: str, forward: bool = True) -> str:
    """Snap *date_str* to the nearest NYSE trading day.

    If *date_str* is already a trading day it is returned unchanged.
    Otherwise moves forward (next session) or backward (previous session)
    depending on the *forward* flag.
    """
    cal = _get_nyse_calendar()
    ts = pd.Timestamp(date_str)

    if cal.is_session(ts):
        return date_str

    if forward:
        return cal.next_session(ts).strftime("%Y-%m-%d")
    else:
        return cal.previous_session(ts).strftime("%Y-%m-%d")
