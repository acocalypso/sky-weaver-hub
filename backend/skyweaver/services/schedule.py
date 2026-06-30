from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astral import Depression, Observer
from astral.sun import SunDirection, dawn, dusk, sunrise, sunset, time_at_elevation


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_clock(value: str | None, fallback: time) -> time:
    if not value:
        return fallback
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute[:2]))
    except (TypeError, ValueError):
        return fallback


def _fixed_transition(day: date, value: str | None, tz: ZoneInfo, fallback: time) -> datetime:
    return datetime.combine(day, _parse_clock(value, fallback), tzinfo=tz)


def _observer(schedule: dict[str, Any]) -> Observer:
    return Observer(latitude=float(schedule.get("latitude", 0)), longitude=float(schedule.get("longitude", 0)))


def _sun_angle(schedule: dict[str, Any], key: str) -> float:
    value = schedule.get(key)
    if value is None:
        value = schedule.get("sun_angle", -6)
    return float(value)


def _sun_transition(day: date, schedule: dict[str, Any], direction: SunDirection, tz: ZoneInfo, angle_key: str) -> datetime | None:
    observer = _observer(schedule)
    try:
        return time_at_elevation(observer, _sun_angle(schedule, angle_key), date=day, direction=direction, tzinfo=tz)
    except (TypeError, ValueError):
        return None


def _event_transition(day: date, schedule: dict[str, Any], mode: str, tz: ZoneInfo) -> datetime | None:
    observer = _observer(schedule)
    try:
        if mode == "sunset":
            return sunset(observer, date=day, tzinfo=tz)
        if mode == "sunrise":
            return sunrise(observer, date=day, tzinfo=tz)
        if mode == "civil_dusk":
            return dusk(observer, date=day, depression=Depression.CIVIL, tzinfo=tz)
        if mode == "nautical_dusk":
            return dusk(observer, date=day, depression=Depression.NAUTICAL, tzinfo=tz)
        if mode == "astronomical_dusk":
            return dusk(observer, date=day, depression=Depression.ASTRONOMICAL, tzinfo=tz)
        if mode == "civil_dawn":
            return dawn(observer, date=day, depression=Depression.CIVIL, tzinfo=tz)
        if mode == "nautical_dawn":
            return dawn(observer, date=day, depression=Depression.NAUTICAL, tzinfo=tz)
        if mode == "astronomical_dawn":
            return dawn(observer, date=day, depression=Depression.ASTRONOMICAL, tzinfo=tz)
    except (TypeError, ValueError):
        return None
    return None


def _start_for(day: date, schedule: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    mode = str(schedule.get("start_mode") or "sun_angle")
    if mode == "manual":
        return None
    if mode == "fixed":
        return _fixed_transition(day, schedule.get("fixed_start_time"), tz, time(18, 0))
    if mode == "sun_angle":
        return _sun_transition(day, schedule, SunDirection.SETTING, tz, "start_sun_angle")
    return _event_transition(day, schedule, mode, tz)


def _end_for(day: date, schedule: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    mode = str(schedule.get("end_mode") or "sun_angle")
    if mode == "manual":
        return None
    if mode == "fixed":
        return _fixed_transition(day, schedule.get("fixed_end_time"), tz, time(6, 0))
    if mode == "sun_angle":
        return _sun_transition(day, schedule, SunDirection.RISING, tz, "end_sun_angle")
    return _event_transition(day, schedule, mode, tz)


def active_window(schedule: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    tz = _tz(str(schedule.get("timezone", "UTC")))
    local_now = (now or datetime.now(tz)).astimezone(tz)
    today = local_now.date()

    candidates: list[tuple[datetime, datetime]] = []
    for start_day in (today - timedelta(days=1), today):
        start = _start_for(start_day, schedule, tz)
        end = _end_for(start_day, schedule, tz)
        if start is None or end is None:
            continue
        if end <= start:
            end = _end_for(start_day + timedelta(days=1), schedule, tz) or (end + timedelta(days=1))
        candidates.append((start, end))

    active = next(((start, end) for start, end in candidates if start <= local_now < end), None)
    future_starts = sorted(start for start, _end in candidates if start > local_now)
    future_ends = sorted(end for _start, end in candidates if end > local_now)

    if active:
        start, end = active
        next_transition = end
        next_state = "inactive"
    else:
        next_transition = future_starts[0] if future_starts else None
        next_state = "active" if next_transition else "unknown"
        start = None
        end = future_ends[0] if future_ends else None

    return {
        "enabled": bool(schedule.get("enabled")),
        "active": bool(schedule.get("enabled")) and active is not None,
        "now": local_now.isoformat(),
        "window_start": start.isoformat() if start else None,
        "window_end": end.isoformat() if end else None,
        "next_transition_at": next_transition.isoformat() if next_transition else None,
        "next_state": next_state,
        "timezone": str(tz),
    }


def should_capture_now(schedule: dict[str, Any], now: datetime | None = None) -> bool:
    return active_window(schedule, now)["active"]
