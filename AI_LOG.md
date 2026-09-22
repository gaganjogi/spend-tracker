# AI Suggestions Log

Running record of significant suggestions made by the AI during this build, phase by phase.
For each entry: what was suggested, why, and (filled in by the human) what was kept/changed/rejected.

---

## Phase 0 — Planning: folder structure & DB schema

**Suggested:**
- Standard FastAPI layout: `app/{main,config,database,models,schemas,crud}.py` + `app/routers/{expenses,summary}.py`, `static/` for the plain HTML/JS frontend, `tests/` mirroring the routers.
- Single `expenses` table (no separate `categories` table) since the spec only needs filtering by a category string, not managing a category list.
- `amount_minor INTEGER` (paise) per the user's own tech choice, with a `CHECK (amount_minor > 0)` constraint.
- Separate `expense_date` column distinct from `created_at`, so backfilled/late-entered expenses still summarize correctly by the date they actually occurred.
- Indexes on `category` and `expense_date` to support the filter/summary query patterns.
- No Alembic migrations — `Base.metadata.create_all` is enough for a single stable table at this scope; called out as a "what I'd do differently" README item instead.
- Single-currency assumption (no `currency` column) since the spec doesn't mention multi-currency.

**Human decision:** _(pending)_

---

## Phase 1 — DB setup, model, schemas, POST /expenses

**Suggested:**
- `SQLAlchemy 2.0` typed style (`DeclarativeBase` + `Mapped`/`mapped_column`) instead of the older `declarative_base()` + `Column()` style, per the requested SQLAlchemy 2.x.
- `pydantic-settings` for config (`Settings.db_path`, auto-read from env var `DB_PATH`) instead of manual `os.getenv` calls scattered around.
- Amount validation split two ways: `Field(gt=0, le=MAX_AMOUNT)` for range (declarative), plus a `field_validator` checking `Decimal.as_tuple().exponent` for the "max 2 decimal places" rule (can't express that via `Field` alone). `MAX_AMOUNT = 1,000,000.00` is an arbitrary sanity ceiling, not a real business rule — flagged as adjustable.
- Category: trimmed, rejected-if-empty-after-trim, length-checked, then lowercased in a single validator (order matters — checking length/emptiness *before* trimming would let `"   "` slip through as non-empty).
- Note: same trim treatment; an empty string after trimming is normalized to `None` rather than stored as `""`.
- Date: rejected if `> date.today()` (naive server-local "today" — no timezone handling, called out as a simplification).
- `ExpenseOut.from_model()` explicit converter (rather than `from_attributes=True` auto-mapping) because `amount_minor` → `amount` and `expense_date` → `date` both need real conversion (Decimal math, field rename), not just a name/type passthrough.
- Consistent `{"error": {"code", "message", "details"}}` shape applied to **both** validation errors (422) and generic HTTP errors (404 etc.) via two exception handlers, not just validation — since a consistent shape implies all error paths, not only the one the spec called out by name. Flagging this as slightly ahead of the literal ask, done to avoid revisiting main.py later when 401/404s from auth/other endpoints show up.
- No static file mount yet in `main.py` — the `static/` directory doesn't exist until the frontend phase; mounting it now would 500 on startup.

**Verified:** ran the server locally and exercised the happy path plus every validation rule (amount ≤0, >2 decimals, over max, empty/whitespace category, future date, bad date format, missing field, over-length note) and a 404, confirming trimming/lowercasing and the error envelope all behave as designed.

**Human decision:** _(pending)_

---

## Phase 2 — GET /expenses (filter, sort, pagination)

**Suggested:**
- Response is a small envelope `{items, total, limit, offset}` rather than a bare array. Reasoning: a UI consuming this needs `total` to know whether to show a "next page" control, and it's one extra `COUNT(*)` query with the same filters — not over-engineering, just what limit/offset pagination needs to be useful. Flagging it since you only asked for "limit/offset pagination," not the envelope shape explicitly.
- `category` query param is normalized the same way as on create (`.strip().lower()`) before filtering, so `?category=Food` matches rows stored as `"food"`. An empty/whitespace-only `category=` is treated as "no filter" (lenient), not an error — a blank filter value from a UI dropdown shouldn't 400.
- `start_date`/`end_date` are each optional and independent — you can filter by only one side of the range. The `start_date > end_date` check only fires when *both* are present, returned as `400 bad_request` (not a 422 validation error) since both values are individually valid dates; the problem is their relationship, which is exactly what `HTTPException` is for vs. Pydantic field validation.
- `limit`/`offset` are validated via `Query(ge=..., le=...)` (default limit 20, max 100, offset ≥0) rather than a custom validator — FastAPI/Pydantic already enforce bounds declaratively and the errors flow through the same validation-error envelope for free.
- Sorting is `ORDER BY expense_date DESC, id DESC` — the `id` tiebreaker makes pagination stable when multiple expenses share a date (without it, two expenses on the same day could sort inconsistently across pages).
- `crud.list_expenses` runs `.count()` on the filtered-but-unpaginated query, then a separate `.offset().limit()` call for the page — two queries, but it's the standard, simplest way to get an accurate total alongside a page in SQL (a single query can't return both without a window function, which would be overkill here).

**Verified:** seeded 5 expenses across categories/dates, then checked: default list (sort order correct, id used as tiebreaker for same-date rows), category filter (case-insensitive), inclusive date range, `start_date > end_date` → 400 with the consistent error shape, `limit`/`offset` pagination slicing, and out-of-bounds `limit`/`offset` → 422.

**Human decision:** _(pending)_

---

## Phase 3 — GET /summary + service module

**Suggested:**
- Aggregation logic lives in `app/services/summary_service.py`, split into two groups: **pure functions** (`shift_month`, `month_bounds`, `percent_change`, `parse_month`, `to_major`) that take/return plain values and never touch the DB, and **query functions** (`get_total_minor`, `get_by_category_minor`, `get_month_total_minor`, `get_month_by_category_minor`) that do `SUM`/`GROUP BY` in SQL. This is what you asked for — pure where possible, so the month-math and percent-math can be unit tested directly without spinning up a DB or an HTTP client.
- `func.coalesce(func.sum(...), 0)` rather than `func.sum(...) or 0` in Python — `SUM` over zero rows returns SQL `NULL`, not `0`, so without `coalesce` an empty table would make `.scalar()` return `None`. This is the "no expenses at all → zeros, not an error" requirement enforced at the SQL layer.
- Month arithmetic done via a single pure `shift_month(year, month, delta)` using integer index math (`year*12 + month - 1 + delta`, then floor-div/mod back to year/month) rather than a `dateutil.relativedelta` dependency or manual if/else for the January-wraps-to-December-of-prior-year case. One formula handles the wraparound for free — no special-casing needed, which is also why it's easy to unit test in isolation.
- Month boundaries use `[start_of_month, start_of_next_month)` — a half-open range — rather than `[start, last_day_of_month]`. This sidesteps having to compute the last valid day of a month (28/29/30/31) entirely.
- **`total` and `by_category` use the optional `start_date`/`end_date` filter**; **`month_over_month` and `rising_categories` use the independent `month` param** (default: current month). They're deliberately separate concepts — a date-range total and a specific month's comparison aren't the same question, even though both can be asked in one request.
- **Bonus insight — chose "flag new categories" over "skip them."** A category with $0 last month and real spend this month is arguably the most interesting insight a spend tracker can surface (a brand-new recurring cost), so silently dropping it felt like hiding the useful case to avoid a divide-by-zero. It gets its own `flag: "new"` (with `change_percent: null`, since percent-of-zero is undefined) so the frontend/reader can distinguish "grew >20%" from "wasn't here before" rather than conflating them.
- The >20% check is strictly `change > 20`, not `>=`, per your spec that exactly 20% must not trigger — verified directly (see below).
- `month` query param is validated with a small `parse_month` pure function (not Pydantic's date parser) since `"YYYY-MM"` isn't a valid ISO date on its own; a bad value returns `400 bad_request` with a clear message, consistent with the `start_date > end_date` case (a value that's syntactically fine but semantically wrong for a business rule is an `HTTPException`, not a 422 field-validation error).

**Verified:** empty-DB summary (all zeros, `change_percent: null`, no error), `?month=2026-01` boundary (previous month correctly reported as `2025-12`), malformed `month` values (400s), `start_date > end_date` (400), and a seeded Aug/Sep scenario exercising all three rising-category paths at once: food +25% (100→125) → flagged `"increase"`; transport +20% exactly (100→120) → correctly **not** flagged; rent $0→$30 → flagged `"new"` with null percent; entertainment flat (50→50) → not flagged. `total`/`by_category` also confirmed to sum across *all* expenses when no date range is given, independent of the `month` param.

**Human decision:** _(pending)_

---

## Phase 4 — pytest test suite

**Suggested:**
- Each test gets an isolated SQLite file via `tmp_path` (pytest's built-in per-test temp dir) — a fresh engine + `Base.metadata.create_all` per test function, wired in via `app.dependency_overrides[get_db]`, torn down after. This is what "each test gets its own temporary SQLite DB via a fixture" means concretely: no shared state, no test-order dependence.
- `tests/conftest.py` sets `DB_PATH`/`API_KEY` env vars at **module level, before any `from app...` import** — not inside a fixture — because pytest imports `conftest.py` (and hence executes this code) at collection time, before any test module (and its top-level `from app.main import app`) is imported. A fixture-based approach would run too late.
- `tests/test_summary_service.py` calls `summary_service.shift_month`/`month_bounds`/`percent_change`/`parse_month` directly — no `client`, no DB — per your "unit tests for the service functions directly" requirement.
- Split `test_expenses_create.py` / `test_expenses_list.py` / `test_summary_api.py` / `test_summary_service.py` by concern rather than one giant test file, mirroring the app's own module boundaries.
- Fixed a `StarletteDeprecationWarning` in `main.py` (`HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`) surfaced by the test run — not a behavior bug, just cleanup while the warning was visible.

**Result:** 46/46 passed on the first run. No real bugs found at this stage — the same edge cases (decimal validation, category normalization, the exact-20% boundary, empty-DB zeros) had already been hand-verified with curl during Phases 1–3, so the tests mostly *confirmed* existing behavior rather than catching something new. Re-ran with 52/52 passing after Phase 5 added the 6 auth tests below.

**Human decision:** _(pending)_

---

## Phase 5 — API key auth

**Suggested:**
- **Chose "fail clearly at startup" over a dev-mode bypass** when `API_KEY` is unset. Made `api_key: str` a required field (no default) on the Pydantic `Settings` model — `Settings()` raises a `ValidationError` at import time if the env var is missing, which naturally happens before the server ever binds a port. Reasoning: a silent "auth disabled" dev mode is the kind of thing that's easy to forget about and ship — someone deploys without setting `API_KEY`, the app starts, and every write endpoint is wide open with no visible signal. A crash with `api_key: Field required` is impossible to miss and costs nothing extra to implement (it's a side effect of Pydantic's own required-field behavior, not custom code). Verified by importing the app with `API_KEY` unset — it throws immediately with a clear message (see terminal output above).
- Auth is a single dependency (`app/auth.py: require_api_key`), applied once per router via `APIRouter(dependencies=[Depends(require_api_key)])` on `expenses.router` and `summary.router` — not decorating each endpoint individually, so a newly added endpoint under either router is protected by default rather than by remembering to add the dependency each time.
- **Constant-time comparison** via `secrets.compare_digest`, not `==`, so a wrong key doesn't leak timing information about how many leading characters matched — the textbook reason `==` is wrong for secret comparison.
- The `x_api_key is None or not secrets.compare_digest(...)` short-circuit matters: `compare_digest` needs two strings, so checking `is None` first avoids a `TypeError` when the header is absent, rather than making `compare_digest` handle `None`.
- `/health` and the (future) static frontend files are untouched — no dependency added to the bare `@app.get("/health")` route or to the static mount, so they stay open as required.

**Verified:** ran the full test suite (52/52 passing, including 6 new auth tests: missing key on `/expenses`, wrong key on `/expenses`, correct key succeeds, missing key on `POST /expenses`, missing key on `/summary`, `/health` open without a key) and manually confirmed against a live server — no `API_KEY` set → import fails immediately; `API_KEY` set → `/health` open, `/expenses` and `/summary` both 401 without a key, 401 with a wrong key, 200 with the right one.

**Human decision:** _(pending)_

---

## Phase 6 — Frontend (static/index.html)

**Suggested:**
- Single self-contained HTML file (inline `<style>`/`<script>`, no build step, no separate .css/.js) per your "single static/index.html" instruction — mounted read-only via `StaticFiles(directory=STATIC_DIR, html=True)` in `main.py`, registered **after** the API routers so it never shadows `/expenses`, `/summary`, `/health`.
- API key lives in one `let apiKey` JS variable, updated on the input's `input` event, read fresh on every request — never written to `localStorage`/`sessionStorage`/cookies, so it's gone on refresh, per "kept in memory only."
- A `formatError(body)` helper reads the `{error: {code, message, details}}` shape from Phase 1 directly — this only works cleanly *because* every error path (validation, auth, bad_request) already returns the same envelope; the frontend didn't need any endpoint-specific error handling.
- **Found and fixed a bug during manual testing**: the amount `<input>` originally had `step="0.01" min="0.01"`. Browsers enforce those natively and silently block form submission on invalid values (e.g. `-5`) *before* our JS handler ever runs — so the server's validation error never had a chance to reach the UI, defeating the "showing the API's validation errors" requirement. Removed `min`/tightened `step` to `"any"` so validation is genuinely server-driven and the error-rendering path actually gets exercised; kept `type="number"` and `required` for basic input-shape UX. Left the "field required" native check in place, since that one doesn't hide a *different* error message the server would show.
- Add-expense success handler re-fetches both `/summary` and `/expenses` (`Promise.all`), so the totals/table and the list update immediately without a manual reload — the small bit of UI state management that felt necessary rather than decorative.
- Category/date-range filters on the list are plain inputs read at filter-submit time (no live-as-you-type fetching) to avoid firing a request per keystroke.

**Verified:** drove the page in an actual browser end-to-end — loaded with the API key, submitted a negative amount and watched the exact server error text ("amount: Input should be greater than 0") render in the UI (after the min/step fix above), then added a valid expense and watched the total, by-category table, month-over-month line, and the new-category insight all update automatically, and confirmed the category filter correctly narrows the list to "Showing 0 of 0" for a non-matching category. No console errors at any point.

**Human decision:** _(pending)_

---

## Phase 7 — README, pinned deps, Render config, final review

**Suggested:**
- Pinned every entry in `requirements.txt` to the exact version actually installed (`pip freeze`-derived), not `>=`/bare names — reproducible builds for a grader running this cold, verified by reinstalling into a brand-new venv from scratch (see below).
- **Final review found one real cleanup**: `app/main.py` had `from pathlib import Path` sandwiched *after* the third-party `fastapi`/`starlette` imports instead of before them — cosmetic (stdlib-before-third-party ordering), fixed. No other dead code, unused imports, or naming inconsistencies turned up across `app/` — each module's imports are all used, and naming is consistent (`*_minor` for paise-integer values throughout the service layer, `snake_case` params matching the Pydantic/SQLAlchemy field names end to end).
- README's "what I'd do differently" list is deliberately concrete (Alembic, Postgres, JWT-based multi-user auth, recurring expenses, multi-currency, rate limiting, CI) rather than generic filler — each one names the specific limitation in *this* codebase it would address (e.g. "single shared API key doesn't scale past one demo user," not just "add auth").
- `render.yaml` uses `sync: false` for `API_KEY` (Render prompts for it in the dashboard rather than storing it in the committed file) and `$PORT` in the start command, since Render assigns the port dynamically rather than letting the app pick 8000.
- README explicitly documents SQLite-on-Render's-free-tier-is-ephemeral as an **accepted trade-off**, not a bug to fix — per your instruction, so a reviewer doesn't mistake data loss on redeploy for an oversight.

**Verified — full clean-room check:** deleted and recreated the venv from scratch, `pip install -r requirements.txt` (pinned versions) into it, ran the full test suite (52/52 passing), then followed the README's own setup steps verbatim (`cp .env.example .env`, set `API_KEY`, `export $(grep -v '^#' .env | xargs)`, `uvicorn app.main:app --reload`) and ran every curl example printed in the README's API section against the live server — all returned exactly the documented shapes. Cleaned up all test artifacts (`spend.db`, `.env`, the scratch venv) afterward.

**Human decision:** _(pending)_
