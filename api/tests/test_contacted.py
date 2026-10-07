"""POST /api/follow-up/{id}/contacted, including safe replay with Idempotency-Key (Section D1)."""
import uuid

from tests.conftest import CLINICIAN_0101, CLINICIAN_0207, DISTRICT
from tests.test_api_contract import assert_error

BODY = {"contacted_at": "2026-10-06T09:14:00+02:00", "note": "Phoned; will come Thursday"}


def post(client, pid, body=BODY, headers=CLINICIAN_0101, key=None):
    h = {**headers, **({"Idempotency-Key": key} if key else {})}
    return client.post(f"/api/follow-up/{pid}/contacted", json=body, headers=h)


def test_records_attempt_and_returns_204(client, db):
    pid = db.patient_with_appointment(10)
    r = post(client, pid)
    assert r.status_code == 204 and r.content == b""
    row = db.conn.execute("SELECT contacted_at, note, recorded_by, facility_id FROM contact_attempt").fetchone()
    assert row[0].isoformat() == "2026-10-06T07:14:00+00:00"
    assert row[1:] == ("Phoned; will come Thursday", "clin.0101", "FAC-0101")


def test_note_is_optional_and_trimmed(client, db):
    pid = db.patient_with_appointment(10)
    assert post(client, pid, {"contacted_at": "2026-10-06T09:00:00Z", "note": "   "}).status_code == 204
    assert db.conn.execute("SELECT note FROM contact_attempt").fetchone()[0] is None


def test_replay_with_same_key_writes_once(client, db):
    pid = db.patient_with_appointment(10)
    key = str(uuid.uuid4())
    first = post(client, pid, key=key)
    second = post(client, pid, key=key)
    assert first.status_code == second.status_code == 204
    assert second.headers["Idempotent-Replayed"] == "true"
    assert db.count("contact_attempt") == 1


def test_same_key_different_request_is_409(client, db):
    pid = db.patient_with_appointment(10)
    key = str(uuid.uuid4())
    assert post(client, pid, key=key).status_code == 204
    r = post(client, pid, {**BODY, "note": "something else"}, key=key)
    assert_error(r, 409, "IDEMPOTENCY_KEY_REUSED")
    assert db.count("contact_attempt") == 1


def test_without_key_each_post_is_a_new_attempt(client, db):
    pid = db.patient_with_appointment(10)
    post(client, pid)
    post(client, pid)
    assert db.count("contact_attempt") == 2


def test_district_officer_cannot_write(client, db):
    pid = db.patient_with_appointment(10)
    assert_error(post(client, pid, headers=DISTRICT), 403, "FORBIDDEN")
    assert db.count("contact_attempt") == 0


def test_other_facility_patient_is_404_not_403(client, db):
    pid = db.patient_with_appointment(10, facility="FAC-0101")
    assert_error(post(client, pid, headers=CLINICIAN_0207), 404, "PATIENT_NOT_FOUND")
    assert_error(post(client, uuid.uuid4()), 404, "PATIENT_NOT_FOUND")


def test_validation(client, db):
    pid = db.patient_with_appointment(10)
    cases = [
        ({}, "contacted_at"),
        ({"contacted_at": "yesterday"}, "contacted_at"),
        ({"contacted_at": "2026-10-06T09:00:00"}, "contacted_at"),     # no offset: ambiguous
        ({"contacted_at": "2099-01-01T00:00:00Z"}, "contacted_at"),    # future
        ({"contacted_at": "2026-10-06T09:00:00Z", "note": "x" * 501}, "note"),
    ]
    for body, field in cases:
        err = assert_error(post(client, pid, body), 400, "VALIDATION_FAILED")
        assert err["details"][0]["field"] == field, body
    err = assert_error(post(client, pid, key="short"), 400, "VALIDATION_FAILED")
    assert err["details"][0]["field"] == "Idempotency-Key"
    r = client.post(f"/api/follow-up/{pid}/contacted", content=b"{not json",
                    headers={**CLINICIAN_0101, "Content-Type": "application/json"})
    assert_error(r, 400, "VALIDATION_FAILED")
    assert_error(post(client, "not-a-uuid"), 400, "VALIDATION_FAILED")
    assert db.count("contact_attempt") == 0


def test_requires_auth(client, db):
    pid = db.patient_with_appointment(10)
    assert_error(post(client, pid, headers={}), 401, "UNAUTHENTICATED")
