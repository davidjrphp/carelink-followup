# A. Architecture: CareLink Follow-Up

## Summary

Follow-Up is a **module in one modular monolith**: one FastAPI codebase, one PostgreSQL database per deployment. The same build runs in two places:

- a **facility node** at the ~1,100 clinics with intermittent or no connectivity, so losing the internet never stops clinical work;
- the **national platform** in an in-country data centre, which also hosts the ~400 well-connected clinics as virtual facility instances and owns identity, integrations and district/national views.

Nodes and the national platform exchange data only through an idempotent, versioned sync API.

**Assumptions**
1. CareLink already runs a database at each facility (Section G mentions "every facility database"), so Follow-Up deploys onto existing nodes rather than new hardware.
2. District officers need patient-level lists for their own district only; national users need aggregates, with audited exceptions.
3. The laboratory system speaks FHIR R4 or HL7 v2 through an adapter; the reporting platform takes aggregate indicators (DHIS2-style).

## 1. Components and communication

![CareLink Follow-Up architecture: a facility site (browser, facility node, PostgreSQL) talks to the national platform (gateway, national API, sync service, Keycloak, PostgreSQL, integration workers, monitoring) only through the sync API; integration workers exchange FHIR R4 / HL7 messages with the laboratory system and send nightly aggregates to the reporting platform.](diagrams/architecture.svg)

- **Browser:** React + TypeScript progressive web app. A service worker caches the app itself; the browser keeps only a small encrypted working cache and an outbox (D2).
- **Facility node:** modules call each other in-process. PostgreSQL holds the facility's patients, visits, contact attempts and sync outbox. The follow-up list is computed locally, so it needs no internet.
- **National platform:** the same API in national mode, plus a sync service and integration workers that read a PostgreSQL outbox.
- **Communication:** REST/JSON over HTTPS. Between tiers, the only path is the sync API.

## 2. Data approach

| Data | Facility | National |
|---|---|---|
| Patients, visits, contact attempts | Its own (authoritative for new local records) | Copy of all facilities |
| Lab results | Received via sync | Received from lab, routed to facility |
| Users and roles | Signed copy of local users | Authoritative |
| District/national views, indicators | No | Yes |

**Reconciliation**
- Every record gets a **UUIDv7 where it is created**, so offline creation never collides. `patient_number` stays the human identifier.
- Each change carries `version`, `updated_by` and `origin_node`. The node pushes its outbox in order, then pulls changes since its last cursor.
- **Visits and contact attempts are append-only**, so they never conflict. Only demographic edits can conflict; clinical fields go to human review, never last-write-wins (D2.3).
- A **daily checksum** of counts per table and per follow-up status flags any drift between facility and national copies.

## 3. API approach

- REST, **OpenAPI-first**, versioned: `/api/v1` for clients, `/sync/v1` for nodes. One error shape everywhere. Contract tests in CI, because 1,500 nodes will never all run the same version.
- Every write accepts an `Idempotency-Key` (D1).
- **Laboratory:** only the national platform talks to the lab, via FHIR R4 `ServiceRequest`/`DiagnosticReport`. Results are routed to the facility on its next pull, so the lab never deals with 1,500 endpoints and offline clinics get results on reconnect.
- **Reporting platform:** nightly aggregate indicators per facility and month (missed, contacted, returned to care). No patient-level data leaves.
- **Outbox pattern:** the outbound message is written in the same transaction as the change and delivered by a worker with retries, so CareLink and external systems cannot silently disagree.

## 4. Authentication and authorisation

| Role | Scope | Access | Offline |
|---|---|---|---|
| Clinician | Own facility | Read and write patients, visits, contact attempts | Yes |
| Facility administrator | Own facility | Clinician access + audit, sync status, conflicts, local account lock | Yes |
| District officer | Own district | Read-only patient-level lists | No |
| National user | All | Aggregates; audited patient-level exceptions | No |

- Keycloak issues OIDC tokens carrying role and facility or district scope. Accounts are personal, so the audit log names a person.
- One policy layer on the server checks role, scope and the record's facility on every request. The client only hides what the server would refuse. Every patient-level read is audited.
- **Offline:** the node holds a signed list of its users with salted password verifiers. Users who logged in online within **14 days** can log in offline; sessions last 8 hours and lock after 5 idle minutes. Revocations apply at the next sync, and a facility administrator can lock an account locally at once. District and national roles never log in at a facility node.

## 5. Client behaviour when offline for days

Clinics with a node keep working normally: registration, visits, the follow-up list and contact attempts. A banner shows "Offline since Mon 09:12 · 43 changes waiting". Features that need the national platform (new lab results, transfers in) are labelled unavailable rather than failing. On reconnect, sync resumes where it stopped; conflicts and rejected changes go to a "Needs review" list. Clinics without a node use the browser-only mode described in D2.

## 6. Monitoring, in clinic terms

| What a clinic would ask | Measure | Alert |
|---|---|---|
| Does the list open without waiting? | p95 response time per facility | Over 3 s for 15 min |
| Is anything stuck that we think we sent? | Changes waiting; age of oldest | Over 24 h while online |
| Which clinics have gone quiet? | Hours since last sync | Over 72 h, listed by district |
| Are lab results reaching us? | Lab result to facility time | Over 24 h |
| Do clinic and national numbers agree? | Daily checksum | Any mismatch |
| Did the last release hurt anyone? | Errors per facility, before and after | Rise in the pilot ring |

Logs are structured JSON with correlation IDs and no names, phone numbers or national IDs.

## 7. Deployment and in-country data

- National platform in a Ministry data centre or accredited in-country provider. Data, backups, logs and the disaster-recovery site all stay in-country, with no dependency on foreign cloud services. Encrypted nightly backups, with restores tested monthly.
- Facility nodes run Docker Compose and pull signed images from a national registry when connected.
- **Releasing while clinics are open:** expand/contract migrations so old and new versions coexist; the sync protocol accepts the current and previous version; feature flags; rings of 10, then 100, then all facilities with a 48-hour watch each; blue-green swap nationally and a one-command rollback on nodes.

## 8. Five largest technical risks

| Risk | Clinic impact | Mitigation |
|---|---|---|
| Sync duplicates or loses records | Wrong history, missed follow-ups | Client UUIDs, idempotency keys, append-only events, daily checksum |
| Same person registered at several facilities | "Missed" at one clinic while attending another | Candidate matching; human-confirmed, reversible, audited merges |
| A release breaks clinics or versions drift | Care interrupted at many sites | Rings, expand/contract, protocol versioning, rehearsed rollback |
| Old hardware chokes on 10,000-row lists | Staff abandon the tool | Server-side filtering and paging, row virtualisation, performance budget on a 4 GB machine |
| Patient data exposed on shared PCs or nodes | Legal and ethical harm | Encryption at rest, short sessions, minimal browser cache, no personal data in logs, read auditing |

## Trade-offs

1. **Modular monolith over microservices.** Nine engineers and nine months is too small a team to operate distributed services, and a facility node must be one deployable unit on modest hardware. Module boundaries are enforced in code, so a module can be extracted later if national load demands it.
2. **Facility node over a browser-only offline client.** With browser-only storage, two computers in one clinic cannot see each other's offline work, and large patient caches would sit on shared 4 GB PCs. The cost is operating ~1,100 nodes, acceptable because CareLink already runs facility databases.
3. **PostgreSQL outbox over Kafka.** I have worked with Kafka and it excels at high-volume streaming, but this load is modest and the outbox gives transactional "write and publish" with one less system to run and secure in-country. I would revisit if event volume or consumers grow sharply.
4. **Human review over last-write-wins for clinical conflicts.** Clinic clocks drift, and silently discarding a clinician's edit is unsafe. The cost is a review queue, kept small by making most data append-only.
