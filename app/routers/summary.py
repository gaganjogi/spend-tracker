from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import schemas
from ..auth import require_api_key
from ..database import get_db
from ..services import summary_service

router = APIRouter(tags=["summary"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=schemas.SummaryOut)
def summary(
    start_date: Optional[date_type] = Query(default=None),
    end_date: Optional[date_type] = Query(default=None),
    month: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date",
        )

    if month is not None:
        try:
            year, month_num = summary_service.parse_month(month)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    else:
        today = date_type.today()
        year, month_num = today.year, today.month

    data = summary_service.build_summary(db, start_date, end_date, year, month_num)
    return schemas.SummaryOut(**data)
