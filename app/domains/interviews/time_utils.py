"""Wall-clock conversions shared by availability validation and scheduling."""

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def hhmm_to_minutes(value: str) -> int:
    try:
        h, m = (int(p) for p in value.split(":"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"'{value}' is not a HH:MM time") from exc
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"'{value}' is out of range")
    total = h * 60 + m
    # 24:00 is the valid end-of-day sentinel; 24:01–24:59 are not real times
    # and exceed the DB's end_minute <= 1440 constraint.
    if total > 1440:
        raise ValueError(f"'{value}' is past the end of the day (max 24:00)")
    return total


def minutes_to_hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"
