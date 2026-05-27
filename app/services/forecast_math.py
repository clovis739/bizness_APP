import math


MAX_NUMERIC_5_2 = 999.99


def calculate_growth_rate(
    projected_profit_cfa: float,
    startup_capital_cfa: float,
    limit: float = MAX_NUMERIC_5_2,
) -> float:
    """
    Calculates ROI-style growth as a percentage and clamps it for numeric(5,2).
    PostgreSQL numeric(5,2) accepts values whose absolute value is below 1000.
    """
    startup_capital = max(1.0, float(startup_capital_cfa or 0))
    projected_profit = float(projected_profit_cfa or 0)
    raw_growth_rate = (projected_profit / startup_capital) * 100

    if not math.isfinite(raw_growth_rate):
        return 0.0

    clamped = max(-limit, min(raw_growth_rate, limit))
    return round(clamped, 2)
