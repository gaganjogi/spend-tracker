from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Arbitrary but generous ceiling to catch fat-finger entry (e.g. an extra
# zero), not a real business rule. Easy to change if that assumption is wrong.
MAX_AMOUNT = Decimal("1000000.00")


class ExpenseCreate(BaseModel):
    amount: Decimal = Field(..., gt=0, le=MAX_AMOUNT)
    category: str
    note: Optional[str] = None
    date: date_type

    @field_validator("amount")
    @classmethod
    def amount_max_two_decimals(cls, v: Decimal) -> Decimal:
        if v.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v

    @field_validator("category")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("category must not be empty")
        if len(v) > 50:
            raise ValueError("category must be at most 50 characters")
        return v.lower()

    @field_validator("note")
    @classmethod
    def clean_note(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 255:
            raise ValueError("note must be at most 255 characters")
        return v or None

    @field_validator("date")
    @classmethod
    def date_not_in_future(cls, v: date_type) -> date_type:
        if v > date_type.today():
            raise ValueError("date cannot be in the future")
        return v


class ExpenseOut(BaseModel):
    id: int
    amount: Decimal
    category: str
    note: Optional[str]
    date: date_type
    created_at: datetime

    @classmethod
    def from_model(cls, expense) -> "ExpenseOut":
        return cls(
            id=expense.id,
            amount=(Decimal(expense.amount_minor) / 100).quantize(Decimal("0.01")),
            category=expense.category,
            note=expense.note,
            date=expense.expense_date,
            created_at=expense.created_at,
        )


class ExpenseListOut(BaseModel):
    items: list[ExpenseOut]
    total: int
    limit: int
    offset: int


class CategoryTotal(BaseModel):
    category: str
    amount: Decimal


class MonthOverMonth(BaseModel):
    month: str
    current_total: Decimal
    previous_month: str
    previous_total: Decimal
    change_amount: Decimal
    change_percent: Optional[Decimal]


class RisingCategory(BaseModel):
    category: str
    previous_amount: Decimal
    current_amount: Decimal
    change_percent: Optional[Decimal]
    flag: str


class SummaryOut(BaseModel):
    total: Decimal
    by_category: list[CategoryTotal]
    month_over_month: MonthOverMonth
    rising_categories: list[RisingCategory]
