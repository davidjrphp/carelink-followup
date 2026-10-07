"""Runtime configuration, read from environment variables (see .env.example)."""
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str

    # "Today" for the follow-up rule. Blank means the real date in TIMEZONE.
    # Fixing it makes demos and tests reproducible against the pack's sample data.
    as_of_date: date | None = None
    timezone: str = "Africa/Lusaka"

    # Status buckets (see README, "Assumptions"). Days are relative to the appointment date.
    due_soon_days: int = 7          # due_soon: appointment from today up to N days ahead
    missed_window_days: int = 14    # missed: more than overdue_days past, up to this many days

    # Static demo tokens: "token=ROLE:FACILITY:user_id;..." (FACILITY is * for district officers).
    # Assessment only. Production uses OIDC (Keycloak) access tokens; see README.
    auth_tokens: str = ""

    log_level: str = "INFO"

    @field_validator("as_of_date", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if v in ("", None) else v

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    def today(self) -> date:
        return self.as_of_date or datetime.now(ZoneInfo(self.timezone)).date()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
