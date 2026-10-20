# Clinic Booking API

A booking service for a small clinic (5 doctors, 30-minute slots). Patients see which slots are free for a doctor on a given day, book one, and can cancel or reschedule. A booked slot is never available to anyone else.

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async) + Alembic, PostgreSQL, Docker, GitHub Actions, Render, Neon.

## Links

| | |
|---|---|
| Live app | https://clinic-api-latest-3axz.onrender.com |
| Interactive API docs (Swagger UI) | https://clinic-api-latest-3axz.onrender.com/docs |
| Repository | https://github.com/Kalukwo/savannah-booking |
| AI reflection (Section 4) | [AI_REFLECTION.md](AI_REFLECTION.md) |

> **Cold start:** the app runs on Render's free tier and the database on Neon's free tier. Both sleep after a period of inactivity, so the first request can take 50 seconds or more. Later requests are fast.

**Quick try** (in `/docs`): `GET /doctors/1/availability?date=<a weekday>`, then `POST /appointments` with a slot from that list. Seeded IDs: doctors 1-5, patients 1-5 (see [Directory data](#directory-data)). Times without an offset are read as EAT (see [Time zones](#time-zones)).

## Contents

1. [Repository structure](#1-repository-structure)
2. [System design](#2-system-design)
3. [API reference](#3-api-reference)
4. [Concurrency and atomicity](#4-concurrency-and-atomicity)
5. [Validation and errors](#5-validation-and-errors)
6. [Testing](#6-testing)
7. [Deployment and CI/CD](#7-deployment-and-cicd)
8. [Additions beyond the brief](#8-additions-beyond-the-brief)
9. [Growth path](#9-growth-path)
10. [Run locally](#10-run-locally)
11. [AI reflection](#11-ai-reflection)

---

## 1. Repository structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml              - GitHub Actions: test on PR, test + deploy on merge to main
├── alembic/                    - Version-controlled database migrations
│   └── versions/
├── app/
│   ├── api/
│   │   └── routes/             - HTTP only: parse request, call one service, return response
│   ├── core/
│   │   ├── config.py           - Settings from environment variables
│   │   ├── errors.py           - Domain error types and exception handlers
│   │   ├── clock.py            - Injectable clock
│   │   └── timezone.py         - The only time zone module (EAT <-> UTC)
│   ├── directories/            - DoctorDirectory / PatientDirectory interfaces + test-data implementations
│   ├── models/                 - SQLAlchemy models: Appointment, IdempotencyKey
│   ├── repositories/           - All database queries
│   ├── schemas/                - Pydantic request and response models
│   ├── services/               - All business rules: booking, availability, cancel, reschedule, lifecycle, idempotency
│   └── main.py                 - FastAPI app entry point
├── tests/
│   ├── unit/                   - No database (60 tests)
│   └── integration/            - Real PostgreSQL (13 tests)
├── .env.example                - Environment variable template
├── alembic.ini
├── AI_REFLECTION.md            - AI reflection (Section 4 of the brief)
├── docker-compose.yml          - db, testdb, app
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

Things to note:

- Routes contain no business rules. Services contain no SQL. Repositories contain no business rules.
- Doctors and patients have no tables. Their data comes from `app/directories` (see [Directory data](#directory-data)).
- Slots are never stored. They are computed on request.
- Schema changes go through Alembic only.

---

## 2. System design

### 2.1 Assumptions (the brief is ambiguous, so these are my decisions)

| # | Ambiguity | Decision | Why |
|---|---|---|---|
| A | What is this service? | A **booking service inside a larger platform**. It owns appointments and the booking rules. Doctors and patients belong to other services, so only their **IDs** are stored (no doctor/patient tables, no foreign keys to them). | The brief says the clinic is "starting small but wants to grow". A single-domain service with clear boundaries can be plugged into other services later. |
| B | Where do doctor and patient data come from? | Two small interfaces, `DoctorDirectory` and `PatientDirectory`. Today they are backed by **test-data directories** held in code (see [Directory data](#directory-data)), with **no database seeding**. In the real world these would be HTTP clients calling the doctor and patient services. | Booking rules depend on the interface, so swapping in the real services changes no booking logic. Working hours live with the doctor directory because they describe the doctor; a local copy would drift from the source. |
| C | Time zone | The clinic operates in **EAT** (Africa/Nairobi, UTC+3, no DST). See [Time zones](#time-zones). | The brief never mentions time zones. |
| D | Who is calling? | **No authentication or registration.** The caller states their identity in the request body (`doctor_id`, `patient_id`, or `actor`/`actor_id`) and the API checks it against the appointment. | Out of scope for the brief. This enforces the business rules but is **not security**: anyone can send any ID. Production would authenticate at platform level and authorize by role. |
| E | Do bookings need confirmation? | Yes, a booking is **reserved** and the assigned doctor approves or rejects it. | A clinic must confirm a booking before it is final. See [Additions](#8-additions-beyond-the-brief). |

### 2.2 Models

| Model | Fields |
|---|---|
| **Appointment** | `id`, `doctor_id`, `patient_id`, `start_time` (timestamptz, UTC), `status`, `cancel_reason`, `cancelled_by` (patient or doctor), `created_at`, `updated_at` |
| **IdempotencyKey** | `key` (unique), `request_hash`, `response_status`, `response_body`, `created_at` |

**Not models:** Doctor and Patient (owned by other services) and Slot. **Slots are never stored.** They are computed on request (see 2.5).

**Key constraint:** a partial unique index on `(doctor_id, start_time) WHERE status NOT IN ('cancelled','rejected')`. It is the final guard against double booking. It is *partial* so that a cancelled or rejected slot can be booked again; a plain unique index would block the slot forever. Because slots are fixed, aligned 30-minute blocks, a unique start time is enough to prevent overlaps.

### 2.3 Components

```
Client → API routes → Services → Repositories → PostgreSQL
                         │
                         ├─ Directories (test data now, HTTP clients later)
                         └─ Time zone helper
```

| Component | Responsibility |
|---|---|
| API routes (`app/api/routes`) | HTTP only: parse and validate the request shape, call one service, return the response. No business rules. |
| Schemas (`app/schemas`) | Pydantic request and response models. |
| Services (`app/services`) | All business rules: booking, availability, cancel, reschedule, lifecycle, idempotency. |
| Repositories (`app/repositories`) | All database queries. |
| Directories (`app/directories`) | `DoctorDirectory` / `PatientDirectory` interfaces and their test-data implementations. |
| Core (`app/core`) | Config, error types and handlers, injectable clock, the only time zone module. |
| Migrations (`alembic/`) | Version-controlled schema changes. |
| PostgreSQL | Stores appointments and enforces the double-booking constraint. |

### 2.4 Appointment lifecycle

Statuses: `reserved`, `confirmed`, `rejected`, `cancelled`, `completed`, `no_show`.

| Transition | Who | When |
|---|---|---|
| reserved → confirmed / rejected | assigned doctor | before start |
| reserved / confirmed → cancelled | owning patient **or** assigned doctor | before start, no cancellation window |
| reserved / confirmed → reserved (reschedule) | owning patient | before start; the new slot needs approval again |
| confirmed → completed / no_show | assigned doctor | after start |

`cancelled`, `rejected`, `completed` and `no_show` are final. Any other move returns `409 INVALID_TRANSITION`.

- Slots held by `reserved`, `confirmed`, `completed` and `no_show` appointments are unavailable. `cancelled` and `rejected` free the slot.
- A `reserved` appointment whose start time has passed is expired and cannot be approved.
- Cancel and reschedule treat `cancelled`, `rejected` and past (expired) appointments alike, as "already cancelled", and return a 409.
- Cancelling is allowed at any time before the start. No cancellation window was chosen to free slots as early as possible.

> **Naming note:** the brief calls a newly created booking `pending`. This implementation calls it `reserved`, because the booking holds the slot until the doctor confirms it, which `reserved` describes more accurately. The migration `0002_pending_to_reserved` renamed the status in place; no other status changed.

### 2.5 Slots are computed, not stored

`GET /doctors/{id}/availability?date=` runs these steps on every call:

1. Read the doctor's schedule from `DoctorDirectory` (hours and working days).
2. If the date is not a working day, return an empty list.
3. Generate every 30-minute slot between start and end of the working day, in EAT.
4. Fetch that doctor's active appointments for the EAT day (as a UTC range).
5. Remove taken slots, past slots and slots less than 1 hour from now.
6. Return the rest with a `+03:00` offset.

**Why:** nothing to keep in sync, schedule changes apply immediately, and no pre-created rows. **Caveat:** availability is a snapshot. A free slot can be taken a moment later, so booking may still return `409 SLOT_TAKEN`; the client should re-fetch availability and choose another slot.

A slot must end by the closing time, so the last slot starts 30 minutes before it.

### 2.6 Architecture choice

**Layered monolith** (routes → services → repositories → database) plus a thin integration boundary (the directories).

- **Why:** one domain (appointments), a small scope, and a 3-5 day limit.
- **Considered and skipped:** clean/hexagonal architecture (more interfaces and mapping code than this scope justifies) and per-domain modules (only one domain here).
- **Trade-off:** the partial unique index is PostgreSQL-specific, so moving to another database vendor would need a different double-booking guard.
- Booking runs in one database transaction, which the double-booking guarantee relies on.

### Directory data

**This service is a microservice in a larger platform.** It does **not** own doctor or patient records; in production those are fetched from the doctor service and the patient service over HTTP. The interfaces it depends on are `DoctorDirectory` and `PatientDirectory` (`app/directories/base.py`).

So that the service can run and be tested today, both interfaces are backed by **in-code test-data implementations** in `app/directories/test_data/`:

| Implementation | File | Data source |
|---|---|---|
| `DoctorTestDataDirectory` | `app/directories/test_data/doctor_directory.py` | A dict in code: 5 doctors and their working hours |
| `PatientTestDataDirectory` | `app/directories/test_data/patient_directory.py` | A set in code: patients 1-5 |

There is **no doctor table, no patient table and no seed script**. Nothing about doctors or patients is written to PostgreSQL; appointments store only their integer IDs. Replacing these classes with HTTP clients against the real services requires no change to any booking rule.

**Doctors** (IDs 1-5, all Monday to Friday, times in EAT):

| Doctor ID | Working hours | Working days |
|---|---|---|
| 1 | 08:00 - 17:00 | Mon - Fri |
| 2 | 09:00 - 16:00 | Mon - Fri |
| 3 | 10:00 - 18:00 | Mon - Fri |
| 4 | 08:00 - 14:00 | Mon - Fri |
| 5 | 09:00 - 17:00 | Mon - Fri |

**Patients:** IDs **1, 2, 3, 4, 5**. Patients have no schedule and no attributes beyond the ID.

Any doctor or patient ID outside these sets returns `404 DOCTOR_NOT_FOUND` or `404 PATIENT_NOT_FOUND`.

### Time zones

- Clinic zone is EAT (Africa/Nairobi, UTC+3, no DST). All conversion lives in one module, `app/core/timezone.py`.
- Everything is **stored in UTC** (`timestamptz`) and compared in UTC.
- Input **with** an offset (`Z`, `+03:00`) is converted to UTC. Input **without** an offset is read as **EAT**, so `"2026-10-21T10:00:00"` means 10:00 at the clinic. This keeps manual testing in Swagger or Postman simple.
- Working hours are EAT local times, judged in EAT (07:30 EAT is rejected even though 07:30 UTC would look "inside" the hours).
- Responses return times in EAT with the `+03:00` offset.
- **Growth:** for several clinics or regions, each clinic would carry its own time zone and conversion would become automatic. Because times are stored in UTC and conversion is isolated, no stored data would need migrating.

---

## 3. API reference

Interactive docs: `/docs`. All request bodies reject unknown fields. Errors use one shape: `{"code": "...", "detail": "..."}`.

| Method | Path | Body | Success | Source |
|---|---|---|---|---|
| POST | `/appointments` | `doctor_id`, `patient_id`, `start_time`; optional header `Idempotency-Key` | 201, status `reserved` | Brief |
| GET | `/doctors/{id}/availability?date=YYYY-MM-DD` | none | 200 | Brief |
| PATCH | `/appointments/{id}/cancel` | `reason` (required), `actor` (`patient` or `doctor`), `actor_id` | 200 | Brief |
| PATCH | `/appointments/{id}/reschedule` | `patient_id`, `start_time` | 200 | Brief |
| GET | `/patients/{id}/appointments` | none | 200, upcoming `reserved` and `confirmed`, sorted by start time | Brief (bonus) |
| PATCH | `/appointments/{id}/approve` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/reject` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/complete` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/no-show` | `doctor_id` | 200 | **Addition** |
| GET | `/` | none | 200, short JSON message | **Addition** |

The brief's bonus "prevention of bookings within 1 hour of now" is implemented as the `SLOT_TOO_SOON` rule.

**Example: book a slot** (no offset means EAT)

```http
POST /appointments
{ "doctor_id": 1, "patient_id": 2, "start_time": "2026-10-21T10:00:00" }
```

```json
{
  "id": 1,
  "doctor_id": 1,
  "patient_id": 2,
  "start_time": "2026-10-21T10:00:00+03:00",
  "status": "reserved",
  "cancel_reason": null,
  "cancelled_by": null,
  "created_at": "...",
  "updated_at": "..."
}
```

**Example: availability**

```json
{
  "doctor_id": 1,
  "date": "2026-10-21",
  "slots": ["2026-10-21T08:00:00+03:00", "2026-10-21T08:30:00+03:00", "..."]
}
```

The brief asks to "return all available 30-minute slots". They are returned inside an object together with the doctor and date, so the response is self-describing.

### Idempotency-Key (optional)

`POST /appointments` accepts an **optional** `Idempotency-Key` header. **It is not required.** Without it, the endpoint behaves exactly as the brief describes (a repeated booking returns `409 SLOT_TAKEN`), so ordinary clients, Swagger and Postman need not send it.

- **With a key:** the first request runs and the key, request hash and response are stored in the same transaction as the booking. The same key with the same body **replays** the stored response and creates no second booking. The same key with a **different** body returns `409 IDEMPOTENCY_KEY_REUSED`.
- Keys expire after 24 hours. Use a **new key for each new booking**, and reuse a key only to retry that exact request (for example after a timeout).
- There is deliberately no automatic duplicate detection without a key. It would make a plain duplicate booking succeed, contradicting the brief's expected 409.

---

## 4. Concurrency and atomicity

Checks produce friendly errors, but **the database is the real guard**: two requests can both pass a check before either writes.

**Reschedule runs in one transaction:**

1. `SELECT ... FOR UPDATE` on the appointment (row lock).
2. Check its status (same rule as cancel), then validate the new slot exactly as for a fresh booking.
3. `UPDATE` the **same row**: new `start_time`, status back to `reserved`.
4. If another transaction holds the new slot, the unique index raises `IntegrityError`. The transaction rolls back and returns `409 SLOT_TAKEN`, leaving the original booking untouched.

The old slot frees itself because one row is updated, so there is never a moment where the old slot is lost and the new one is not yet held.

| Race | Handled by |
|---|---|
| Two bookings for the same slot | Unique index: one gets 201, the other 409 |
| Reschedule and another booking on the target slot | Unique index |
| Reschedule and cancel on the same appointment | Row lock: the second request waits, then sees the new status |
| Two reschedules of one appointment | Row lock, then re-validation |

The API is async (FastAPI with SQLAlchemy `AsyncSession` and `asyncpg`), with one session per request. It uses no Python-level locks, because those break as soon as more than one container instance runs.

---

## 5. Validation and errors

Validation happens at three levels: **input shape** (Pydantic), **business rules** (services) and **integrity** (database constraint).

The approach is pragmatic. It covers every rule in the brief plus the checks needed for correctness:

- The slot must **end** within working hours (the last slot starts 30 minutes before closing).
- The cancel `reason` is required, trimmed, not blank, and at most 500 characters.
- Rescheduling to the same time returns `422 SAME_SLOT`.
- Unknown body fields are rejected.

Deliberately skipped (see [Growth path](#9-growth-path)): a maximum booking horizon, name and phone format checks (owned by the external services) and rate limiting.

Services raise named domain errors; one exception handler turns them into HTTP responses. Pydantic validation errors use the same `{"code", "detail"}` shape.

| Code | Status | Raised when |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request shape is invalid (missing field, bad date, blank reason) |
| `DOCTOR_NOT_FOUND` / `PATIENT_NOT_FOUND` / `APPOINTMENT_NOT_FOUND` | 404 | The referenced ID does not exist |
| `OUTSIDE_WORKING_HOURS` | 422 | Not a working day, or the slot is not fully inside the doctor's hours |
| `SLOT_IN_PAST` | 422 | The slot is in the past |
| `SLOT_TOO_SOON` | 422 | The slot is less than 1 hour from now |
| `SLOT_NOT_ALIGNED` | 422 | The start time is not on `:00` or `:30` (EAT) |
| `SAME_SLOT` | 422 | Reschedule to the current time |
| `SLOT_TAKEN` | 409 | The slot is held by an active appointment |
| `ALREADY_CANCELLED` | 409 | Cancel or reschedule on a cancelled appointment |
| `REJECTED_NOT_CANCELLABLE` | 409 | Cancel or reschedule on a rejected appointment |
| `APPOINTMENT_EXPIRED` | 409 | The appointment's start has already passed |
| `INVALID_TRANSITION` | 409 | The status change is not allowed (for example approving a cancelled appointment, or completing before it starts) |
| `NOT_APPOINTMENT_DOCTOR` / `NOT_APPOINTMENT_OWNER` | 403 | The stated doctor or patient does not match the appointment |
| `IDEMPOTENCY_KEY_REUSED` | 409 | The same key was sent with a different request |
| `INTERNAL_ERROR` | 500 | Unexpected failure (details are never leaked) |
| `NOT_FOUND` / `HTTP_ERROR` | 404 / varies | Framework-level errors such as an unknown route |

**Status code meaning:** 404 the thing does not exist, 422 the input is invalid, 409 the input is valid but conflicts with the current state, 403 the stated actor does not match the appointment.

---

## 6. Testing

**73 tests, all passing:** 60 unit and 13 integration, none skipped.

| Level | What it covers |
|---|---|
| **Unit** (no database) | Booking rules, availability, cancel, reschedule, lifecycle transitions, time zone handling, clock injection, error mapping. They use the test-data directories and an injectable clock. |
| **Integration** (FastAPI with real PostgreSQL) | Double booking gives 201 then 409; concurrent requests for one slot produce exactly one winner and no 500; reschedule onto a taken slot leaves the original unchanged; rebooking after a cancel works (proves the partial index frees the slot); idempotency replay; error response shape. |

**Why integration tests despite the small API:** the double-booking and atomic-reschedule guarantees live in the database and cannot be proven with mocks.

**Not included:** end-to-end and load tests (there is no UI, the API is small, and the time limit is short). Code coverage has not been measured.

```bash
docker compose up -d testdb      # test database on host port 5433
.venv/bin/python -m pytest -q
```

Tests read `TEST_DATABASE_URL` and **delete data between tests**. Never point it at a real database.

---

## 7. Deployment and CI/CD

**Hosting:** the app runs as a container on **Render** (free web service, deployed from a Docker Hub image). The database is **Neon** (free PostgreSQL). All configuration comes from environment variables, and `DATABASE_URL` is set only in Render's dashboard.

**Branch that deploys:** `main`.

**Pipeline** (`.github/workflows/ci.yml`, GitHub Actions):

| Trigger | What runs |
|---|---|
| Every pull request | **`test` job:** starts a throwaway PostgreSQL service container, installs dependencies, runs migrations, runs the full test suite |
| Merge (push) to `main` | `test` runs again, then the **`deploy` job** (only if tests pass): log in to Docker Hub, build the image, push it tagged `latest` and with the commit SHA, then call Render's deploy hook |

- The deploy hook is called with an `imgURL` parameter naming the **commit-SHA image**, so Render deploys exactly the build CI just pushed, not whatever `latest` happens to point at.
- The test job's database URL is hardcoded to the throwaway container, so CI can never touch a real database.
- **Migrations run when the container starts** (`alembic upgrade head`, then `uvicorn` on Render's `$PORT`). Every deploy therefore brings the production schema up to date, and a failed migration fails the deploy instead of serving a broken app. Render's Pre-Deploy Command is intentionally unused.
- Secrets live in GitHub (`DOCKER_USERNAME`, `DOCKER_TOKEN`, `DEPLOY_HOOK_URL`). No secrets are in the repository.

---

## 8. Additions beyond the brief

| Addition | Why I added it | Cost or trade-off |
|---|---|---|
| **Approval flow** (`reserved` → `confirmed` / `rejected`) via `PATCH .../approve` and `.../reject` | A clinic must confirm a booking before it is final, and the doctor is the person who can. | More states, more endpoints and more tests. A `reserved` booking holds the slot until someone acts on it. |
| **`complete` and `no-show` endpoints** | Real appointments end in a visit or a missed visit. Recording the outcome keeps the lifecycle complete and the history truthful, and it enables later reporting. | Two more endpoints, and rules that they only apply after the start time. |
| **`GET /`** | A friendly response at the bare URL and a simple health check for the host. | None. |
| **`cancelled_by`** | Records whether the patient or the doctor cancelled. | One extra column. |
| **Error codes** (`code` plus `detail`) | Clients can react to a stable code instead of parsing messages. | Slightly more code to maintain. |
| **EAT handling** (offset-free input means EAT) | The brief is silent on time zones, and a Kenyan clinic's "10:00" means 10:00 EAT. | One documented assumption. |
| **Directory interfaces** | Makes the "booking service in a larger platform" assumption real in the code. | Two small interfaces and test-data implementations. |
| **Computed slots** | Nothing to keep in sync. | Availability is a snapshot. |
| **Optional `Idempotency-Key`** | Lets clients retry a booking safely after a timeout. | A small table. Optional, so it does not affect normal use. |

---

## 9. Growth path

**Built for growth now**

- Stateless container: scale by running more instances behind a load balancer.
- Slots are computed, so schedule changes need no data migration.
- Directory interfaces can swap to HTTP clients with no change to the booking rules.
- Concurrency is enforced in the database, so it stays correct with many instances.
- Time zones are isolated in one module and stored in UTC.

**Next steps as load or scope grows**

- Indexes on `(doctor_id, start_time)` and `(patient_id, start_time)`, then read replicas for availability queries.
- Cache doctor schedules fetched from the doctor service, with timeouts and retries for external calls.
- Publish appointment events (confirmed, cancelled, completed, no-show) so notification and billing services can react.
- Per-clinic time zones.
- Authentication and role checks at platform level.
- Also future: automatic expiry of stale `reserved` bookings, a cancellation window, an appointment history table, lunch breaks and longer visit types.

---

## 10. Run locally

**Prerequisites:** Python 3.12, Docker with Compose.

```bash
git clone https://github.com/Kalukwo/savannah-booking.git
cd savannah-booking
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # then set POSTGRES_PASSWORD
```

**Option A: Docker Compose (recommended)**

```bash
docker compose up --build
```

Starts three services: `db` (host port 5434), `testdb` (host port 5433, for tests) and `app` (port 8000). Migrations run automatically. Open http://localhost:8000/docs.

**Option B: uvicorn directly** (needs a local PostgreSQL, with `DATABASE_URL` set in `.env`)

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**Environment variables**

| Variable | Used for |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Docker Compose databases |
| `DATABASE_URL` | The app and Alembic. Compose builds it for you; Render sets it in production |
| `TEST_DATABASE_URL` | The test suite (see `.env.example`; it must point at the `testdb` service) |

**Run the tests:** see [Testing](#6-testing).

---

## 11. AI reflection

See [AI_REFLECTION.md](AI_REFLECTION.md).
