"""Follow-up queries. All filtering, classification, sorting and paging happen in PostgreSQL.

The rule (README, "Assumptions"):
  * a patient's most recent visit is the latest visit_date, ties broken by the latest created_at;
  * only that visit's next_appointment_date counts; NULL means the patient is not on any list;
  * the patient attended if that visit is on or after the appointment date (visit_date >= appt);
  * days_overdue = today - appointment date; "more than n days" is strict.

Each patient's latest visit is found with a LATERAL ... LIMIT 1 that walks the index
visit(patient_id, visit_date DESC, created_at DESC) INCLUDE (next_appointment_date), so the cost is
one index probe per patient in the facility, not a scan of the visit table.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, VARCHAR
from sqlalchemy.engine import Connection

from app.followup.schemas import FollowUpStatus, SortOrder


@dataclass(frozen=True)
class RuleParams:
    today: date
    overdue_days: int
    missed_window_days: int
    due_soon_days: int

    @property
    def overdue_cutoff(self) -> int:
        # "overdue" starts after the missed window, or after the threshold if that is larger.
        return max(self.overdue_days, self.missed_window_days)


# Whitelisted ORDER BY fragments; user input never reaches the SQL text.
_ORDER_BY = {
    SortOrder.DAYS_OVERDUE_DESC: "days_overdue DESC, last_name, first_name, id",
    SortOrder.DAYS_OVERDUE_ASC: "days_overdue ASC, last_name, first_name, id",
    SortOrder.NAME_ASC: "last_name, first_name, id",
}

_CLASSIFIED_CTE = """
latest AS (
    SELECT p.id, p.patient_number, p.first_name, p.last_name, p.phone_number, p.facility_id,
           lv.visit_date AS last_visit_date,
           lv.next_appointment_date,
           (CAST(:today AS date) - lv.next_appointment_date) AS days_overdue
    FROM patient p
    CROSS JOIN LATERAL (
        SELECT v.visit_date, v.next_appointment_date
        FROM visit v
        WHERE v.patient_id = p.id
        ORDER BY v.visit_date DESC, v.created_at DESC
        LIMIT 1
    ) lv
    WHERE p.facility_id = :facility_id
      {search}
),
classified AS (
    SELECT l.*,
           CASE
               WHEN l.days_overdue > :overdue_cutoff THEN 'overdue'
               WHEN l.days_overdue > :overdue_days THEN 'missed'
               WHEN l.days_overdue BETWEEN -CAST(:due_soon_days AS int) AND 0 THEN 'due_soon'
           END AS follow_up_status
    FROM latest l
    WHERE l.next_appointment_date IS NOT NULL
      AND l.last_visit_date < l.next_appointment_date
)
"""

_SEARCH = """
      AND (p.last_name ILIKE :q ESCAPE '\\' OR p.first_name ILIKE :q ESCAPE '\\'
           OR p.patient_number LIKE :q ESCAPE '\\')"""


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _rule_binds(rule: RuleParams, facility_id: str, q: str | None) -> dict[str, object]:
    binds: dict[str, object] = {
        "today": rule.today,
        "facility_id": facility_id,
        "overdue_days": rule.overdue_days,
        "overdue_cutoff": rule.overdue_cutoff,
        "due_soon_days": rule.due_soon_days,
    }
    if q:
        binds["q"] = _escape_like(q) + "%"  # prefix match: "ban" finds Banda
    return binds


def list_follow_up(conn: Connection, *, facility_id: str, rule: RuleParams,
                   statuses: list[FollowUpStatus], sort: SortOrder, page: int, page_size: int,
                   q: str | None) -> tuple[int, list[dict[str, object]]]:
    order_by = _ORDER_BY[sort]
    sql = text(f"""
        WITH {_CLASSIFIED_CTE.format(search=_SEARCH if q else "")},
        page AS (
            SELECT c.*, count(*) OVER () AS total
            FROM classified c
            WHERE c.follow_up_status = ANY(:statuses)
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        )
        SELECT page.*, f.name AS facility_name, lc.last_contact_attempt
        FROM page
        JOIN facility f ON f.facility_id = page.facility_id
        LEFT JOIN LATERAL (
            SELECT max(ca.contacted_at) AS last_contact_attempt
            FROM contact_attempt ca
            WHERE ca.patient_id = page.id
        ) lc ON true
        ORDER BY {order_by}
    """).bindparams(bindparam("statuses", type_=ARRAY(VARCHAR)))
    binds = _rule_binds(rule, facility_id, q) | {
        "statuses": [s.value for s in statuses],
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    rows = [dict(r) for r in conn.execute(sql, binds).mappings()]
    if rows:
        total = int(rows[0]["total"])  # type: ignore[call-overload]  # bigint from count(*)
    elif page > 1:
        total = count_follow_up(conn, facility_id=facility_id, rule=rule, statuses=statuses, q=q)
    else:
        total = 0
    return total, rows


def count_follow_up(conn: Connection, *, facility_id: str, rule: RuleParams,
                    statuses: list[FollowUpStatus], q: str | None) -> int:
    sql = text(f"""
        WITH {_CLASSIFIED_CTE.format(search=_SEARCH if q else "")}
        SELECT count(*) FROM classified WHERE follow_up_status = ANY(:statuses)
    """).bindparams(bindparam("statuses", type_=ARRAY(VARCHAR)))
    binds = _rule_binds(rule, facility_id, q) | {"statuses": [s.value for s in statuses]}
    return int(conn.execute(sql, binds).scalar_one())


def summarise(conn: Connection, *, facility_id: str, rule: RuleParams) -> dict[FollowUpStatus, int]:
    sql = text(f"""
        WITH {_CLASSIFIED_CTE.format(search="")}
        SELECT follow_up_status, count(*) AS n
        FROM classified
        WHERE follow_up_status IS NOT NULL
        GROUP BY follow_up_status
    """)
    counts = {s: 0 for s in FollowUpStatus}
    for status, n in conn.execute(sql, _rule_binds(rule, facility_id, None)):
        counts[FollowUpStatus(status)] = int(n)
    return counts


# --- facilities and patients --------------------------------------------------------------------

def facility_exists(conn: Connection, facility_id: str) -> bool:
    return conn.execute(text("SELECT 1 FROM facility WHERE facility_id = :f"),
                        {"f": facility_id}).first() is not None


def list_facilities(conn: Connection, facility_id: str | None) -> list[dict[str, object]]:
    sql = "SELECT facility_id, name, district FROM facility"
    if facility_id is not None:
        sql += " WHERE facility_id = :f"
    sql += " ORDER BY district, name"
    return [dict(r) for r in conn.execute(text(sql), {"f": facility_id}).mappings()]


def patient_facility(conn: Connection, patient_id: UUID) -> str | None:
    return conn.execute(text("SELECT facility_id FROM patient WHERE id = :id"),
                        {"id": patient_id}).scalar_one_or_none()


# --- contact attempts ---------------------------------------------------------------------------

def request_hash(patient_id: UUID, contacted_at: datetime, note: str | None) -> str:
    canonical = json.dumps({
        "patient_id": str(patient_id),
        "contacted_at": contacted_at.astimezone(UTC).isoformat(),
        "note": note,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class InsertOutcome:
    created: bool
    conflicting: bool  # same idempotency key, different request


def insert_contact_attempt(conn: Connection, *, patient_id: UUID, facility_id: str,
                           contacted_at: datetime, note: str | None, recorded_by: str,
                           idempotency_key: str | None) -> InsertOutcome:
    digest = request_hash(patient_id, contacted_at, note)
    # The key is stored with the row, in the same transaction, so "written" and "remembered as
    # written" can never disagree. A concurrent duplicate blocks on the unique index until the
    # first transaction commits, then sees the conflict.
    inserted = conn.execute(text("""
        INSERT INTO contact_attempt
            (patient_id, facility_id, contacted_at, note, recorded_by, idempotency_key, request_hash)
        VALUES (:patient_id, :facility_id, :contacted_at, :note, :recorded_by, :key, :digest)
        ON CONFLICT ON CONSTRAINT uq_contact_attempt_idempotency DO NOTHING
        RETURNING id
    """), {"patient_id": patient_id, "facility_id": facility_id, "contacted_at": contacted_at,
           "note": note, "recorded_by": recorded_by, "key": idempotency_key, "digest": digest}).first()
    if inserted is not None:
        return InsertOutcome(created=True, conflicting=False)

    existing = conn.execute(text("""
        SELECT request_hash FROM contact_attempt
        WHERE facility_id = :facility_id AND idempotency_key = :key
    """), {"facility_id": facility_id, "key": idempotency_key}).scalar_one()
    return InsertOutcome(created=False, conflicting=existing != digest)
