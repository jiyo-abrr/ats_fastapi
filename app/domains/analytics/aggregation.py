"""Pure aggregation helpers for the analytics repository.

Kept separate from repository.py (which does the SQL) so the risky
arithmetic — rates, weighted averages, score bucketing — is unit-testable
without a database.
"""

from datetime import date, datetime, timedelta, timezone

FIT_SCORE_BANDS = ("0-49", "50-69", "70-84", "85-100")

# Each granularity picks its own natural window — there's no single "period"
# slider any more, just "how do you want time sliced." Bucket sizes match
# what Postgres's own date_trunc() understands directly.
_BUCKET_BY_GRANULARITY = {
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
    "yearly": "year",
}


def period_start(period: str, now: datetime | None = None) -> datetime | None:
    """The lower bound for a given granularity's natural window — `None` for
    "yearly" (no lower bound; grouped by calendar year across all time)."""
    now = now or datetime.now(timezone.utc)
    if period == "daily":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        return now - timedelta(weeks=12)
    if period == "monthly":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def bucket_for(period: str) -> str:
    """The date_trunc() unit for a granularity — "day"/"week"/"month"/"year"."""
    return _BUCKET_BY_GRANULARITY.get(period, "day")


def bucket_starts(start: date, end: date, bucket: str) -> list[date]:
    """Every bucket-start date covering [start, end], inclusive — for zero-
    filling a time series so quiet buckets show up as real 0s instead of
    being silently absent. `bucket` is "day", "week" (Monday-aligned, to
    match Postgres date_trunc('week', ...)), or "month"."""
    if bucket == "day":
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if bucket == "week":
        first = start - timedelta(days=start.weekday())
        last = end - timedelta(days=end.weekday())
        out = []
        cursor = first
        while cursor <= last:
            out.append(cursor)
            cursor += timedelta(weeks=1)
        return out
    if bucket == "month":
        out = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            out.append(date(year, month, 1))
            month += 1
            if month > 12:
                month = 1
                year += 1
        return out
    raise ValueError(f"bucket_starts doesn't support bucket '{bucket}'")


def rate(part: int, whole: int) -> float:
    """`part/whole` as a 0-100 percentage rounded to 1dp; 0 when whole is 0."""
    return round((part / whole * 100) if whole else 0.0, 1)


def weighted_average(pairs: list[tuple[float, int]]) -> float | None:
    """Average of values weighted by their counts, rounded to 1dp.

    `pairs` is `(value, weight)`; entries with a falsy weight are ignored.
    Returns None when there is nothing to average.
    """
    total_weight = sum(weight for _value, weight in pairs if weight)
    if not total_weight:
        return None
    return round(
        sum(value * weight for value, weight in pairs if weight) / total_weight,
        1,
    )


def fit_score_bands(scores: list[int]) -> dict[str, int]:
    """Count fit scores into the fixed bands (keys = `FIT_SCORE_BANDS`)."""
    counts = dict.fromkeys(FIT_SCORE_BANDS, 0)
    for score in scores:
        if score < 50:
            counts["0-49"] += 1
        elif score < 70:
            counts["50-69"] += 1
        elif score < 85:
            counts["70-84"] += 1
        else:
            counts["85-100"] += 1
    return counts
