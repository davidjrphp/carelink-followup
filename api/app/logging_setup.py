"""Structured JSON logging with a correlation ID.

Rule: logs carry facility, role, user id, route template, status and duration. Never names, phone
numbers, patient numbers, notes or query strings (a search term can be a patient's name).
"""
import json
import logging
import re
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_VALID_INCOMING_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CORRELATION_HEADER = "X-Correlation-ID"

# Only these keys from `extra=` reach the log line. An allow-list, so a careless
# log.info(..., extra={"patient": p}) cannot leak personal data.
ALLOWED_EXTRA = {
    "event", "method", "route", "status", "duration_ms", "role", "facility_id", "user_id",
    "result_count", "total", "replayed", "error_type", "page", "page_size",
}


def get_correlation_id() -> str:
    return _correlation_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        for key in ALLOWED_EXTRA:
            if key in record.__dict__:
                out[key] = record.__dict__[key]
        if record.exc_info and record.exc_info[0] is not None:
            # Stack frames only. Exception messages from the database driver can echo row values.
            out["error_type"] = record.exc_info[0].__name__
            out["stack"] = "".join(traceback.format_tb(record.exc_info[2]))[-4000:]
        return json.dumps(out, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's access log and httpx both print full URLs, query strings included.
    logging.getLogger("uvicorn.access").disabled = True
    for chatty in ("httpx", "httpcore"):
        logging.getLogger(chatty).setLevel(logging.WARNING)


class CorrelationAndAccessLogMiddleware:
    """Pure ASGI middleware: assigns the correlation ID, writes one access log line per request
    and turns any unhandled exception into the standard 500 error body (never a bare stack trace)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = logging.getLogger("carelink.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(CORRELATION_HEADER.lower().encode(), b"").decode("latin-1")
        cid = incoming if _VALID_INCOMING_ID.match(incoming) else uuid.uuid4().hex[:12]
        token = _correlation_id.set(cid)
        state = scope.setdefault("state", {})
        state["correlation_id"] = cid

        started = time.perf_counter()
        status_holder = {"status": 500, "started": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                headers = list(message.get("headers", []))
                headers.append((CORRELATION_HEADER.encode(), cid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self.log.exception("unhandled_error", extra={"event": "unhandled_error"})
            if not status_holder["started"]:
                body = json.dumps({"error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong on the server. Quote the reference if you report it.",
                    "correlation_id": cid,
                }}).encode()
                await send_wrapper({"type": "http.response.start", "status": 500, "headers": [
                    (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send_wrapper({"type": "http.response.body", "body": body})
        finally:
            route = scope.get("route")
            principal = state.get("principal")
            self.log.info("request", extra={
                "event": "request",
                "method": scope.get("method"),
                "route": getattr(route, "path", "unmatched"),  # template, never the raw path or query
                "status": status_holder["status"],
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "role": getattr(principal, "role", None),
                "facility_id": getattr(principal, "facility_id", None),
                "user_id": getattr(principal, "user_id", None),
            })
            _correlation_id.reset(token)
