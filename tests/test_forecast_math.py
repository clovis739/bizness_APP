from app.services.forecast_math import calculate_growth_rate


def test_growth_rate_is_clamped_for_numeric_5_2_upper_bound():
    assert calculate_growth_rate(50_000, 1) == 999.99


def test_growth_rate_is_clamped_for_numeric_5_2_lower_bound():
    assert calculate_growth_rate(-50_000, 1) == -999.99


def test_growth_rate_uses_one_as_minimum_startup_capital():
    assert calculate_growth_rate(5, 0) == 500.0


def test_growth_rate_rounds_normal_values():
    assert calculate_growth_rate(1234.567, 1000) == 123.46
