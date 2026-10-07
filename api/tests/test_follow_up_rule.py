"""The follow-up rule and its boundaries.

A wrong boundary has a clinical cost in both directions: chasing a patient who attended, or missing
one who did not. These tests pin down every boundary stated in the README's assumptions.
"""
from datetime import UTC, date, datetime, timedelta

from tests.conftest import CLINICIAN_0101, CLINICIAN_0207, TODAY

ALL = "due_soon,missed,overdue"


def ids(client, **params) -> list[str]:
    r = client.get("/api/follow-up", params={"page_size": 200, **params}, headers=CLINICIAN_0101)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()["items"]]


def item(client, pid, **params) -> dict | None:
    r = client.get("/api/follow-up", params={"page_size": 200, "status": ALL, **params}, headers=CLINICIAN_0101)
    return next((i for i in r.json()["items"] if i["id"] == str(pid)), None)


def test_pack_sample_data_matches_pack(client, db):
    """Section 15.4: on 6 Oct 2026 with n=7, Thandiwe and Mulenga are overdue; Chipo is not."""
    thandiwe = db.patient("Thandiwe", "Banda", phone="+260970000471")
    db.visit(thandiwe, date(2026, 7, 2), date(2026, 8, 2))
    db.visit(thandiwe, date(2026, 8, 5), date(2026, 9, 5), visit_type="follow_up")
    mulenga = db.patient("Mulenga", "Phiri")
    db.visit(mulenga, date(2026, 8, 20), date(2026, 9, 10))
    chipo = db.patient("Chipo", "Zulu", facility="FAC-0207")
    db.visit(chipo, date(2026, 9, 28), None, visit_type="unscheduled")

    r = client.get("/api/follow-up", params={"facility_id": "FAC-0101", "status": "overdue",
                                             "sort": "days_overdue_desc"}, headers=CLINICIAN_0101)
    body = r.json()
    assert body["total"] == 2
    assert [(i["first_name"], i["days_overdue"], i["follow_up_status"], i["missed_appointment_date"])
            for i in body["items"]] == [
        ("Thandiwe", 31, "overdue", "2026-09-05"),
        ("Mulenga", 26, "overdue", "2026-09-10"),
    ]
    assert body["items"][0]["facility_name"] == "Mwansa Urban Clinic"

    r = client.get("/api/follow-up", params={"status": ALL}, headers=CLINICIAN_0207)
    assert r.json()["total"] == 0  # Chipo: most recent visit set no next appointment


def test_threshold_is_strict_seven_days_out_eight_days_in(client, db):
    seven = db.patient_with_appointment(7)
    eight = db.patient_with_appointment(8)
    assert ids(client) == [str(eight)]
    assert str(seven) not in ids(client, status=ALL)  # grace period: on no list at all


def test_custom_threshold_moves_the_boundary(client, db):
    one = db.patient_with_appointment(1)
    three = db.patient_with_appointment(3)
    assert set(ids(client, overdue_days=0)) == {str(one), str(three)}
    assert ids(client, overdue_days=2) == [str(three)]
    assert ids(client, overdue_days=3) == []


def test_only_the_most_recent_visit_counts(client, db):
    """An earlier visit set an appointment, but the latest visit set none: not on the list."""
    pid = db.patient()
    db.visit(pid, date(2026, 6, 1), date(2026, 7, 1))
    db.visit(pid, date(2026, 7, 1), None, visit_type="unscheduled")
    assert ids(client, status=ALL) == []


def test_visit_on_the_appointment_date_counts_as_attending(client, db):
    pid = db.patient()
    db.visit(pid, date(2026, 8, 1), date(2026, 9, 1))
    db.visit(pid, date(2026, 9, 1), date(2026, 9, 1))  # came on the day; nothing new booked
    assert ids(client, status=ALL) == []


def test_later_visit_with_new_appointment_replaces_the_old_one(client, db):
    pid = db.patient()
    db.visit(pid, date(2026, 6, 1), date(2026, 7, 1))     # missed this one...
    db.visit(pid, date(2026, 7, 20), date(2026, 10, 30))  # ...but came back; next is in the future
    assert ids(client, status=ALL) == []


def test_same_day_visits_tie_broken_by_created_at(client, db):
    day = date(2026, 9, 1)
    at = datetime(2026, 9, 1, 9, tzinfo=UTC)
    booked_last = db.patient("Booked", "Last")
    db.visit(booked_last, day, None, created_at=at)
    db.visit(booked_last, day, date(2026, 9, 15), created_at=at + timedelta(hours=1))
    booked_first = db.patient("Booked", "First")
    db.visit(booked_first, day, date(2026, 9, 15), created_at=at)
    db.visit(booked_first, day, None, created_at=at + timedelta(hours=1))
    assert ids(client) == [str(booked_last)]


def test_status_buckets_and_their_edges(client, db):
    cases = {
        -8: None, -7: "due_soon", 0: "due_soon",   # appointment up to 7 days ahead, or today
        1: None, 7: None,                           # grace period
        8: "missed", 14: "missed",                  # recently missed
        15: "overdue", 400: "overdue",
    }
    pids = {d: db.patient_with_appointment(d) for d in cases}
    for days, expected in cases.items():
        found = item(client, pids[days])
        assert (found and found["follow_up_status"]) == expected, f"{days} days past"
        if found:
            assert found["days_overdue"] == days


def test_default_returns_missed_and_overdue_not_due_soon(client, db):
    due = db.patient_with_appointment(-2)
    missed = db.patient_with_appointment(10)
    overdue = db.patient_with_appointment(40)
    assert set(ids(client)) == {str(missed), str(overdue)}
    assert ids(client, status="due_soon") == [str(due)]
    assert ids(client, status="missed") == [str(missed)]


def test_threshold_above_missed_window_leaves_only_overdue(client, db):
    db.patient_with_appointment(16)
    r = client.get("/api/follow-up", params={"overdue_days": 15}, headers=CLINICIAN_0101)
    assert [i["follow_up_status"] for i in r.json()["items"]] == ["overdue"]


def test_patients_without_visits_are_not_listed(client, db):
    db.patient()
    assert ids(client, status=ALL) == []


def test_other_facilities_patients_never_appear(client, db):
    db.patient_with_appointment(20, facility="FAC-0207")
    mine = db.patient_with_appointment(20)
    assert ids(client) == [str(mine)]


def test_sorting_by_days_overdue(client, db):
    a = db.patient_with_appointment(10, last="Alpha")
    b = db.patient_with_appointment(50, last="Bravo")
    c = db.patient_with_appointment(20, last="Charlie")
    assert ids(client) == [str(b), str(c), str(a)]
    assert ids(client, sort="days_overdue_asc") == [str(a), str(c), str(b)]
    assert ids(client, sort="name_asc") == [str(a), str(b), str(c)]


def test_search_by_name_or_number_prefix(client, db):
    banda = db.patient_with_appointment(10, first="Thandiwe", last="Banda")
    db.patient_with_appointment(10, first="Mulenga", last="Phiri")
    assert ids(client, q="ban") == [str(banda)]
    assert ids(client, q="THAN") == [str(banda)]
    assert ids(client, q="0101-000001") == [str(banda)]
    assert ids(client, q="%") == []  # wildcards are literal


def test_last_contact_attempt_is_the_latest(client, db):
    pid = db.patient_with_appointment(10)
    for ts in ("2026-09-20T10:00:00Z", "2026-09-29T09:14:00Z", "2026-09-25T10:00:00Z"):
        r = client.post(f"/api/follow-up/{pid}/contacted", json={"contacted_at": ts}, headers=CLINICIAN_0101)
        assert r.status_code == 204
    assert item(client, pid)["last_contact_attempt"] == "2026-09-29T09:14:00Z"


def test_as_of_date_is_reported(client, db):
    r = client.get("/api/follow-up", headers=CLINICIAN_0101)
    assert r.json()["as_of"] == TODAY.isoformat()
