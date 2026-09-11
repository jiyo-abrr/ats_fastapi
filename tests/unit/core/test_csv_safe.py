from app.core.csv_safe import csv_safe


def test_guards_formula_prefixes():
    for bad in ("=1+1", "+1", "-1+2", "@SUM(A1)", "\ttab", "\rcr"):
        assert csv_safe(bad) == "'" + bad


def test_leaves_ordinary_values_alone():
    assert csv_safe("Ana Reyes") == "Ana Reyes"
    assert csv_safe("advance") == "advance"
    assert csv_safe(42) == 42
    assert csv_safe(None) is None
    assert csv_safe("") == ""
