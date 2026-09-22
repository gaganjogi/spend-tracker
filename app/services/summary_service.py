"""Spend summary aggregation.

Split into pure helpers (month arithmetic, percent-change math, month-string
parsing — no DB, trivially unit-testable) and query functions that do the
actual SUM/GROUP BY aggregation in SQL rather than pulling rows into Python.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models

RISE_THRESHOLD_PERCENT = Decimal("20")


# ---- pure helpers (no DB) --------------------------------------------------

def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by `delta` months. Handles year wraparound."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return [start, end) as calendar-day bounds for the given month."""
    start = date(year, month, 1)
    end_year, end_month = shift_month(year, month, 1)
    return start, date(end_year, end_month, 1)


def percent_change(previous: Decimal, current: Decimal) -> Optional[Decimal]:
    """None (not 0 or an error) when there's nothing to compare against."""
    if previous == 0:
        return None
    return ((current - previous) / previous * 100).quantize(Decimal("0.01"))


def parse_month(value: str) -> tuple[int, int]:
    """Parse a 'YYYY-MM' string. Raises ValueError with a clear message."""
    parts = value.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError("month must be in YYYY-MM format")
    year, month = int(parts[0]), int(parts[1])
    if not 1 <= month <= 12:
        raise ValueError("month must be between 01 and 12")
    return year, month


def to_major(amount_minor: Optional[int]) -> Decimal:
    return (Decimal(amount_minor or 0) / 100).quantize(Decimal("0.01"))


# ---- SQL aggregation --------------------------------------------------------

def get_total_minor(db: Session, start_date: Optional[date], end_date: Optional[date]) -> int:
    query = db.query(func.coalesce(func.sum(models.Expense.amount_minor), 0))
    if start_date is not None:
        query = query.filter(models.Expense.expense_date >= start_date)
    if end_date is not None:
        query = query.filter(models.Expense.expense_date <= end_date)
    return query.scalar() or 0


def get_by_category_minor(
    db: Session, start_date: Optional[date], end_date: Optional[date]
) -> dict[str, int]:
    query = db.query(models.Expense.category, func.sum(models.Expense.amount_minor))
    if start_date is not None:
        query = query.filter(models.Expense.expense_date >= start_date)
    if end_date is not None:
        query = query.filter(models.Expense.expense_date <= end_date)
    return dict(query.group_by(models.Expense.category).all())


def get_month_total_minor(db: Session, year: int, month: int) -> int:
    start, end = month_bounds(year, month)
    total = (
        db.query(func.coalesce(func.sum(models.Expense.amount_minor), 0))
        .filter(models.Expense.expense_date >= start, models.Expense.expense_date < end)
        .scalar()
    )
    return total or 0


def get_month_by_category_minor(db: Session, year: int, month: int) -> dict[str, int]:
    start, end = month_bounds(year, month)
    rows = (
        db.query(models.Expense.category, func.sum(models.Expense.amount_minor))
        .filter(models.Expense.expense_date >= start, models.Expense.expense_date < end)
        .group_by(models.Expense.category)
        .all()
    )
    return dict(rows)


# ---- assembly ---------------------------------------------------------------

def build_summary(
    db: Session,
    start_date: Optional[date],
    end_date: Optional[date],
    year: int,
    month: int,
) -> dict:
    total_minor = get_total_minor(db, start_date, end_date)
    by_category_minor = get_by_category_minor(db, start_date, end_date)

    current_minor = get_month_total_minor(db, year, month)
    prev_year, prev_month = shift_month(year, month, -1)
    previous_minor = get_month_total_minor(db, prev_year, prev_month)

    current_by_cat = get_month_by_category_minor(db, year, month)
    previous_by_cat = get_month_by_category_minor(db, prev_year, prev_month)

    rising = []
    for category, current_amount in current_by_cat.items():
        previous_amount = previous_by_cat.get(category, 0)
        if previous_amount == 0:
            if current_amount > 0:
                rising.append(
                    {
                        "category": category,
                        "previous_amount": to_major(previous_amount),
                        "current_amount": to_major(current_amount),
                        "change_percent": None,
                        "flag": "new",
                    }
                )
            continue
        change = percent_change(Decimal(previous_amount), Decimal(current_amount))
        if change is not None and change > RISE_THRESHOLD_PERCENT:
            rising.append(
                {
                    "category": category,
                    "previous_amount": to_major(previous_amount),
                    "current_amount": to_major(current_amount),
                    "change_percent": change,
                    "flag": "increase",
                }
            )
    rising.sort(key=lambda r: r["category"])

    return {
        "total": to_major(total_minor),
        "by_category": [
            {"category": c, "amount": to_major(a)}
            for c, a in sorted(by_category_minor.items())
        ],
        "month_over_month": {
            "month": f"{year:04d}-{month:02d}",
            "current_total": to_major(current_minor),
            "previous_month": f"{prev_year:04d}-{prev_month:02d}",
            "previous_total": to_major(previous_minor),
            "change_amount": to_major(current_minor - previous_minor),
            "change_percent": percent_change(Decimal(previous_minor), Decimal(current_minor)),
        },
        "rising_categories": rising,
    }
