"""Tests run against a real PostgreSQL database (carelink_test), migrated from empty with Alembic.

The follow-up rule lives in SQL, so testing it against SQLite or mocks would test something else.
"""
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DB_URL:
    raise RuntimeError("TEST_DATABASE_URL is not set; run tests with `make test-api`")

# Must be set before the app (and its cached settings) is imported.
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["AS_OF_DATE"] = "2026-10-06"
os.environ["AUTH_TOKENS"] = (
    "t-clin-0101=CLINICIAN:FAC-0101:clin.0101;"
    "t-clin-0207=CLINICIAN:FAC-0207:clin.0207;"
    "t-district=DISTRICT_OFFICER:*:district.1"
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402

TODAY = date(2026, 10, 6)
CLINICIAN_0101 = {"Authorization": "Bearer t-clin-0101"}
CLINICIAN_0207 = {"Authorization": "Bearer t-clin-0207"}
DISTRICT = {"Authorization": "Bearer t-district"}


def _create_database_if_missing() -> None:
    info = psycopg.conninfo.conninfo_to_dict(TEST_DB_URL)
    target = info["dbname"]
    admin = psycopg.conninfo.make_conninfo(TEST_DB_URL, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    get_settings.cache_clear()
    _create_database_if_missing()
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")  # prove the migration runs from empty, every time
    command.upgrade(cfg, "head")


@pytest.fixture()
def db() -> Iterator["Db"]:
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE contact_attempt, visit, patient, facility")
        conn.execute("""INSERT INTO facility VALUES
            ('FAC-0101', 'Mwansa Urban Clinic', 'Mwansa'),
            ('FAC-0207', 'Kalemba Rural Health Centre', 'Kalemba'),
            ('FAC-0312', 'Chembe District Hospital', 'Chembe')""")
        yield Db(conn)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_engine().dispose()


class Db:
    """Small helpers to build exactly the patient history a test needs."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self._n = 0

    def patient(self, first: str = "Test", last: str = "Patient", facility: str = "FAC-0101",
                phone: str | None = None) -> UUID:
        self._n += 1
        row = self.conn.execute(
            """INSERT INTO patient (facility_id, patient_number, first_name, last_name, date_of_birth, sex, phone_number)
               VALUES (%s, %s, %s, %s, '1990-01-01', 'female', %s) RETURNING id""",
            (facility, f"{facility[4:]}-{self._n:06d}", first, last, phone)).fetchone()
        assert row is not None
        return row[0]

    def visit(self, patient_id: UUID, visit_date: date, next_appt: date | None,
              created_at: datetime | None = None, visit_type: str = "routine") -> None:
        created = created_at or datetime.combine(visit_date, time(9), tzinfo=UTC)
        self.conn.execute(
            """INSERT INTO visit (patient_id, visit_date, next_appointment_date, visit_type, created_at)
               VALUES (%s, %s, %s, %s, %s)""", (patient_id, visit_date, next_appt, visit_type, created))

    def patient_with_appointment(self, days_overdue: int, **kw: object) -> UUID:
        """A patient whose only visit booked an appointment `days_overdue` days before TODAY."""
        pid = self.patient(**kw)  # type: ignore[arg-type]
        appt = TODAY - timedelta(days=days_overdue)
        self.visit(pid, appt - timedelta(days=30), appt)
        return pid

    def count(self, table: str) -> int:
        row = self.conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()
        assert row is not None
        return int(row[0])
