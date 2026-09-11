"""Spreadsheet-injection guard for generated CSVs. See docs/decisions/D09.

Excel / Google Sheets treat a cell starting with = + - @ (or a leading tab /
CR) as a formula. CSV quoting controls delimiter parsing, not formula
interpretation, so the fix is the leading-apostrophe convention those apps
honour.
"""

_RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """Return `value` unchanged unless it's a string that would be read as a
    formula, in which case prefix it with a single quote."""
    if isinstance(value, str) and value.startswith(_RISKY_PREFIXES):
        return "'" + value
    return value
