from datetime import datetime
from zoneinfo import ZoneInfo

from skyweaver.services.schedule import active_window, should_capture_now


def base_schedule(**overrides):
    schedule = {
        "enabled": True,
        "start_mode": "fixed",
        "end_mode": "fixed",
        "fixed_start_time": "22:00",
        "fixed_end_time": "06:00",
        "sun_angle": -6,
        "start_sun_angle": -8,
        "end_sun_angle": -2,
        "timezone": "Europe/Berlin",
        "latitude": 49.1012,
        "longitude": 10.121,
    }
    schedule.update(overrides)
    return schedule


def test_fixed_overnight_window_is_active_after_midnight():
    now = datetime(2026, 6, 30, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))

    preview = active_window(base_schedule(), now)

    assert preview["active"] is True
    assert preview["next_state"] == "inactive"
    assert preview["window_start"] == "2026-06-29T22:00:00+02:00"
    assert preview["window_end"] == "2026-06-30T06:00:00+02:00"
    assert should_capture_now(base_schedule(), now) is True


def test_disabled_schedule_reports_window_but_not_active():
    now = datetime(2026, 6, 30, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))

    preview = active_window(base_schedule(enabled=False), now)

    assert preview["enabled"] is False
    assert preview["active"] is False
    assert preview["window_start"] == "2026-06-29T22:00:00+02:00"
    assert preview["window_end"] == "2026-06-30T06:00:00+02:00"
    assert should_capture_now(base_schedule(enabled=False), now) is False


def test_named_twilight_to_sunrise_window_is_active_overnight():
    schedule = base_schedule(start_mode="nautical_dusk", end_mode="sunrise")
    now = datetime(2026, 6, 30, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))

    preview = active_window(schedule, now)

    assert preview["active"] is True
    assert preview["window_start"].startswith("2026-06-29T")
    assert preview["window_end"].startswith("2026-06-30T")
    assert preview["window_start"] < now.isoformat() < preview["window_end"]


def test_independent_start_and_end_sun_angles_change_transitions():
    now = datetime(2026, 6, 30, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    split_angles = base_schedule(start_mode="sun_angle", end_mode="sun_angle", start_sun_angle=-12, end_sun_angle=-3)
    same_angles = base_schedule(start_mode="sun_angle", end_mode="sun_angle", start_sun_angle=-6, end_sun_angle=-6)

    split_preview = active_window(split_angles, now)
    same_preview = active_window(same_angles, now)

    assert split_preview["active"] is True
    assert same_preview["active"] is True
    assert split_preview["window_start"] != same_preview["window_start"]
    assert split_preview["window_end"] != same_preview["window_end"]
    assert split_preview["window_start"] < split_preview["window_end"]


def test_invalid_timezone_falls_back_to_utc():
    now = datetime(2026, 6, 30, 1, 30, tzinfo=ZoneInfo("UTC"))

    preview = active_window(base_schedule(timezone="Not/AZone"), now)

    assert preview["timezone"] == "UTC"
    assert preview["now"] == "2026-06-30T01:30:00+00:00"
