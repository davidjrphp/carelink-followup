"""Paging, validation, status codes, access control and the error shape."""
import pytest

from tests.conftest import CLINICIAN_0101, CLINICIAN_0207, DISTRICT


def assert_error(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert err["code"] == code
    assert err["message"]
    assert err["correlation_id"] == r.headers["X-Correlation-ID"]
    return err


def test_pagination(client, db):
    for d in range(10, 35):
        db.patient_with_appointment(d)
    r = client.get("/api/follow-up", params={"page": 2, "page_size": 10}, headers=CLINICIAN_0101)
    body = r.json()
    assert (body["page"], body["page_size"], body["total"]) == (2, 10, 25)
    assert [i["days_overdue"] for i in body["items"]] == list(range(24, 14, -1))

    r = client.get("/api/follow-up", params={"page": 3, "page_size": 10}, headers=CLINICIAN_0101)
    assert len(r.json()["items"]) == 5

    r = client.get("/api/follow-up", params={"page": 9, "page_size": 10}, headers=CLINICIAN_0101)
    assert r.json()["items"] == [] and r.json()["total"] == 25  # total still reported past the end


def test_defaults(client, db):
    body = client.get("/api/follow-up", headers=CLINICIAN_0101).json()
    assert (body["page"], body["page_size"], body["overdue_days"]) == (1, 50, 7)


@pytest.mark.parametrize("params,field", [
    ({"page_size": 0}, "page_size"),
    ({"page_size": 201}, "page_size"),
    ({"page": 0}, "page"),
    ({"page": "one"}, "page"),
    ({"overdue_days": -1}, "overdue_days"),
    ({"overdue_days": 366}, "overdue_days"),
    ({"status": "late"}, "status"),
    ({"status": "missed,late"}, "status"),
    ({"sort": "random"}, "sort"),
    ({"facility_id": "0101"}, "facility_id"),
    ({"facility_id": "FAC-0101'; DROP TABLE patient;--"}, "facility_id"),
    ({"q": "x" * 101}, "q"),
])
def test_invalid_query_is_400_with_field(client, db, params, field):
    r = client.get("/api/follow-up", params=params, headers=CLINICIAN_0101)
    err = assert_error(r, 400, "VALIDATION_FAILED")
    assert err["details"][0]["field"] == field


def test_missing_or_bad_token_is_401(client, db):
    assert_error(client.get("/api/follow-up"), 401, "UNAUTHENTICATED")
    r = client.get("/api/follow-up", headers={"Authorization": "Bearer nope"})
    assert_error(r, 401, "UNAUTHENTICATED")
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert_error(client.get("/api/follow-up", headers={"Authorization": "Basic abc"}), 401, "UNAUTHENTICATED")


def test_clinician_defaults_to_own_facility_and_cannot_read_another(client, db):
    db.patient_with_appointment(10, facility="FAC-0207")
    assert client.get("/api/follow-up", headers=CLINICIAN_0207).json()["total"] == 1
    r = client.get("/api/follow-up", params={"facility_id": "FAC-0207"}, headers=CLINICIAN_0101)
    assert_error(r, 403, "FORBIDDEN")


def test_district_officer_reads_any_facility_but_must_choose_one(client, db):
    db.patient_with_appointment(10, facility="FAC-0207")
    db.patient_with_appointment(10, facility="FAC-0101")
    err = assert_error(client.get("/api/follow-up", headers=DISTRICT), 400, "VALIDATION_FAILED")
    assert err["message"] == "facility_id is required"
    r = client.get("/api/follow-up", params={"facility_id": "FAC-0207"}, headers=DISTRICT)
    assert r.json()["total"] == 1


def test_unknown_facility_is_404(client, db):
    r = client.get("/api/follow-up", params={"facility_id": "FAC-9999"}, headers=DISTRICT)
    assert_error(r, 404, "FACILITY_NOT_FOUND")


def test_unknown_route_uses_error_shape(client, db):
    assert_error(client.get("/api/nope", headers=CLINICIAN_0101), 404, "NOT_FOUND")


def test_correlation_id_is_echoed_or_generated(client, db):
    r = client.get("/api/follow-up", headers={**CLINICIAN_0101, "X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"
    r = client.get("/api/follow-up", headers={**CLINICIAN_0101, "X-Correlation-ID": "bad id\n<script>"})
    assert r.headers["X-Correlation-ID"] != "bad id\n<script>"  # unsafe input replaced
    assert len(r.headers["X-Correlation-ID"]) == 12


def test_summary_counts(client, db):
    for d in (-3, 0, 9, 12, 20, 100):
        db.patient_with_appointment(d)
    body = client.get("/api/follow-up/summary", headers=CLINICIAN_0101).json()
    assert body["counts"] == {"due_soon": 2, "missed": 2, "overdue": 2}
    assert_error(client.get("/api/follow-up/summary", params={"facility_id": "FAC-0207"},
                            headers=CLINICIAN_0101), 403, "FORBIDDEN")


def test_facilities_scoped_by_role(client, db):
    mine = client.get("/api/facilities", headers=CLINICIAN_0101).json()
    assert [f["facility_id"] for f in mine] == ["FAC-0101"]
    assert len(client.get("/api/facilities", headers=DISTRICT).json()) == 3


def test_me(client, db):
    assert client.get("/api/me", headers=DISTRICT).json() == {
        "user_id": "district.1", "role": "DISTRICT_OFFICER", "facility_id": None, "can_write": False}


def test_unexpected_error_is_500_with_shape_and_no_stack(client, db, monkeypatch):
    from app.followup import repository

    def boom(*a, **k):
        raise RuntimeError("database said: Thandiwe Banda +260970000471")
    monkeypatch.setattr(repository, "list_follow_up", boom)
    r = client.get("/api/follow-up", headers=CLINICIAN_0101)
    err = assert_error(r, 500, "INTERNAL_ERROR")
    assert "Thandiwe" not in r.text and "Traceback" not in r.text
    assert err["correlation_id"]
