from datetime import date

from sqlalchemy.orm import Session

from . import models, schemas


def create_expense(db: Session, payload: schemas.ExpenseCreate) -> models.Expense:
    expense = models.Expense(
        amount_minor=int(payload.amount * 100),
        category=payload.category,
        note=payload.note,
        expense_date=payload.date,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def list_expenses(
    db: Session,
    category: str | None,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    offset: int,
) -> tuple[list[models.Expense], int]:
    query = db.query(models.Expense)
    if category is not None:
        query = query.filter(models.Expense.category == category)
    if start_date is not None:
        query = query.filter(models.Expense.expense_date >= start_date)
    if end_date is not None:
        query = query.filter(models.Expense.expense_date <= end_date)

    total = query.count()
    items = (
        query.order_by(models.Expense.expense_date.desc(), models.Expense.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total
