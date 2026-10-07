from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FollowUpStatus(StrEnum):
    DUE_SOON = "due_soon"
    MISSED = "missed"
    OVERDUE = "overdue"


# With no status filter the endpoint returns the B1 rule: patients past the threshold.
DEFAULT_STATUSES = (FollowUpStatus.MISSED, FollowUpStatus.OVERDUE)


class SortOrder(StrEnum):
    DAYS_OVERDUE_DESC = "days_overdue_desc"
    DAYS_OVERDUE_ASC = "days_overdue_asc"
    NAME_ASC = "name_asc"


class FollowUpItem(BaseModel):
    id: UUID
    patient_number: str
    first_name: str
    last_name: str
    facility_id: str
    facility_name: str
    missed_appointment_date: date
    # Negative for due_soon: -3 means the appointment is in 3 days.
    days_overdue: int
    follow_up_status: FollowUpStatus
    phone_number: str | None
    last_contact_attempt: datetime | None
    last_visit_date: date


class FollowUpPage(BaseModel):
    page: int
    page_size: int
    total: int
    as_of: date
    overdue_days: int
    items: list[FollowUpItem]


class FollowUpSummary(BaseModel):
    facility_id: str
    as_of: date
    overdue_days: int
    counts: dict[FollowUpStatus, int]


class ContactAttemptIn(BaseModel):
    contacted_at: datetime
    note: str | None = Field(default=None, max_length=500)

    @field_validator("contacted_at")
    @classmethod
    def _must_have_offset(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("must include a time zone offset, e.g. 2026-10-06T09:14:00Z")
        return v

    @field_validator("note")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = v.strip() if v is not None else None
        return v or None


class Facility(BaseModel):
    facility_id: str
    name: str
    district: str


class Me(BaseModel):
    user_id: str
    role: str
    facility_id: str | None
    can_write: bool
