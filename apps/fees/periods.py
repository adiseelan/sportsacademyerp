"""Date/period helpers for the fee engine (no external deps)."""
from datetime import date


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # clamp day to end of target month
    day = min(d.day, [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


PERIOD_MONTHS = {"MONTHLY": 1, "QUARTERLY": 3, "YEARLY": 12}


def period_label(start: date, period: str) -> str:
    if period == "MONTHLY":
        return start.strftime("%b %Y")
    if period == "QUARTERLY":
        q = (start.month - 1) // 3 + 1
        return f"Q{q} {start.year}"
    if period == "YEARLY":
        return str(start.year)
    return start.strftime("%b %Y")
