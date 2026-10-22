# AI Reflection (Section 4)

**My AI setup:** an **OpenClaw agent running in my VM, with DeepSeek as its base model**. I used **Claude** (in a chat) as a reference to think through decisions and to review what the agent produced. I supplied the talking points for this file, and AI wrote the raw text.

## 1. What did I use AI for across the four sections?

- **Section 1 (system design):** AI was a sounding board. I compared repo and architecture structures (layered, clean, modular), the approval flow, and authentication.
- **Section 2 (API implementation):** AI wrote the raw code. I wrote the build instructions in a chat with Claude, and the OpenClaw agent produced the code from them.
- **Section 3 (deployment and CI/CD):** AI wrote the raw GitHub Actions workflow files, and Claude helped me debug the failing pipeline.
- **Section 4 (this reflection):** AI scaffolded this file and wrote the raw text. I provided all of the talking points.

## 2. One example where an AI suggestion improved my work

**Running migrations when the container starts.**

- **What happened:** after the first deploy to Render, `GET /doctors/{id}/availability` returned a 500. I pasted the 500 response, and then the Render log traceback, into Claude.
- **The cause:** the traceback ended in `relation "appointments" does not exist`. The migrations had never run against the production database. My agent's Dockerfile left migrations to a Render Pre-Deploy Command that was never set, and CI only migrated the throwaway test database, so the tests passed while production had no tables.
- **The suggestion:** Claude suggested running `alembic upgrade head` in the container's start command, so every deploy migrates the real database before serving traffic, and a failed migration fails the deploy instead of leaving a broken app running.
- **The result:** I had my agent make the change. After the next merge the pipeline ran the migration on its own and the live endpoint worked. The same change also made the container use Render's `$PORT`, and made Alembic use the same URL normaliser as the app, so it no longer breaks on Neon's `sslmode` setting.

## 3. One example where AI output was wrong or incomplete, and how I caught it

**A UUID change that broke an untested code path.**

- **What happened:** the project's IDs were moved from integers to UUIDs, and my agent applied the change across about 25 files. It missed one place: `idempotency.py` still hashed the request body with `json.dumps`, written when IDs were integers. UUID objects cannot be serialised to JSON.
- **How I caught it:** the test suite. 72 of 74 tests passed, including booking, availability, cancel, reschedule and concurrency. The two idempotency tests failed with `TypeError: Object of type UUID is not JSON serializable`, and the traceback pointed straight at the `json.dumps` call.
- **The fix:** one argument, `default=str`.
- **Why it matters:** that code only runs when a client sends an `Idempotency-Key` header. Without the integration tests, it would have shipped and broken for exactly the clients the header exists for: those retrying after a timeout.

## 4. Two decisions I made without AI, and why I trusted my own judgment

### Decision 1: a booking service with no doctor or patient tables

- **The decision:** I decided this should be a service that depends on a main service which owns doctors and patients. It stores only their IDs, and reads their details (including working hours) through directory interfaces. The brief does not say this. I raised the idea myself, and it shaped the directory interfaces, the layered structure and the assumptions section of the README. I discussed the details with Claude afterwards.
- **Why I trusted my own judgment:** my experience with microservices. It gave me the conviction that this assessment suits a production booking API that expands an already existing system, not a standalone app that owns every table.

### Decision 2: no authentication or registration

- **The decision:** I first planned JWT authentication with roles, using a design worked out with Claude, and then removed it. Authentication and registration are not part of the brief, and I treated them as an architectural concern: in the platform this service belongs to, another service would handle identity. The API therefore takes the caller's stated ID and checks it against the appointment. This enforces the business rules but is not real security, and the README says so.
- **Why I trusted my own judgment:** it follows from my understanding of how a microservice platform is split. Identity is owned by a separate service, so building login and registration inside the booking service would blur the boundary I had chosen.
