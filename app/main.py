from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import Base, engine
from .routers import expenses, summary

Base.metadata.create_all(bind=engine)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Spend Tracker API")


def _error_response(code: str, message: str, details, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p != "body"),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return _error_response(
        "validation_error",
        "Request validation failed",
        details,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = _STATUS_CODES.get(exc.status_code, "error")
    return _error_response(code, str(exc.detail), None, exc.status_code)


app.include_router(expenses.router)
app.include_router(summary.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Mounted last so it never shadows the API routes above — Starlette matches
# routes in registration order, and this mount would otherwise catch every
# path (including /expenses, /summary) that isn't matched first.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
