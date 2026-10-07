# D. Resilience, offline working and data integrity

Principle throughout: **replaying must be safe by design, and clinical data is never silently overwritten or deleted.**

## D1: Duplicate submissions

### 1. Making replay safe in the API

Two layers, so safety does not rest on one mechanism.

**Client-chosen identity.** Every new patient, visit and contact attempt gets a **UUIDv7 generated on the device when it is recorded**. A create becomes "create *this* record": if the ID already exists with the same content, the server returns the existing record instead of inserting again. This protection never expires.

**Idempotency keys.** Every write carries an `Idempotency-Key`. The server stores `(facility_id, key)` as unique, with a hash of the request and the original response, **in the same transaction as the write**:

| Situation | Server response |
|---|---|
| Same key, same request, completed | The stored response; nothing is written again |
| Same key, different request | `409 IDEMPOTENCY_KEY_REUSED` (a client bug, never guessed at) |
| Same key, still in progress | `409 IN_PROGRESS`; client retries later |

The sync endpoint accepts batches but applies and acknowledges **each operation separately**, so a time-out mid-batch leaves a clear record of what landed.

### 2. What the client must do

- Generate the key and record IDs **once, when the user saves**, and store them with the queued operation. Never regenerate on retry: the incident happened because the whole queue was re-sent as new requests.
- Keep the outbox durable (node database, or IndexedDB in the browser).
- Mark an operation done only on acknowledgement, and resume from the first unacknowledged one.
- Send a patient before that patient's visits.

### 3. How long the state is kept

Idempotency records are kept **30 days** (configurable): well beyond the longest expected outage. A nightly job removes older ones. After that, creates remain protected by their client IDs, and the server rejects any queued operation older than 30 days with `409 STALE_OPERATION`, routing it to "Needs review" rather than applying it blindly. A queue that old also raises a monitoring alert.

### 4. Cleaning up existing duplicates

Ship the fix first, then clean up.

**Visits.** Candidates are visits for the same patient, date, type and content, created within the incident's replay window. The extra copy is **voided**, not deleted: `voided = true`, a reason, a link to the surviving visit, and an audit entry. If the content differs at all, a person decides.

**Patients.** These are clinical identities, and the lab may already reference them.
1. A script lists candidate pairs (same facility, name, date of birth and sex, created in the incident window), with the reason each matched.
2. The facility's data manager or clinician confirms each pair. Nothing merges automatically.
3. The merge moves visits, contact attempts and lab links to the surviving record. The other becomes a tombstone, "merged into X", keeping its `patient_number` as an alias so paper and lab references still resolve.
4. Merges are audited and reversible for a set period.
5. Before-and-after counts go to the programme so reported figures can be corrected and explained.

## D2: Working through an outage

### 1. What is cached, where, and for how long

**Clinics with a facility node:** an internet outage never reaches the browser. The node keeps the facility's full working data on an encrypted disk. The browser holds only:

| What | Where | How long |
|---|---|---|
| App shell | Service worker cache | Until the next release |
| Current list page: name, patient number, appointment date, status, phone | IndexedDB, encrypted | Until logout, at most 24 h |
| Pending actions | IndexedDB outbox, encrypted | Until acknowledged |

**Clinics served directly by the national platform:** the browser caches the facility's follow-up list with the same minimal fields for up to **72 hours**, then marks it "possibly out of date", and queues contact attempts and visits in the outbox.

### 2. Synchronising queued actions

- **Order:** first-in, first-out per record; a visit waits for its patient. Batches of about 50, then a pull of changes since the last cursor.
- **Retry and back-off:** network errors, time-outs, `429` and `5xx` retry with exponential back-off and random jitter (about 2 s, 4 s, 8 s, capped at 5 minutes), honouring `Retry-After`. Jitter stops hundreds of clinics hitting the server in the same second when a regional link returns.
- **Partial failure:** each operation is acknowledged individually, so the queue resumes exactly where it stopped. Validation errors (`400`/`422`) are not retried: that operation and its dependants move to "Needs review" with the server's message, while unrelated work keeps flowing.
- **Visible to staff:** "Synced 14:02 · 43 waiting · 2 need review".

### 3. Monday offline edit, Tuesday central change, Wednesday reconnect

**What happens.** Each editable record has a `version`. Monday's edit records the version it started from (v3). On Wednesday the server sees v4 and compares field by field:
- **Different fields changed:** both changes are kept and the merge is audited.
- **Same field changed:** Tuesday's value stays live. Monday's edit is held as a **conflict**, neither applied nor discarded. Timestamp-based last-write-wins is rejected because clinic clocks drift.
- **Visits and contact attempts** are append-only, so both days' entries are kept.

**What the user sees.** "1 change needs your review", showing both values side by side with who made each and when, and three choices: *Keep current*, *Use mine*, *Edit*. The record is marked "pending review" until resolved.

**Who decides.** The clinician who made the offline edit, since they know what they saw on Monday. After 3 days it escalates to the facility administrator. The system never chooses a clinical value on its own.

### 4. Protecting data on a shared clinic computer

- Personal accounts only; lock after 5 idle minutes; browser cache **wiped on logout**.
- Browser data encrypted with AES-GCM under a per-session key held only in memory, so it is unreadable once the session ends.
- Facility nodes: full-disk encryption, a non-administrator database login, encrypted backups, unreachable from outside the clinic network.
- No personal data in URLs, logs or crash reports. Every patient-level read is audited.

**What I would refuse to store in the browser at all:** clinical notes, diagnoses, lab results, HIV or other sensitive programme status, national ID numbers, passwords or long-lived refresh tokens, anything in `localStorage`, and any CSV or USB export of patient lists.
