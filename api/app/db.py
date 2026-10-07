from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().sqlalchemy_url,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,  # survive a database restart without a burst of 500s
        pool_timeout=5,
    )


def get_conn() -> Iterator[Connection]:
    """One transaction per request: committed on success, rolled back on any error."""
    with get_engine().begin() as conn:
        yield conn
