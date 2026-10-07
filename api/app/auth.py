"""Static bearer tokens mapped to a role and facility.

Assessment only. In production: OIDC (Keycloak) issues short-lived JWTs carrying role and facility or
district scope; this module would verify the signature and read the same three claims, and nothing
that depends on `Principal` would change.
"""
import hmac
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.errors import ApiError


class Role(StrEnum):
    CLINICIAN = "CLINICIAN"
    DISTRICT_OFFICER = "DISTRICT_OFFICER"


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    facility_id: str | None  # None = not bound to one facility (district officer)

    @property
    def can_write(self) -> bool:
        return self.role is Role.CLINICIAN


@lru_cache
def _token_table() -> tuple[tuple[str, Principal], ...]:
    table = []
    for entry in filter(None, (e.strip() for e in get_settings().auth_tokens.split(";"))):
        token, _, spec = entry.partition("=")
        role, facility, user_id = spec.split(":")
        table.append((token, Principal(user_id=user_id, role=Role(role),
                                       facility_id=None if facility == "*" else facility)))
    return tuple(table)


def _unauthenticated(message: str) -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message, headers={"WWW-Authenticate": "Bearer"})


# auto_error=False: we raise our own 401 in the standard error shape. Declaring the scheme also
# gives the OpenAPI docs an "Authorize" button.
_bearer = HTTPBearer(auto_error=False, description="Demo token from .env.example, e.g. clin-0101-demo-token")


async def current_principal(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthenticated("Sign in to continue: a bearer token is required.")
    token = credentials.credentials.strip()
    for known, principal in _token_table():
        if hmac.compare_digest(known.encode(), token.encode()):
            request.state.principal = principal  # read by the access log
            return principal
    raise _unauthenticated("Your session is not valid. Sign in again.")


def resolve_facility(principal: Principal, requested: str | None) -> str:
    """The one place that decides which facility a read is allowed to target."""
    if principal.role is Role.CLINICIAN:
        if requested is not None and requested != principal.facility_id:
            raise ApiError(403, "FORBIDDEN", "You can only view patients at your own facility.")
        assert principal.facility_id is not None
        return principal.facility_id
    if requested is None:
        raise ApiError(400, "VALIDATION_FAILED", "facility_id is required",
                       details=[{"field": "facility_id", "message": "is required"}])
    return requested
