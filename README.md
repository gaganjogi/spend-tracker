# Spend Tracker

A small expense-tracking API (FastAPI + SQLAlchemy + SQLite) with summary/insight
endpoints, API key auth, and a minimal HTML/JS frontend.

**Live demo:** https://spend-tracker-oo83.onrender.com — the API key isn't
public; ask for it, or run it yourself with your own key (see below). Note
the [ephemeral-SQLite caveat](#deployment-render): expenses added there don't
survive a redeploy.

## Setup and run

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env and set a real API_KEY
```

Start the server:

```bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)   # or just `export API_KEY=...` directly
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ for the frontend. The API itself is at the same
origin (`/expenses`, `/summary`, `/health`).

The app **fails to start** if `API_KEY` isn't set — see [Design
decisions](#design-decisions) for why.

## Running tests

```bash
source .venv/bin/activate
pytest -q
```

Each test gets its own temporary SQLite file (via a pytest fixture), so tests
don't share state or depend on run order.

## Environment variables

| Variable  | Required | Default       | Purpose                                             |
|-----------|----------|---------------|------------------------------------------------------|
| `API_KEY` | Yes      | *(none)*      | Value clients must send in `X-API-Key` to hit `/expenses` or `/summary`. |
| `DB_PATH` | No       | `./spend.db`  | Path to the SQLite database file.                    |

## API

All endpoints except `/health` and the frontend (`/`) require an `X-API-Key`
header. Errors always come back as:

```json
{"error": {"code": "...", "message": "...", "details": null}}
```

| Method | Path        | Auth | Description                                              |
|--------|-------------|------|------------------------------------------------------------|
| GET    | `/health`   | No   | Liveness check.                                             |
| POST   | `/expenses` | Yes  | Create an expense.                                          |
| GET    | `/expenses` | Yes  | List expenses, filterable + paginated.                      |
| GET    | `/summary`  | Yes  | Totals, by-category breakdown, month-over-month, insights.  |

### `POST /expenses`

```bash
curl -X POST http://127.0.0.1:8000/expenses \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount": 12.50, "category": "Food", "note": "lunch", "date": "2026-09-20"}'
```

Validation: `amount` > 0, ≤ 2 decimal places, ≤ 1,000,000.00; `category`
trimmed/lowercased, 1–50 chars; `note` optional, ≤ 255 chars; `date` must be
`YYYY-MM-DD` and not in the future. Returns `201` with the created expense on
success, `422` with field-level `details` on failure.

### `GET /expenses`

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/expenses?category=food&start_date=2026-09-01&end_date=2026-09-30&limit=20&offset=0"
```

Query params: `category`, `start_date`, `end_date` (inclusive), `limit`
(default 20, max 100), `offset` (default 0). Sorted by date desc, then id
desc. `start_date > end_date` → `400`. Response is
`{items, total, limit, offset}`.

### `GET /summary`

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:8000/summary?month=2026-09"
```

`start_date`/`end_date` (optional, filters `total` and `by_category`) and
`month` (optional `YYYY-MM`, default current month, drives `month_over_month`
and `rising_categories`) are independent filters. Example response:

```json
{
  "total": "575.00",
  "by_category": [{"category": "food", "amount": "225.00"}],
  "month_over_month": {
    "month": "2026-09", "current_total": "325.00",
    "previous_month": "2026-08", "previous_total": "250.00",
    "change_amount": "75.00", "change_percent": "30.00"
  },
  "rising_categories": [
    {"category": "food", "previous_amount": "100.00", "current_amount": "125.00",
     "change_percent": "25.00", "flag": "increase"},
    {"category": "rent", "previous_amount": "0.00", "current_amount": "30.00",
     "change_percent": null, "flag": "new"}
  ]
}
```

## Design decisions

- **Amounts stored as integer paise** (`amount_minor`), converted to/from a
  decimal major-unit amount at the API boundary. Avoids float rounding errors
  in sums; integer arithmetic is exact.
- **SQLite via SQLAlchemy 2.0** typed models (`DeclarativeBase`/`Mapped`).
  One `expenses` table — no separate `categories` table, since categories are
  free-text and filtered/grouped by string, not managed as their own entity.
- **Service layer** (`app/services/summary_service.py`) separates pure
  month-arithmetic/percent-math functions (no DB, directly unit-testable)
  from SQL `SUM`/`GROUP BY` aggregation functions — the summary endpoint
  never loads rows into Python to aggregate them.
- **Consistent error envelope** (`{"error": {"code", "message", "details"}}`)
  via two FastAPI exception handlers — one for Pydantic validation errors
  (422, with per-field `details`), one for all other `HTTPException`s (400,
  401, 404, ...) — so every error path looks the same to a client.
- **Month-over-month edge cases**: previous month = 0 spend → `change_percent`
  is `null` (not a divide-by-zero, not a fabricated 0%). January's "previous
  month" is computed via integer month-index arithmetic
  (`year*12 + month`), so it correctly resolves to December of the prior
  year with no special-casing. An empty database returns all zeros, not an
  error, because SQL's `SUM` over zero rows is `NULL` and is explicitly
  `COALESCE`d to `0`.
- **Rising-category insight**: a category with $0 spend last month and >$0
  this month is flagged `"new"` (not skipped, not silently divided by zero) —
  distinct from `"increase"` (>20% rise where last month was nonzero), so a
  reader can tell "this grew a lot" apart from "this didn't exist before."
- **API key auth fails the app at startup** if `API_KEY` is unset, rather
  than falling back to an unauthenticated dev mode. A crash on missing
  config is loud and impossible to miss; a silent "auth disabled" fallback
  is the kind of thing that quietly ships to production. Comparison is
  constant-time (`secrets.compare_digest`).
- **No client-side amount validation** (`min`/rigid `step` on the number
  input) — the browser would otherwise silently block invalid submissions
  before the server's own validation error could ever reach the UI, which
  defeats the point of surfacing the API's error messages.

## What I'd do differently with more time

- **Alembic migrations** instead of `Base.metadata.create_all()` — fine for
  one stable table, not fine once the schema needs to evolve.
- **Postgres** instead of SQLite for anything beyond a demo — real
  concurrent writes, and no ephemeral-disk problem on hosts like Render.
- **Per-user accounts + JWT** instead of a single shared API key — the
  current auth proves the concept but doesn't scale past "one person/demo."
- **Recurring expenses** (e.g. a `rrule`-style recurrence on an expense
  template) rather than only one-off entries.
- **Multi-currency support** — the schema currently assumes a single
  currency; a real version would store a currency code per expense and
  convert for aggregation.
- **Rate limiting** on the API, especially `POST /expenses`, since it's
  publicly reachable behind just one static key.
- **CI** (GitHub Actions running `pytest` on every push) — currently tests
  are only run locally/manually.
- Tighten `RisingCategory.flag`/similar string fields to `Literal[...]`
  types instead of bare `str`, for stricter typing at the schema boundary.

## Deployment (Render)

See `render.yaml`. Set `API_KEY` in the Render dashboard (not committed).
**SQLite on Render's free tier lives on an ephemeral filesystem** — every
redeploy (and every time the free-tier instance spins down and back up)
wipes the database. That's an accepted trade-off for a demo deployment, not
something this setup tries to work around; a real deployment would use
Postgres or a persistent disk.
