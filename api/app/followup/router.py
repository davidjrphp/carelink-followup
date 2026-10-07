import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.engine import Connection

from app.auth import Principal, current_principal, resolve_facility
from app.config import Settings, get_settings
from app.db import get_conn
from app.errors import ApiError
from app.followup import repository as repo
from app.followup.schemas import (
    DEFAULT_STATUSES, ContactAttemptIn, Facility, FollowUpItem, FollowUpPage, FollowUpStatus,
    FollowUpSummary, Me, SortOrder,
)

log = logging.getLogger("carelink.followup")
router = APIRouter(prefix="/api")

FACILITY_ID = r"^FAC-\d{4}$"
MAX_PAGE_SIZE = 200
CLOCK_SKEW = timedelta(minutes=5)
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")

PrincipalDep = Annotated[Principal, Depends(current_principal)]
ConnDep = Annotated[Connection, Depends(get_conn)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
FacilityQuery = Annotated[str | None, Query(pattern=FACILITY_ID, description="e.g. FAC-0101")]
OverdueDaysQuery = Annotated[int, Query(ge=0, le=365, description="Threshold n: more than n days past")]


def _parse_statuses(raw: str | None) -> list[FollowUpStatus]:
    if raw is None or raw.strip() == "":
        return list(DEFAULT_STATUSES)
    out: list[FollowUpStatus] = []
    for part in raw.split(","):
        try:
            status = FollowUpStatus(part.strip())
        except ValueError:
            allowed = ", ".join(s.value for s in FollowUpStatus)
            raise ApiError(400, "VALIDATION_FAILED", f"status must be one of: {allowed}",
                           details=[{"field": "status", "message": f"must be one of: {allowed}"}]) from None
        if status not in out:
            out.append(status)
    return out


def _require_facility(conn: Connection, facility_id: str) -> None:
    if not repo.facility_exists(conn, facility_id):
        raise ApiError(404, "FACILITY_NOT_FOUND", f"Facility {facility_id} does not exist.")


def _rule(settings: Settings, overdue_days: int) -> repo.RuleParams:
    return repo.RuleParams(today=settings.today(), overdue_days=overdue_days,
                           missed_window_days=settings.missed_window_days,
                           due_soon_days=settings.due_soon_days)


@router.get("/follow-up", response_model=FollowUpPage, summary="Paged follow-up list")
def get_follow_up(
    principal: PrincipalDep, conn: ConnDep, settings: SettingsDep,
    facility_id: FacilityQuery = None,
    status: Annotated[str | None, Query(description="Comma-separated: due_soon, missed, overdue. "
                                                     "Default: missed,overdue")] = None,
    overdue_days: OverdueDaysQuery = 7,
    sort: SortOrder = SortOrder.DAYS_OVERDUE_DESC,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    q: Annotated[str | None, Query(max_length=100, description="Name or patient number prefix")] = None,
) -> FollowUpPage:
    facility = resolve_facility(principal, facility_id)
    statuses = _parse_statuses(status)
    _require_facility(conn, facility)
    rule = _rule(settings, overdue_days)

    total, rows = repo.list_follow_up(conn, facility_id=facility, rule=rule, statuses=statuses,
                                      sort=sort, page=page, page_size=page_size,
                                      q=(q or "").strip() or None)
    log.info("follow_up_listed", extra={"event": "follow_up_listed", "facility_id": facility,
                                        "result_count": len(rows), "total": total,
                                        "page": page, "page_size": page_size})
    return FollowUpPage(
        page=page, page_size=page_size, total=total, as_of=rule.today, overdue_days=overdue_days,
        items=[FollowUpItem(missed_appointment_date=r["next_appointment_date"], **r) for r in rows],
    )


@router.get("/follow-up/summary", response_model=FollowUpSummary, summary="Counts per status")
def get_summary(principal: PrincipalDep, conn: ConnDep, settings: SettingsDep,
                facility_id: FacilityQuery = None,
                overdue_days: OverdueDaysQuery = 7) -> FollowUpSummary:
    facility = resolve_facility(principal, facility_id)
    _require_facility(conn, facility)
    rule = _rule(settings, overdue_days)
    return FollowUpSummary(facility_id=facility, as_of=rule.today, overdue_days=overdue_days,
                           counts=repo.summarise(conn, facility_id=facility, rule=rule))


@router.post("/follow-up/{patient_id}/contacted", status_code=204, response_class=Response,
             summary="Record a contact attempt",
             responses={409: {"description": "Idempotency-Key reused with a different request"}})
def record_contact(
    patient_id: UUID, body: ContactAttemptIn, principal: PrincipalDep, conn: ConnDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    if not principal.can_write:
        raise ApiError(403, "FORBIDDEN", "District officers have read-only access.")
    if idempotency_key is not None and not _IDEMPOTENCY_KEY.match(idempotency_key):
        raise ApiError(400, "VALIDATION_FAILED", "Idempotency-Key must be 8-128 letters, digits, - or _",
                       details=[{"field": "Idempotency-Key", "message": "is invalid"}])
    if body.contacted_at > datetime.now(UTC) + CLOCK_SKEW:
        raise ApiError(400, "VALIDATION_FAILED", "contacted_at cannot be in the future",
                       details=[{"field": "contacted_at", "message": "cannot be in the future"}])

    # 404 rather than 403 for another facility's patient: do not confirm that the record exists.
    if repo.patient_facility(conn, patient_id) != principal.facility_id:
        raise ApiError(404, "PATIENT_NOT_FOUND", "No patient with that id at your facility.")

    assert principal.facility_id is not None
    outcome = repo.insert_contact_attempt(
        conn, patient_id=patient_id, facility_id=principal.facility_id,
        contacted_at=body.contacted_at, note=body.note, recorded_by=principal.user_id,
        idempotency_key=idempotency_key)
    if outcome.conflicting:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED",
                       "This Idempotency-Key was already used for a different request.")

    log.info("contact_attempt_recorded", extra={"event": "contact_attempt_recorded",
                                                "facility_id": principal.facility_id,
                                                "replayed": not outcome.created})
    headers = {} if outcome.created else {"Idempotent-Replayed": "true"}
    return Response(status_code=204, headers=headers)


@router.get("/facilities", response_model=list[Facility], summary="Facilities visible to the caller")
def get_facilities(principal: PrincipalDep, conn: ConnDep) -> list[Facility]:
    return [Facility(**r) for r in repo.list_facilities(conn, principal.facility_id)]  # type: ignore[arg-type]


@router.get("/me", response_model=Me, summary="The signed-in user")
def get_me(principal: PrincipalDep) -> Me:
    return Me(user_id=principal.user_id, role=principal.role.value,
              facility_id=principal.facility_id, can_write=principal.can_write)
