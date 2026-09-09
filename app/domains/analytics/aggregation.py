"""Pure aggregation helpers for the analytics repository.

Kept separate from repository.py (which does the SQL) so the risky
arithmetic — rates, weighted averages, score bucketing — is unit-testable
without a database.
"""

from datetime import datetime, timedelta, timezone

FIT_SCORE_BANDS = ("0-49", "50-69", "70-84", "85-100")


def period_start(period: str, now: datetime | None = None) -> datetime | None:
    """`None` for "all" (no lower bound), otherwise the cutoff datetime."""
    now = now or datetime.now(timezone.utc)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None


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
