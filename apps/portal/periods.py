"""Reporting periods (a calendar month or a calendar year) for the admin
dashboard's period picker and period-scoped exports.

URL format: ``?period=2026-10`` (month) or ``?period=2026`` (year).
Anything missing, malformed or in the future falls back to the current month.
"""
import calendar
import re
from dataclasses import dataclass
from datetime import date

MONTH = "month"
YEAR = "year"

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


@dataclass(frozen=True)
class ReportingPeriod:
    kind: str  # MONTH | YEAR
    start: date
    end: date

    @property
    def is_year(self):
        return self.kind == YEAR

    @property
    def value(self):
        """Query-string value: '2026-10' or '2026'."""
        return f"{self.start:%Y}" if self.is_year else f"{self.start:%Y-%m}"

    @property
    def label(self):
        """Short label for the picker button: 'Oct 2026' or '2026'."""
        return f"{self.start:%Y}" if self.is_year else f"{self.start:%b %Y}"

    @property
    def option_label(self):
        """Label in the dropdown list: 'October 2026' or '2026'."""
        return f"{self.start:%Y}" if self.is_year else f"{self.start:%B %Y}"

    @property
    def range_label(self):
        """'01 Oct – 31 Oct 2026' / '01 Jan – 31 Dec 2026'."""
        return f"{self.start:%d %b} – {self.end:%d %b %Y}"


def month_period(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return ReportingPeriod(MONTH, date(year, month, 1), date(year, month, last_day))


def year_period(year):
    return ReportingPeriod(YEAR, date(year, 1, 1), date(year, 12, 31))


def current_month(today):
    return month_period(today.year, today.month)


def parse_period(value, today):
    """Turn a query-string value into a ReportingPeriod (never in the future)."""
    value = (value or "").strip()
    period = None
    m = _MONTH_RE.match(value)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and year >= 2000:
            period = month_period(year, month)
    else:
        y = _YEAR_RE.match(value)
        if y and int(y.group(1)) >= 2000:
            period = year_period(int(y.group(1)))
    if period is None or period.start > today:
        return current_month(today)
    return period


def _shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_options(today, earliest=None, maximum=36):
    """Most recent first: the current month back to the month of the first
    recorded payment (no empty months before the academy started collecting)."""
    count = 1
    if earliest and earliest <= today:
        span = (today.year - earliest.year) * 12 + (today.month - earliest.month) + 1
        count = min(span, maximum)
    return [month_period(*_shift_month(today.year, today.month, -i)) for i in range(count)]


def year_options(today, earliest=None):
    """Most recent first: the current year back to the year of the first payment."""
    first = earliest.year if earliest and earliest <= today else today.year
    return [year_period(y) for y in range(today.year, first - 1, -1)]
