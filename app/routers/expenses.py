from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..auth import require_api_key
from ..database import get_db

router = APIRouter(prefix="/expenses", tags=["expenses"], dependencies=[Depends(require_api_key)])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@router.post("", response_model=schemas.ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(payload: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    expense = crud.create_expense(db, payload)
    return schemas.ExpenseOut.from_model(expense)


@router.get("", response_model=schemas.ExpenseListOut)
def list_expenses(
    category: Optional[str] = Query(default=None),
    start_date: Optional[date_type] = Query(default=None),
    end_date: Optional[date_type] = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date",
        )

    normalized_category = category.strip().lower() if category and category.strip() else None

    items, total = crud.list_expenses(
        db,
        category=normalized_category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return schemas.ExpenseListOut(
        items=[schemas.ExpenseOut.from_model(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
