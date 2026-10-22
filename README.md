# Clinic Booking API

A booking service for a small clinic: 5 doctors, 30-minute slots. Patients see which slots are free, book one, and can cancel or reschedule. **A booked slot is never available to anyone else.**

**Reviewer summary:** I treat this as the booking microservice of a larger platform (my assumption, see 2.1). It owns appointments only — doctors and patients live in other services. The core guarantee (no double booking) is enforced by a **partial unique index** in PostgreSQL, not by application checks. Start at [/docs](https://clinic-api-latest-3axz.onrender.com/docs).

**Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async) + Alembic, PostgreSQL, Docker, GitHub Actions, Render, Neon.

| | |
|---|---|
| Live app | https://clinic-api-latest-3axz.onrender.com (free tier — first request after a pause can take 50s+) |
| Interactive API docs | https://clinic-api-latest-3axz.onrender.com/docs |
| Repository | https://github.com/Kalukwo/savannah-booking |
| AI reflection (Section 4 of the brief) | [AI_REFLECTION.md](AI_REFLECTION.md) |

**Quick try** in `/docs`: `GET /doctors/00000000-0000-4000-8000-000000000001/availability?date=<a weekday>`, then `POST /appointments` with one of the returned slots.

### Test-data UUIDs

Every ID is a UUID. Doctor and patient IDs are owned by other services, so I assume UUIDs, which cannot collide across services or be guessed in sequence. These are **fixed, hand-written values in the test data** (not `uuid4()` and not a seed script), so they are stable across runs and can be pasted into `/docs`.

**Doctors** — all work Monday to Friday; hours are EAT.

| Doctor | UUID | Working hours |
|---|---|---|
| Doctor 1 | `00000000-0000-4000-8000-000000000001` | 08:00 - 17:00 |
| Doctor 2 | `00000000-0000-4000-8000-000000000002` | 09:00 - 16:00 |
| Doctor 3 | `00000000-0000-4000-8000-000000000003` | 10:00 - 18:00 |
| Doctor 4 | `00000000-0000-4000-8000-000000000004` | 08:00 - 14:00 |
| Doctor 5 | `00000000-0000-4000-8000-000000000005` | 09:00 - 17:00 |

**Patients** — no schedule, no attributes beyond the UUID.

| Patient | UUID |
|---|---|
| Patient 1 | `00000000-0000-4000-8000-000000000101` |
| Patient 2 | `00000000-0000-4000-8000-000000000102` |
| Patient 3 | `00000000-0000-4000-8000-000000000103` |

Times without an offset are read as EAT (see [2.8](#28-time-zones)).

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
├── .github/workflows/ci.yml     - test on PR; test + deploy on merge to main
├── alembic/
│   └── versions/                - 0001_initial, 0002_pending_to_reserved, 0003_uuid_ids
├── app/
│   ├── api/routes/              - HTTP only: parse request, call one service, return response
│   ├── core/                    - config, errors, injectable clock, the only time zone module
│   ├── directories/
│   │   ├── base.py              - DoctorDirectory / PatientDirectory protocols
│   │   └── test_data/           - in-code stand-ins: 5 doctors, 3 patients
│   ├── models/                  - Appointment, IdempotencyKey
│   ├── repositories/            - all database queries
│   ├── schemas/                 - Pydantic request and response models
│   ├── services/                - all business rules
│   └── main.py
├── tests/
│   ├── unit/                    - no database
│   └── integration/             - real PostgreSQL
├── AI_REFLECTION.md             - AI reflection, Section 4 of the brief
├── docker-compose.yml
├── Dockerfile
├── requirements.txt / requirements-dev.txt
└── README.md
```

Routes hold no business rules, services hold no SQL, repositories hold no rules. Schema changes go through Alembic only.

---

## 2. System design

### 2.1 Assumptions (the brief is ambiguous, so these are my decisions)

| # | Ambiguity | Decision | Why |
|---|---|---|---|
| A | What is this service? | A **booking service inside a larger platform**. It owns appointments and the booking rules. | The clinic is "starting small but wants to grow"; a single-domain service can be plugged into others later. See [2.7](#27-why-there-are-no-doctor-or-patient-tables). |
| B | Where do doctor and patient data come from? | Two interfaces, `DoctorDirectory` and `PatientDirectory`, backed today by in-code test data. | Swapping in the real services changes no booking rule. See [2.7](#27-why-there-are-no-doctor-or-patient-tables). |
| C | Time zone | The clinic operates in **EAT**. | The brief never mentions time zones. See [2.8](#28-time-zones). |
| D | Who is calling? | **No authentication or registration.** The caller states their identity in the body and the API checks it against the appointment. | Out of scope. This enforces business rules but is **not security**: anyone can send any ID. Production would authenticate at platform level. |
| E | Do bookings need confirmation? | Yes — a booking is **reserved** and the assigned doctor approves or rejects it. | A clinic must confirm before a booking is final. See [Section 8](#8-additions-beyond-the-brief). |

### 2.2 Models

| Model | Fields |
|---|---|
| **Appointment** | `id`, `doctor_id`, `patient_id` (UUIDs), `start_time` (timestamptz, UTC), `status`, `cancel_reason`, `cancelled_by`, `created_at`, `updated_at` |
| **IdempotencyKey** | `key` (unique), `request_hash`, `response_status`, `response_body`, `created_at` |

**Key constraint:** a partial unique index on `(doctor_id, start_time) WHERE status NOT IN ('cancelled','rejected')`. It is the final guard against double booking, and it is *partial* so a cancelled slot can be booked again.

### 2.3 Components

```
Client → API routes → Services → Repositories → PostgreSQL
                         │
                         ├─ Directories (test data now, HTTP clients later)
                         └─ Time zone helper
```

### 2.4 Appointment lifecycle

Statuses: `reserved`, `confirmed`, `rejected`, `cancelled`, `completed`, `no_show`.

| Transition | Who | When |
|---|---|---|
| reserved → confirmed / rejected | assigned doctor | before start |
| reserved / confirmed → cancelled | owning patient **or** assigned doctor | before start, no cancellation window |
| reserved / confirmed → reserved (reschedule) | owning patient | before start; the new slot needs approval again |
| confirmed → completed / no_show | assigned doctor | after start |

`cancelled`, `rejected`, `completed` and `no_show` are final. Any other move returns `409 INVALID_TRANSITION`.

Slots held by `reserved`, `confirmed`, `completed` and `no_show` are unavailable; `cancelled` and `rejected` free the slot. A `reserved` appointment past its start time is expired and cannot be approved. Cancelling is allowed at any time before the start — no cancellation window — so slots free up as early as possible.

> **Naming note:** a new booking is `reserved`, because it holds the slot for the patient until the assigned doctor confirms it.

### 2.5 Slots are computed, not stored

`GET /doctors/{id}/availability?date=` runs on every call:

1. Read the doctor's schedule from `DoctorDirectory`.
2. If the date is not a working day, return an empty list.
3. Generate every 30-minute slot in the working day, in EAT.
4. Fetch that doctor's active appointments for the EAT day.
5. Remove taken, past, and less-than-1-hour-from-now slots.
6. Return the rest with a `+03:00` offset.

**Why:** nothing to keep in sync, schedule changes apply immediately, no pre-created rows. **Caveat:** availability is a snapshot, so booking may still return `409 SLOT_TAKEN`; the client re-fetches and picks another slot. A slot must end by closing time, so the last slot starts 30 minutes before it.

### 2.6 Architecture choice

**A single service with a layered structure** (routes → services → repositories → database) plus a thin integration boundary (the directories).

- **Why:** one domain, small scope, 3-5 day limit.
- **Considered and skipped:** clean/hexagonal architecture (more mapping code than this scope justifies) and per-domain modules (only one domain).
- **Trade-off:** the partial unique index is PostgreSQL-specific.
- Booking runs in one transaction, which the double-booking guarantee relies on.

### 2.7 Why there are no doctor or patient tables

This is a booking microservice, so it owns appointments and nothing else about people. Doctors and patients belong to the doctor service and the patient service; appointments store only their UUIDs, with no foreign keys (impossible across service databases) and no copied records (which would drift into a second source of truth).

- Working hours are read from the doctor service, because hours describe the doctor and a local copy would go stale.
- Patient details are never needed, only whether a patient exists, which is why `PatientDirectory` exposes only `exists()`.
- The booking rules depend only on the two protocols in `app/directories/base.py`, so real HTTP clients drop in without touching a rule.

In this submission the other services do not exist, so the directories are backed by test data in code: `DoctorTestDataDirectory` and `PatientTestDataDirectory` in `app/directories/test_data/`. There is no doctor table, no patient table and no seed script. An unknown UUID returns `404 DOCTOR_NOT_FOUND` or `PATIENT_NOT_FOUND`, never 422.

**Trade-off:** the service cannot validate a schedule offline, and a doctor-service outage can make availability unavailable, hence timeouts, retries and a short schedule cache in production (see [Section 9](#9-growth-path)).

### 2.8 Time zones

- Clinic zone is **EAT** (Africa/Nairobi, UTC+3, no DST). All conversion lives in `app/core/timezone.py`.
- Everything is **stored in UTC** and compared in UTC.
- Input **with** an offset is converted to UTC; input **without** one is read as **EAT**, so `"2027-03-01T10:00:00"` means 10:00 at the clinic.
- Working hours are EAT local times, judged in EAT (07:30 EAT is rejected even though 07:30 UTC would look "inside" the hours).
- Responses return times in EAT with a `+03:00` offset.
- **Growth:** several clinics would each carry their own zone; because times are stored in UTC and conversion is isolated, nothing stored would need migrating.

---

## 3. API reference

Interactive docs: `/docs`. Request bodies reject unknown fields. Errors use one shape: `{"code": "...", "detail": "..."}`.

| Method | Path | Body | Success | Source |
|---|---|---|---|---|
| POST | `/appointments` | `doctor_id`, `patient_id`, `start_time`; optional header `Idempotency-Key` | 201, status `reserved` | Brief |
| GET | `/doctors/{id}/availability?date=YYYY-MM-DD` | none | 200 | Brief |
| PATCH | `/appointments/{id}/cancel` | `reason`, `actor` (`patient` or `doctor`), `actor_id` | 200 | Brief |
| PATCH | `/appointments/{id}/reschedule` | `patient_id`, `start_time` | 200 | Brief |
| GET | `/patients/{id}/appointments` | none | 200, upcoming `reserved` and `confirmed`, sorted by start | Brief (bonus) |
| PATCH | `/appointments/{id}/approve` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/reject` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/complete` | `doctor_id` | 200 | **Addition** |
| PATCH | `/appointments/{id}/no-show` | `doctor_id` | 200 | **Addition** |
| GET | `/` | none | 200, short JSON message | **Addition** |

Every `{id}` in a path is a UUID. The brief's bonus "no bookings within 1 hour of now" is the `SLOT_TOO_SOON` rule.

**Example: book a slot** (no offset means EAT)

```http
POST /appointments
{
  "doctor_id":  "…0001",
  "patient_id": "…0102",
  "start_time": "2027-03-01T10:00:00"
}
```

```json
{
  "id": "…",
  "doctor_id": "…0001",
  "patient_id": "…0102",
  "start_time": "2027-03-01T10:00:00+03:00",
  "status": "reserved",
  "cancel_reason": null,
  "cancelled_by": null,
  "created_at": "…",
  "updated_at": "…"
}
```

`…0001` and `…0102` are the last four characters of the Doctor 1 and Patient 2 UUIDs listed at the top.

Use a future weekday: past slots return 422 `SLOT_IN_PAST`.

**Example: availability**

```json
{
  "doctor_id": "…0001",
  "date": "2027-03-01",
  "slots": ["2027-03-01T08:00:00+03:00", "2027-03-01T08:30:00+03:00", "…"]
}
```

The brief says "return all available 30-minute slots"; they are returned inside an object with the doctor and date, so the response is self-describing.

### Idempotency-Key (optional)

`POST /appointments` accepts an **optional** `Idempotency-Key` header. Without it, the endpoint behaves exactly as the brief describes: a repeated booking returns `409 SLOT_TAKEN`, so Swagger and Postman need not send it.

- **With a key:** the key, request hash and response are stored in the same transaction as the booking. The same key with the same body **replays** the stored response and creates no second booking; the same key with a **different** body returns `409 IDEMPOTENCY_KEY_REUSED`.
- Keys expire after 24 hours. Use a new key per booking, and reuse one only to retry that exact request.
- There is deliberately no automatic duplicate detection without a key — it would make a plain duplicate booking succeed, contradicting the brief's expected 409.

**Example: book with an idempotency key**

```http
POST /appointments
Idempotency-Key: 7c2f1a90-5d4b-4e21-9a77-1f3b6c8e0d42
{
  "doctor_id":  "…0001",
  "patient_id": "…0102",
  "start_time": "2027-03-01T10:00:00"
}
```

Send the **exact same request with the same key** again (for example after a timeout) and you get `201` with the *same* appointment `id` — no second booking is created:

```json
{
  "id": "…",
  "doctor_id": "…0001",
  "patient_id": "…0102",
  "start_time": "2027-03-01T10:00:00+03:00",
  "status": "reserved",
  …
}
```

Send the same key with a **different** body and you get:

```json
{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "detail": "Idempotency key was already used with a different request"
}
```


---

## 4. Concurrency and atomicity

Checks produce friendly errors, but **the database is the real guard**: two requests can both pass a check before either writes.

**Reschedule runs in one transaction:**

1. `SELECT ... FOR UPDATE` on the appointment (row lock).
2. Check its status, then validate the new slot exactly as for a fresh booking.
3. `UPDATE` the **same row**: new `start_time`, status back to `reserved`.
4. If another transaction holds the new slot, the unique index raises `IntegrityError`; the transaction rolls back and returns `409 SLOT_TAKEN`, leaving the original booking untouched.

One row is updated, so there is never a moment where the old slot is lost and the new one is not yet held.

| Race | Handled by |
|---|---|
| Two bookings for the same slot | Unique index: one gets 201, the other 409 |
| Reschedule and another booking on the target slot | Unique index |
| Reschedule and cancel on the same appointment | Row lock: the second waits, then sees the new status |
| Two reschedules of one appointment | Row lock, then re-validation |

The API is async (FastAPI, SQLAlchemy `AsyncSession`, `asyncpg`), one session per request, and uses no Python-level locks — those break as soon as more than one container runs.

---

## 5. Validation and errors

Validation happens at three levels: **input shape** (Pydantic), **business rules** (services) and **integrity** (database constraint). Every rule the brief asks for is covered, plus the checks correctness needs (a slot must end within working hours, the cancel reason is trimmed and capped at 500 characters, unknown body fields are rejected). Deliberately skipped: a booking horizon, name and phone formats (owned by the external services) and rate limiting.

Services raise named domain errors; one exception handler turns them into HTTP responses, and Pydantic failures use the same `{"code", "detail"}` shape.

| Code | Status | Raised when |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request shape is invalid (missing field, bad date, blank reason, unknown field, malformed UUID) |
| `DOCTOR_NOT_FOUND` / `PATIENT_NOT_FOUND` / `APPOINTMENT_NOT_FOUND` | 404 | The referenced UUID does not exist (a well-formed unknown UUID is 404, not 422) |
| `OUTSIDE_WORKING_HOURS` | 422 | Not a working day, or the slot is not fully inside the doctor's hours |
| `SLOT_IN_PAST` | 422 | The slot is in the past |
| `SLOT_TOO_SOON` | 422 | The slot is less than 1 hour from now |
| `SLOT_NOT_ALIGNED` | 422 | The start time is not on `:00` or `:30` (EAT) |
| `SAME_SLOT` | 422 | Reschedule to the current time |
| `SLOT_TAKEN` | 409 | The slot is held by an active appointment |
| `ALREADY_CANCELLED` / `REJECTED_NOT_CANCELLABLE` / `APPOINTMENT_EXPIRED` | 409 | Cancel or reschedule on a cancelled, rejected or expired appointment |
| `INVALID_TRANSITION` | 409 | The status change is not allowed |
| `NOT_APPOINTMENT_DOCTOR` / `NOT_APPOINTMENT_OWNER` | 403 | The stated actor does not match the appointment |
| `IDEMPOTENCY_KEY_REUSED` | 409 | The same key was sent with a different request |
| `INTERNAL_ERROR` | 500 | Unexpected failure (details are never leaked) |
| `NOT_FOUND` / `HTTP_ERROR` | 404 / varies | Framework-level errors such as an unknown route |

**Status code meaning:** 404 the thing does not exist, 422 the input is invalid, 409 the input is valid but conflicts with current state, 403 the stated actor does not match.

---

## 6. Testing

**74 tests, all passing:** 60 unit and 14 integration, none skipped.

| Level | What it covers |
|---|---|
| **Unit** (no database) | Booking rules, availability, cancel, reschedule, lifecycle transitions, time zones, clock injection, error mapping. |
| **Integration** (FastAPI + real PostgreSQL) | Concurrency and atomicity (see [Section 4](#4-concurrency-and-atomicity)), plus idempotency replay and error response shape. |

**Why integration tests despite the small API:** the double-booking and atomic-reschedule guarantees live in the database and cannot be proven with mocks.

**Not included:** end-to-end and load tests (no UI, small API, short time limit). Coverage has not been measured.

```bash
docker compose up -d testdb      # test database on host port 5433
.venv/bin/python -m pytest -q
```

Tests read `TEST_DATABASE_URL` and **delete data between tests**. Never point it at a real database.

---

## 7. Deployment and CI/CD

**Hosting:** a container on **Render** (free web service, deployed from a Docker Hub image) with **Neon** (free PostgreSQL). All configuration comes from environment variables; `DATABASE_URL` is set only in Render's dashboard.

**Branch that deploys:** `main`.

| Trigger | What runs |
|---|---|
| Every pull request | **`test`:** throwaway PostgreSQL service container, install dependencies, run migrations, run the full suite |
| Merge to `main` | `test` again, then **`deploy`** if tests pass: log in to Docker Hub, build and push the image tagged `latest` and with the commit SHA, then call Render's deploy hook |

- The deploy hook passes an `imgURL` naming the **commit-SHA image**, so Render deploys exactly what CI just built, not whatever `latest` points at.
- The test job's database URL is hardcoded to the throwaway container, so CI can never touch a real database.
- **Migrations run at container start** (`alembic upgrade head`, then `uvicorn` on Render's `$PORT`), so every deploy brings the schema up to date and a failed migration fails the deploy. Render's Pre-Deploy Command is intentionally unused.
- Secrets live in GitHub (`DOCKER_USERNAME`, `DOCKER_TOKEN`, `DEPLOY_HOOK_URL`). No secrets are in the repository.

---

## 8. Additions beyond the brief

- **Approval flow** — `POST`/`PATCH .../approve` and `.../reject`, so a booking is `reserved` until the assigned doctor confirms it ([2.4](#24-appointment-lifecycle), [3](#3-api-reference)).
- **`complete` and `no-show` endpoints** — real appointments end in a visit or a missed visit; recording it keeps history truthful ([2.4](#24-appointment-lifecycle)).
- **`GET /`** — a friendly bare URL and a health check for the host.
- **`cancelled_by`** — records whether the patient or the doctor cancelled.
- **Stable error codes** (`code` + `detail`) — clients react to a code instead of parsing messages ([5](#5-validation-and-errors)).
- **Optional `Idempotency-Key`** — safe retry after a timeout ([3](#3-api-reference)).

Time zones, computed slots and the directory interfaces are covered in [2.8](#28-time-zones), [2.5](#25-slots-are-computed-not-stored) and [2.7](#27-why-there-are-no-doctor-or-patient-tables).

---

## 9. Growth path

- Indexes on `(doctor_id, start_time)` and `(patient_id, start_time)`, then read replicas for availability queries.
- Cache doctor schedules with timeouts and retries for external calls.
- Publish appointment events (confirmed, cancelled, completed, no-show) for notification and billing services.
- Per-clinic time zones.
- Authentication and role checks at platform level.
- Later: automatic expiry of stale `reserved` bookings, a cancellation window, an appointment history table, lunch breaks and longer visit types.

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

**Option A: Docker Compose (recommended)** — `docker compose up --build` starts `db` (host port 5434), `testdb` (host port 5433, for tests) and `app` (port 8000). Migrations run automatically.

**Option B: uvicorn directly** (needs a local PostgreSQL, with `DATABASE_URL` in `.env`)

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

| Variable | Used for |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Docker Compose databases |
| `DATABASE_URL` | The app and Alembic. Compose builds it; Render sets it in production |
| `TEST_DATABASE_URL` | The test suite — must point at `testdb` |

Run the tests: see [Section 6](#6-testing).

---

## 11. AI reflection

See [AI_REFLECTION.md](AI_REFLECTION.md).
