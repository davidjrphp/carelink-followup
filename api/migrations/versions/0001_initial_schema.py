"""Initial schema: facility, patient, visit, contact_attempt.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TYPE sex AS ENUM ('female', 'male', 'other');
    CREATE TYPE visit_type AS ENUM ('routine', 'follow_up', 'unscheduled');

    CREATE TABLE facility (
        facility_id  varchar(16) PRIMARY KEY CHECK (facility_id ~ '^FAC-[0-9]{4}$'),
        name         text NOT NULL,
        district     text NOT NULL
    );

    CREATE TABLE patient (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        facility_id     varchar(16) NOT NULL REFERENCES facility (facility_id),
        patient_number  varchar(32) NOT NULL,
        first_name      text NOT NULL CHECK (length(trim(first_name)) > 0),
        last_name       text NOT NULL CHECK (length(trim(last_name)) > 0),
        date_of_birth   date NOT NULL,
        sex             sex NOT NULL,
        phone_number    varchar(20),
        created_at      timestamptz NOT NULL DEFAULT now(),
        -- The pack: patient_number is unique within a facility.
        CONSTRAINT uq_patient_facility_number UNIQUE (facility_id, patient_number)
    );

    CREATE TABLE visit (
        id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id             uuid NOT NULL REFERENCES patient (id),
        visit_date             date NOT NULL,
        next_appointment_date  date,
        visit_type             visit_type NOT NULL,
        created_at             timestamptz NOT NULL DEFAULT now(),
        -- "Not before visit_date". "Visit date not in the future" is enforced by the API that
        -- records visits: a CHECK using current_date is not re-evaluated, so it would be misleading.
        CONSTRAINT ck_visit_next_appointment_not_before_visit
            CHECK (next_appointment_date IS NULL OR next_appointment_date >= visit_date)
    );

    CREATE TABLE contact_attempt (
        id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id       uuid NOT NULL REFERENCES patient (id),
        facility_id      varchar(16) NOT NULL REFERENCES facility (facility_id),
        contacted_at     timestamptz NOT NULL,
        note             varchar(500),
        recorded_by      text NOT NULL,
        idempotency_key  varchar(128),
        request_hash     char(64) NOT NULL,
        created_at       timestamptz NOT NULL DEFAULT now(),
        -- Replaying a POST with the same key is a no-op (D1). NULL keys never collide.
        CONSTRAINT uq_contact_attempt_idempotency UNIQUE (facility_id, idempotency_key)
    );

    -- Each patient's most recent visit, without touching the heap (index-only scan).
    CREATE INDEX ix_visit_patient_latest
        ON visit (patient_id, visit_date DESC, created_at DESC)
        INCLUDE (next_appointment_date);

    -- Facility filter; name ordering within a facility.
    CREATE INDEX ix_patient_facility_name ON patient (facility_id, last_name, first_name);

    -- last_contact_attempt per patient.
    CREATE INDEX ix_contact_attempt_patient ON contact_attempt (patient_id, contacted_at DESC);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE contact_attempt;
    DROP TABLE visit;
    DROP TABLE patient;
    DROP TABLE facility;
    DROP TYPE visit_type;
    DROP TYPE sex;
    """)
