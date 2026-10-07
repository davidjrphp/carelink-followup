# C. Code review

**Severity scale**
- **Critical:** can harm a patient, leak data or lose clinical records.
- **Major:** breaks a feature, fails under load or excludes users.
- **Minor:** maintainability or style.

## C1: `PatientService` (back end)

| # | Problem | Practical risk in a clinic | Severity |
|---|---|---|---|
| 1 | **SQL injection.** `q`, `facility`, `Notes` and `VisitDate` are concatenated into SQL | A search box or a visit note can read or delete any patient at any facility. A note containing an apostrophe (`O'Brien`) simply fails | Critical |
| 2 | **Exceptions swallowed in `SaveEncounter`** (`catch { // ignore }`) | The nurse sees "saved"; the visit is gone. The patient later shows as missed and is wrongly chased, or a real follow-up is lost | Critical |
| 3 | **Two writes with no transaction** (insert encounter, update patient) | The encounter exists but `last_visit_date` is stale, or the reverse, so follow-up lists disagree with the record | Critical |
| 4 | **Hard-coded connection string using `sa`** with a password in source | Anyone with repository access has full database admin. A leak exposes every patient. The password cannot be rotated without a release | Critical |
| 5 | **No authorisation.** `userRole` is only logged; `facility` comes from the caller; `DueForFollowUp` passes `"system"` | Any user can search any facility's patients | Critical |
| 6 | **Personal data in logs.** The search term (a patient name) and `NationalId` are written to logs | Logs are copied widely and kept long, so health data leaks outside access controls | Critical |
| 7 | **Connections, commands and readers never disposed** | The pool is exhausted under morning peak (3,000 users), and the system stops for everyone | Major |
| 8 | **`DueForFollowUp` logic is wrong.** It adds the patient once per past appointment, ignores "most recent visit", ignores "no visit since", and has no threshold | Duplicates in the list; patients who did attend are chased | Major |
| 9 | **N+1 queries and in-memory filtering.** It loads every patient, then visits per patient | Thousands of queries per request; times out at 10,000+ patients | Major |
| 10 | **Unbounded results, `SELECT *`.** An empty `q` returns the whole facility | Slow pages; over-fetches sensitive columns | Major |
| 11 | **`DateTime.Now` and string-formatted dates** | Server time zone or locale shifts dates by a day; wrong "overdue" counts | Major |
| 12 | Leading-wildcard `LIKE '%q%'` cannot use an index | Slow search at scale | Minor |
| 13 | Static connection string, no dependency injection, synchronous I/O | Hard to test and configure per environment | Minor |

**Required before merge**
1. **#1 SQL injection.**
2. **#2 and #3 together, silent data loss.** Make the save atomic and let failures surface.
3. **#4 and #6 together, secrets and personal data out of code and logs.**

#5 is also critical. In practice it blocks merge too, but the fix belongs in the shared authorisation layer rather than this class (see Section B), so I track it as a linked ticket.

## C2: `FollowUpList` (front end)

| # | Problem | Practical risk in a clinic | Severity |
|---|---|---|---|
| 1 | **Contract mismatch.** It sends `facility` (the API expects `facility_id`) and treats the response as an array (the API returns `{page, total, items}`) | The list is empty or the screen crashes. Staff conclude nobody needs follow-up | Critical |
| 2 | **No error handling.** `r.ok` is never checked and there is no `.catch` | When the API fails, the screen shows "loading" forever, or crashes on an error body. There is no retry | Critical |
| 3 | **`markContacted` is fire-and-forget.** It mutates state directly and sends no body (`contacted_at` is required) | Contact attempts are silently not saved, so patients are phoned twice or not at all. The row may not even re-render | Critical |
| 4 | **Polling every 3 s; the effect has no dependency array** | Each user downloads the full list every 3 s. With 3,000 users this is ~1,000 large requests per second, which takes the platform down and burns clinic data bundles. The interval is also recreated on every render | Major |
| 5 | **Sort effect mutates state in place** and sets the same reference | The sort is unreliable; it can loop or simply not apply | Major |
| 6 | **Race conditions.** Responses for an old facility, or a late poll, overwrite newer data | A clinician sees the wrong facility's patients | Major |
| 7 | **Not keyboard-operable.** "Mark contacted" is a `div` with `onClick`; the input has no label | Keyboard-only staff, and screen-reader users, cannot complete the task | Major |
| 8 | **Status conveyed only by red text** | Colour-blind staff and monochrome screens miss overdue patients | Major |
| 9 | **Renders every row** and filters only the page held in the browser | Freezes 4 GB machines at 10,000 rows; the name filter misses patients on other pages | Major |
| 10 | **`key={i}` on a sortable list** | Row state attaches to the wrong patient after sorting | Major |
| 11 | **Facility hard-coded** to `FAC-0101`; no auth header | Wrong data for every other clinic; requests fail once auth is enforced | Major |
| 12 | `fetch` inside the component; `any` everywhere; no `encodeURIComponent` | Untestable and untyped; contract drift goes unnoticed | Minor |
| 13 | Loading state is not announced to assistive technology | Screen-reader users don't know the list is loading | Minor |

**Required before merge:** #1 contract mismatch, #2 error handling, #3 silent contact-attempt loss.

## Refactor: C1

**Why C1.** Its critical problems cause **silent clinical data loss and a full data breach**. Those are harder to detect and harder to undo than C2's failures, which at least break visibly. It is also the back-end code nearest my Section B work.

**Addressed:** SQL injection (#1); silent failure and the non-atomic write (#2, #3); secrets and personal data in logs (#4, #6).

**Deliberately not addressed here:**
- `DueForFollowUp` is replaced by the database query in Section B.
- Authorisation (#5) moves to the shared policy layer.

```csharp
public sealed class PatientService
{
    private readonly string _connString;          // from configuration / secret store, least-privilege login
    private readonly ILogger<PatientService> _log;

    public PatientService(IOptions<DbOptions> db, ILogger<PatientService> log)
    {
        _connString = db.Value.ConnectionString;  // not in source control; not 'sa'
        _log = log;
    }

    public async Task<IReadOnlyList<Patient>> SearchAsync(
        string q, string facilityId, int limit = 50, CancellationToken ct = default)
    {
        const string sql = @"
            SELECT id, facility_id, patient_number, first_name, last_name, date_of_birth, sex
            FROM patient
            WHERE facility_id = @facility
              AND (first_name LIKE @pattern OR last_name LIKE @pattern)
            ORDER BY last_name, first_name
            OFFSET 0 ROWS FETCH NEXT @limit ROWS ONLY";

        await using var conn = new SqlConnection(_connString);
        await conn.OpenAsync(ct);
        await using var cmd = new SqlCommand(sql, conn);
        cmd.Parameters.Add("@facility", SqlDbType.VarChar, 16).Value = facilityId;
        cmd.Parameters.Add("@pattern", SqlDbType.NVarChar, 102).Value = "%" + EscapeLike(q) + "%";
        cmd.Parameters.Add("@limit", SqlDbType.Int).Value = Math.Clamp(limit, 1, 200);

        var results = new List<Patient>();
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct)) results.Add(Map(reader));

        // No search term, names or national IDs in logs: only what operations needs.
        _log.LogInformation("patient_search facility={Facility} result_count={Count}",
                            facilityId, results.Count);
        return results;
    }

    public async Task SaveEncounterAsync(Encounter e, CancellationToken ct = default)
    {
        await using var conn = new SqlConnection(_connString);
        await conn.OpenAsync(ct);
        await using var tx = (SqlTransaction)await conn.BeginTransactionAsync(ct);
        try
        {
            await using (var insert = new SqlCommand(
                "INSERT INTO encounter (patient_id, visit_date, notes) VALUES (@pid, @date, @notes)",
                conn, tx))
            {
                insert.Parameters.Add("@pid", SqlDbType.BigInt).Value = e.PatientId;
                insert.Parameters.Add("@date", SqlDbType.Date).Value = e.VisitDate.Date;
                insert.Parameters.Add("@notes", SqlDbType.NVarChar, -1).Value = (object?)e.Notes ?? DBNull.Value;
                await insert.ExecuteNonQueryAsync(ct);
            }

            await using (var update = new SqlCommand(
                @"UPDATE patient SET last_visit_date = @date
                  WHERE id = @pid AND (last_visit_date IS NULL OR last_visit_date < @date)",
                conn, tx))
            {
                update.Parameters.Add("@pid", SqlDbType.BigInt).Value = e.PatientId;
                update.Parameters.Add("@date", SqlDbType.Date).Value = e.VisitDate.Date;
                if (await update.ExecuteNonQueryAsync(ct) == 0 && !await PatientExists(conn, tx, e.PatientId, ct))
                    throw new NotFoundException($"patient {e.PatientId} not found");
            }

            await tx.CommitAsync(ct);
        }
        catch (Exception ex)
        {
            await tx.RollbackAsync(ct);
            _log.LogError(ex, "save_encounter_failed patient_id={PatientId}", e.PatientId);
            throw;   // the caller returns a 4xx/5xx; the clinician is told it did NOT save
        }
    }

    private static string EscapeLike(string s) =>
        (s ?? "").Replace("[", "[[]").Replace("%", "[%]").Replace("_", "[_]");
}
```

**What changed and why**
- **Parameters everywhere.** Injection is no longer possible, and names with apostrophes now save.
- **Atomic save.** Both writes commit together or not at all. A failure is logged with a correlation-friendly ID, then re-thrown, so the user knows the visit was not saved.
- **No secrets or personal data.** The connection string is injected from configuration and uses a least-privilege login. Logs carry facility and count only.
- **Bounded, explicit columns.** Searches return a limited set of named columns, and connections are always disposed (`await using`), which also fixes #7 and #10 along the way.
- **Safer `last_visit_date`.** It only moves forward, so a late-synced older visit cannot overwrite a newer date.
