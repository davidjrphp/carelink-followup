"""Before/after evidence for the follow-up query on the seeded 100k/400k dataset.

    make bench-api      (runs: python -m scripts.bench_api inside the api container)

"Before" swaps the composite visit index for a plain visit(patient_id) index inside a transaction
that is rolled back (PostgreSQL DDL is transactional), so the database is never left changed. Each variant runs warm-up queries, then
reports the median of N timed runs of EXPLAIN ANALYZE execution time, and the median end-to-end HTTP
time for the real endpoint (which always has the index).
"""
import re
import statistics
import time
import urllib.request

from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.followup import repository as repo
from app.followup.schemas import DEFAULT_STATUSES, SortOrder

RUNS = 7
FACILITY = "FAC-0101"


def explain_ms(conn, sql: str, binds: dict) -> tuple[float, str]:
    plan = conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql), binds).scalars().all()
    total = float(re.search(r"Execution Time: ([\d.]+) ms", plan[-1]).group(1))  # type: ignore[union-attr]
    return total, "\n".join(plan)


def page_query() -> tuple[str, dict]:
    settings = get_settings()
    rule = repo.RuleParams(today=settings.today(), overdue_days=7,
                           missed_window_days=settings.missed_window_days,
                           due_soon_days=settings.due_soon_days)
    # Reuse the production SQL text exactly, with literal statuses for EXPLAIN.
    order_by = repo._ORDER_BY[SortOrder.DAYS_OVERDUE_DESC]
    sql = f"""
        WITH {repo._CLASSIFIED_CTE.format(search="")},
        page AS (
            SELECT c.*, count(*) OVER () AS total FROM classified c
            WHERE c.follow_up_status IN ('missed', 'overdue')
            ORDER BY {order_by} LIMIT 50 OFFSET 0
        )
        SELECT page.*, f.name, lc.last_contact_attempt FROM page
        JOIN facility f ON f.facility_id = page.facility_id
        LEFT JOIN LATERAL (SELECT max(contacted_at) AS last_contact_attempt FROM contact_attempt ca
                           WHERE ca.patient_id = page.id) lc ON true
        ORDER BY {order_by}"""
    binds = repo._rule_binds(rule, FACILITY, None)
    assert {s.value for s in DEFAULT_STATUSES} == {"missed", "overdue"}
    return sql, binds


def median_explain(conn, sql, binds) -> tuple[float, str]:
    for _ in range(2):
        explain_ms(conn, sql, binds)
    results = [explain_ms(conn, sql, binds) for _ in range(RUNS)]
    return statistics.median(r[0] for r in results), results[-1][1]


def http_ms(url: str, token: str) -> float:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    urllib.request.urlopen(req).read()  # warm-up
    times = []
    for _ in range(RUNS):
        t = time.perf_counter()
        urllib.request.urlopen(req).read()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def main() -> None:
    sql, binds = page_query()
    engine = get_engine()
    with engine.connect() as conn:
        n_patients, n_visits = conn.execute(text(
            "SELECT (SELECT count(*) FROM patient), (SELECT count(*) FROM visit)")).one()
        after, after_plan = median_explain(conn, sql, binds)
        conn.rollback()

        # "Before": only a plain foreign-key index on visit(patient_id), which most schemas have.
        # (With no visit index at all, the query rescans 400k visits per patient and does not finish.)
        trans = conn.begin()
        conn.execute(text("SET LOCAL statement_timeout = '120s'"))
        conn.execute(text("DROP INDEX ix_visit_patient_latest"))
        conn.execute(text("CREATE INDEX ix_visit_patient_fk_only ON visit (patient_id)"))
        conn.execute(text("ANALYZE visit"))
        before, before_plan = median_explain(conn, sql, binds)
        trans.rollback()  # original index restored, temporary one gone

    token = next(e.split("=")[0] for e in get_settings().auth_tokens.split(";") if "FAC-0101" in e)
    api = http_ms(f"http://localhost:8000/api/follow-up?facility_id={FACILITY}&page=1&page_size=50", token)
    api_deep = http_ms(f"http://localhost:8000/api/follow-up?facility_id={FACILITY}&page=200&page_size=50", token)

    print(f"Dataset: {n_patients:,} patients, {n_visits:,} visits; {FACILITY}, page 1 of 50, median of {RUNS}\n")
    print(f"  DB execution, with visit(patient_id) only    : {before:8.1f} ms")
    print(f"  DB execution, with ix_visit_patient_latest   : {after:8.1f} ms")
    print(f"  HTTP GET page 1 (end to end, with index)     : {api:8.1f} ms")
    print(f"  HTTP GET page 200 (end to end, with index)   : {api_deep:8.1f} ms")
    print("\n--- plan WITHOUT index (abridged) ---")
    print("\n".join(before_plan.splitlines()[:14]))
    print("\n--- plan WITH index (abridged) ---")
    print("\n".join(after_plan.splitlines()[:14]))


if __name__ == "__main__":
    main()
