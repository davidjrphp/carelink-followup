"""Logs are JSON, carry the correlation ID, and never contain personal data."""
import json
import logging

from app.logging_setup import JsonFormatter
from tests.conftest import CLINICIAN_0101

NAME, PHONE, NOTE = "Thandiwe", "+260970000471", "lives behind the market"


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def capture() -> Capture:
    handler = Capture()
    logging.getLogger().addHandler(handler)
    return handler


def test_access_log_is_json_with_correlation_and_no_personal_data(client, db):
    pid = db.patient_with_appointment(10, first=NAME, last="Banda", phone=PHONE)
    handler = capture()
    try:
        client.get("/api/follow-up", params={"q": NAME}, headers={**CLINICIAN_0101, "X-Correlation-ID": "trace-1"})
        client.post(f"/api/follow-up/{pid}/contacted", json={"contacted_at": "2026-10-06T09:00:00Z", "note": NOTE},
                    headers={**CLINICIAN_0101, "X-Correlation-ID": "trace-2"})
    finally:
        logging.getLogger().removeHandler(handler)

    records = [json.loads(line) for line in handler.lines]
    access = [r for r in records if r.get("event") == "request"]
    assert {r["correlation_id"] for r in access} == {"trace-1", "trace-2"}
    get_line = next(r for r in access if r["correlation_id"] == "trace-1")
    assert get_line["route"] == "/api/follow-up"
    assert (get_line["status"], get_line["role"], get_line["facility_id"]) == (200, "CLINICIAN", "FAC-0101")
    assert isinstance(get_line["duration_ms"], float)
    post_line = next(r for r in access if r["correlation_id"] == "trace-2")
    assert post_line["route"] == "/api/follow-up/{patient_id}/contacted"  # template, not the id

    everything = "\n".join(handler.lines)
    for secret in (NAME, "Banda", PHONE, NOTE, str(pid), "0101-0000"):
        assert secret not in everything, f"{secret!r} leaked into logs"


def test_unknown_extra_fields_are_dropped():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    record.patient_name = NAME  # a careless extra= must not reach the log
    record.facility_id = "FAC-0101"
    out = json.loads(JsonFormatter().format(record))
    assert "patient_name" not in out and out["facility_id"] == "FAC-0101"
