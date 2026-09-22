"""Unit tests for the pure aggregation helpers, exercised directly
(no HTTP client, no DB) to prove the math is correct in isolation."""
from datetime import date
from decimal import Decimal

import pytest

from app.services import summary_service


def test_shift_month_forward_within_year():
    assert summary_service.shift_month(2026, 6, 1) == (2026, 7)


def test_shift_month_backward_within_year():
    assert summary_service.shift_month(2026, 6, -1) == (2026, 5)


def test_shift_month_january_wraps_to_previous_december():
    assert summary_service.shift_month(2026, 1, -1) == (2025, 12)


def test_shift_month_december_wraps_to_next_january():
    assert summary_service.shift_month(2025, 12, 1) == (2026, 1)


def test_month_bounds_is_half_open_range():
    start, end = summary_service.month_bounds(2026, 2)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 3, 1)


def test_month_bounds_handles_december():
    start, end = summary_service.month_bounds(2025, 12)
    assert start == date(2025, 12, 1)
    assert end == date(2026, 1, 1)


def test_percent_change_previous_zero_is_none():
    assert summary_service.percent_change(Decimal("0"), Decimal("50")) is None


def test_percent_change_increase():
    assert summary_service.percent_change(Decimal("100"), Decimal("150")) == Decimal("50.00")


def test_percent_change_decrease():
    assert summary_service.percent_change(Decimal("100"), Decimal("80")) == Decimal("-20.00")


def test_percent_change_exactly_twenty():
    assert summary_service.percent_change(Decimal("100"), Decimal("120")) == Decimal("20.00")


def test_parse_month_valid():
    assert summary_service.parse_month("2026-09") == (2026, 9)


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "abc", "2026", "2026-09-01"])
def test_parse_month_rejects_invalid(value):
    with pytest.raises(ValueError):
        summary_service.parse_month(value)
