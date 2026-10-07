# CareLink Follow-Up: technical assessment

Candidate: David Mwelwa · Position: Software Engineer

## What I built and what I stubbed

| Part | Status |
|---|---|
| B1 `GET /api/follow-up` (FastAPI + PostgreSQL) | Built |
| B1 `POST /api/follow-up/{id}/contacted` | Built, with `Idempotency-Key` support (links to D1) |
| B2 follow-up list screen (React + TypeScript, Vite) | Built |
| Stubbed | Nothing. Authentication uses static demo tokens, which the brief allows (production design below) |

Written sections: [A](A-architecture.md) · [C](C-review.md) · [D](D-resilience.md) · [F](F-practice.md) · [G](G-briefing.md) · [E slides](E-presentation.pdf) · [Declaration](declaration.md)

## Stack and why

- **Python + FastAPI.** Pydantic validation gives typed request and response models and correct `400` errors with little code, and OpenAPI docs are generated for free. Python is my strongest language.
- **PostgreSQL 16.** `LATERAL` joins and composite covering indexes make the "most recent visit" rule efficient in the database; it is also what I would choose in production.
- **SQLAlchemy Core + Alembic.** Explicit SQL for the follow-up query, versioned migrations from an empty database.
- **React + TypeScript + Vite**, TanStack Query (loading, error, retry and request cancellation) and TanStack Virtual (10,000 rows).
- **Docker Compose** so the whole thing runs on a clean machine with one command. Node and Python are not needed on the host.

## Running it from a clean machine

**Prerequisites:** Docker Desktop (or Docker Engine + Compose v2) and `make`. Nothing else.

```bash
git clone <repo-url> carelink-followup && cd carelink-followup
cp .env.example .env
make up      # builds and starts postgres, api, web; migrations run on api start
make seed    # sample data from the pack + generated data: 100,000 patients / 400,000 visits (~15 s)
make test    # API and front-end tests
```

- Screen: <http://localhost:5173> (choose a demo account on the sign-in page)
- API docs: <http://localhost:8000/docs> (press **Authorize** and paste a token)
- Demo tokens (in `.env.example`):

| Token | Role | Facility |
|---|---|---|
| `clin-0101-demo-token` | CLINICIAN | FAC-0101 (10,452 patients on the default list after `make seed`) |
| `clin-0207-demo-token` | CLINICIAN | FAC-0207 |
| `district-demo-token` | DISTRICT_OFFICER | all |

```bash
curl -H 'Authorization: Bearer clin-0101-demo-token' \
  'http://localhost:8000/api/follow-up?facility_id=FAC-0101&status=overdue&sort=days_overdue_desc&page=1&page_size=50'
```

Other targets: `make seed-small` (2,000 patients), `make bench-api`, `make bench-web`, `make logs`, `make psql`, `make down`, `make reset` (also deletes the database volume). `make help` lists them all.

**"Today".** `.env.example` sets `AS_OF_DATE=2026-10-06`, the pack's date, so the sample response reproduces exactly (Thandiwe Banda 31 days, Mulenga Phiri 26 days). Leave it blank to use the real date in Africa/Lusaka; `make seed` generates data relative to whichever date applies.

**Using a Postgres already installed on your machine instead:** set `DATABASE_URL=postgresql://USER:PASS@host.docker.internal:5432/carelink` (and `TEST_DATABASE_URL=…/carelink_test`) in `.env`, then `make up-nodb`. The bundled database is exposed on host port **5433** so it does not clash with a local one on 5432.

## Assumptions and how I read the follow-up rule

The pack leaves edge cases open. My interpretation:

1. **Most recent visit** is the latest `visit_date`; ties are broken by the latest `created_at`. Only that visit's `next_appointment_date` counts. If it is null the patient is excluded, even if an earlier visit set one (the Chipo Zulu case).
2. **"Since that date"** includes the appointment date: a visit on the day of the appointment counts as attending. Because the most recent visit is the one that set the appointment, "no visit since" reduces to `visit_date < next_appointment_date` on that visit; a visit that books an appointment for its own date has therefore been attended.
3. **"More than n days"** is strict. With n = 7, a patient 7 days past is not included; 8 days is.
4. **Days overdue** = today − appointment date, with today taken in **Africa/Lusaka**. An `AS_OF_DATE` setting fixes "today" for tests and demos. For `due_soon` the value is negative (−3 = due in 3 days).
5. **Statuses.** The sample response has 8 days as `missed` but 26 and 31 as `overdue`, so the cut-off must sit between 9 and 25 days. I chose **14 days**: "recently missed" means within two weeks of the appointment, the window in which a phone call is most likely to bring someone back.

| Status | Rule (n = `overdue_days`, default 7) |
|---|---|
| `due_soon` | Appointment from today up to 7 days ahead, not yet attended |
| `missed` | More than n days past, up to 14 days |
| `overdue` | More than 14 days past (or more than n, if n ≥ 14) |

   With no `status` filter the endpoint returns `missed` and `overdue` (the rule in B1). `due_soon` is returned only when requested. Patients 1 to n days past are in a deliberate grace period and appear in no list. The 7 and 14 are configurable (`DUE_SOON_DAYS`, `MISSED_WINDOW_DAYS`).
6. **Any visit type** counts as a visit.
7. **Access:** a `CLINICIAN` may only query their own facility (another `facility_id` returns `403`; omitting it defaults to their own). A `DISTRICT_OFFICER` must pass `facility_id` and cannot `POST` (`403`). A clinician posting for another facility's patient gets `404`, so the API does not confirm the record exists.
8. **Production auth** would be OIDC (Keycloak) with short-lived JWTs carrying role and facility or district. Only `app/auth.py` would change; everything downstream uses the same `Principal`.

## API: additions to the contract

All additive, so a client written against the pack still works.

| Addition | Why |
|---|---|
| `status` accepts a comma list (`missed,overdue`) | The screen's "Missed and overdue" and "All statuses" filters in one request |
| `sort`: `days_overdue_desc` (default), `days_overdue_asc`, `name_asc` | Whitelisted; user input never reaches SQL text |
| `q`: name or patient-number **prefix** | Server-side search across all pages (review item C2 #9); prefix rather than `%q%` so it can use an index |
| Response: `as_of`, `overdue_days`, item `last_visit_date` | The screen shows which "today" and threshold produced the list |
| `GET /api/follow-up/summary` | Counts per status for the summary cards, in one query |
| `GET /api/facilities`, `GET /api/me` | Facility picker (scoped by role) and the signed-in user |
| `POST …/contacted`: `Idempotency-Key` header | Same key and body: no second row, `204` with `Idempotent-Replayed: true`. Same key, different body: `409 IDEMPOTENCY_KEY_REUSED` |

`page_size` is 1 to 200 (default 50). Every error uses the pack's shape plus an optional `details` array of `{field, message}`, which the screen uses to attach errors to the right field.

## Schema additions and why

| Addition | Why |
|---|---|
| `facility` table (`district`) | Facility names in the response; district for the facility picker and future district scoping |
| `contact_attempt` table | Backs `POST …/contacted` and `last_contact_attempt`; stores `recorded_by` |
| `UNIQUE (facility_id, idempotency_key)` on `contact_attempt` with a request hash | Safe replay (D1), enforced by the database in the same transaction as the write |
| `UNIQUE (facility_id, patient_number)` | The pack says the number is unique within a facility |
| `CHECK (next_appointment_date >= visit_date)`, enums for `sex` and `visit_type` | Bad data is rejected at the source |
| Index `visit (patient_id, visit_date DESC, created_at DESC) INCLUDE (next_appointment_date)` | Finds each patient's latest visit with one index probe, without touching the table |
| Index `patient (facility_id, last_name, first_name)` | Facility filter and name ordering |
| Index `contact_attempt (patient_id, contacted_at DESC)` | Latest contact attempt per row on the page |

"Visit date not in the future" is validated in the API that records visits rather than as a `CHECK`, because a `CHECK` using `current_date` is not reliably re-evaluated in PostgreSQL. This slice has no visit-writing endpoint.

## Performance evidence

Measured on an Apple Silicon laptop with Docker Desktop, against the seeded data (100,000 patients, 400,000 visits). Reproduce with `make bench-api` and `make bench-web`.

| Measurement | Before | After | How measured |
|---|---|---|---|
| API query, FAC-0101, page 1 of 50 (10,452 matching patients) | 369 ms | 97 ms | `EXPLAIN ANALYZE` execution time, median of 7. Before: only a plain `visit(patient_id)` index. After: the composite covering index |
| API end-to-end, same request | – | 85 ms (page 200: 83 ms) | HTTP round trip, median of 7 |
| Screen, 10,000 rows, first paint | 5,845 ms | 112 ms | `/bench.html`, Chrome with 4× CPU throttling, median of 5 cold loads |
| Screen, 10,000 rows, DOM nodes | 210,043 | 402 | `document.querySelectorAll('*').length` |
| Screen, 10,000 rows, JS heap | 58.7 MB | 4.1 MB | Chrome DevTools Protocol `JSHeapUsedSize` |
| Screen, scroll to middle and paint | 264 ms | 39 ms | Two animation frames after setting `scrollTop` |

With no index on `visit` at all, the query rescans 400,000 visits per patient and did not finish in minutes, so the "before" uses the index most schemas would already have.

**What I did and why.** Two layers. **Server-side paging and filtering**: the browser never holds more than it has scrolled to, so a 4 GB machine never downloads 10,000 rows up front, and search and status filters work across the whole list rather than one page. **Row virtualisation**: only the ~25 visible rows (plus overscan) exist in the DOM, inside a real `<table>` with `aria-rowcount`/`aria-rowindex`, so screen readers still hear "row 4,312 of 10,453". The next page of 100 loads about 30 rows before the user reaches the end. Rows have a fixed height and `table-layout: fixed`, so columns don't shift as rows are recycled. The "before" is the same `FollowUpTable` component with virtualisation turned off, so the comparison isolates that one change.

## Tests

```bash
make test          # everything
make test-api      # pytest against a real PostgreSQL (51 tests, ~2 s)
make test-web      # TypeScript type-check, then Vitest + React Testing Library + MSW (23 tests)
```

**API.** I tested the rule's boundaries hardest, because a wrong boundary means a patient is chased who attended, or missed who didn't: the pack's sample data exactly; 7 vs 8 days; a custom threshold; a visit on the appointment date; a later visit with no next appointment; a return visit that booked a new appointment; ties on `visit_date` (both orders); each status bucket at both edges (−8/−7, 0, 1/7, 8/14, 15); facility isolation; sorting; search, including literal `%`. Then the contract: pagination past the end, every `400` with its field, `401`/`403`/`404`, district vs clinician access, idempotent replay and `409` key reuse, the error shape with its correlation ID, a `500` that leaks no detail, and **logs checked for names, phone numbers, notes, patient numbers and ids** after a real search and a real write. Tests run against PostgreSQL because the rule lives in SQL; a mock would test something else. The test session migrates `base → head` every run, proving the migration works from empty.

**Screen.** Through the real component tree, service layer and HTTP client, with the network mocked by MSW: loading announced, then rows; empty state distinct from error; **error with retry and recovery when the API is down** (and the proxy's `502` read as "can't reach the server"); the exact query parameters sent; threshold validation with the error associated to the field; sorting with `aria-sort`; summary cards as filters; **recording a contact using only the keyboard** (focus moves into the dialog, Tab order, Enter to save, focus returns on Escape); a failed save that says "Not saved" and **retries with the same `Idempotency-Key`**; a future time rejected with focus on the field; district officer has no write actions; the 10,000-row table keeps under 40 rows in the DOM. I chose these because a silently failing list or a lost contact attempt causes harm in a clinic, while visual detail does not.

I also checked "stop your API" by hand: `docker compose stop api`, reload, see the error panel, `docker compose start api`, press **Try again**.

## Accessibility

Three decisions:
1. A real `<table>` with `<th scope="col">` and a row header (`<th scope="row">`) for the patient, and sortable headers as `<button>`s with `aria-sort`, so screen readers announce sort order and which patient a cell belongs to. Virtualisation keeps `aria-rowcount`/`aria-rowindex` so the true size of the list is announced.
2. Status is always a **text badge plus a distinct icon** ("Overdue", "Missed", "Due soon"), with a dashed border for "Due soon" and an explicit "31 days"/"In 3 days"; colour only reinforces it. A `forced-colors` rule keeps badge borders in Windows High Contrast.
3. Every control has a visible `<label>`; field errors are linked with `aria-describedby` and `aria-invalid`, focus moves to the first invalid field, and an `aria-live="polite"` region announces loading and result counts (once per result change, not per page loaded while scrolling). The contact dialog traps focus, closes on Escape and returns focus to the button that opened it.

One thing I chose not to do: **full manual screen-reader testing** (NVDA with Firefox, JAWS). My checks are automated role- and name-based queries and keyboard-only walkthroughs. Real assistive-technology testing with clinic staff is the next step, and I would rather do it with users than tick it off alone.

## What I left out and what I would do next

- **Real OIDC** (Keycloak) instead of static tokens, with district scoping (a district officer limited to their own district's facilities) and audit of every patient-level read.
- **The offline outbox from D2 in the browser**: queued contact attempts in encrypted IndexedDB, replayed with the same idempotency keys. The API side (idempotent writes) is already in place.
- **A sync endpoint** for facility nodes, and expiry of idempotency keys after 30 days (D1).
- **Load testing** at 3,000 concurrent users (k6), and rate limiting (`429`) at the gateway.
- **Contract tests** between front end and API generated from the OpenAPI schema, so the hand-written TypeScript types cannot drift.
- **Query cost at larger facilities.** Each request computes the facility's whole list (≈100 ms for 35,000 patients). If facilities grow to several times that, I would maintain a `patient_follow_up` row per patient (updated in the same transaction as each visit) and index it directly.

## Logging

JSON logs to stdout with a correlation ID taken from, or added as, `X-Correlation-ID` and returned on every response and in every error body. The screen sends its own ID and shows the reference on error panels, so a clinic can quote it. Each request logs method, **route template** (never the raw path or query string, since `q` can be a patient's name), status, duration, role, facility and user id. `extra` fields pass through an allow-list, so a careless `log.info(..., extra={"patient": …})` cannot leak. Stack traces log frames but not exception messages, which from the database driver can echo row values. uvicorn's access log and `httpx` request logging are turned off for the same reason.

## Project layout

```
api/   FastAPI app (app/), Alembic migrations, seed (python -m seed), tests, scripts/bench_api.py
web/   React app: src/api (service layer, typed contract), src/features/followup, src/components, tests
scripts/measure_web.py   10,000-row before/after measurement
```
