"""One error shape everywhere: {"error": {"code", "message", "correlation_id", "details"?}}."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_setup import get_correlation_id

log = logging.getLogger("carelink.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: list[dict[str, str]] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details, self.headers = details, headers


def error_body(code: str, message: str, details: list[dict[str, str]] | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message, "correlation_id": get_correlation_id()}
    if details:
        err["details"] = details
    return {"error": err}


def _field_name(loc: tuple[Any, ...]) -> str:
    # ("query", "page_size") -> "page_size"; ("body", "note") -> "note"; ("body",) -> "body"
    if not loc:
        return "request"
    parts = [str(p) for p in loc if p not in ("query", "path", "header", "body")]
    return ".".join(parts) or str(loc[0])


_FRIENDLY = {
    "missing": "is required",
    "json_invalid": "is not valid JSON",
}


def _sentence(d: dict[str, str]) -> str:
    # "facility_id is required" (the pack's example) or "page_size: Input should be ..."
    sep = " " if d["message"].startswith("is ") else ": "
    return f"{d['field']}{sep}{d['message']}"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details),
                            status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for e in exc.errors():
            field = _field_name(tuple(e.get("loc", ())))
            msg = _FRIENDLY.get(e.get("type", ""), str(e.get("msg", "is invalid")))
            # Pydantic prefixes custom errors with "Value error, "; the client does not need that.
            details.append({"field": field, "message": msg.removeprefix("Value error, ")})
        first = details[0] if details else {"field": "request", "message": "is invalid"}
        return JSONResponse(
            error_body("VALIDATION_FAILED", _sentence(first), details),
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)
