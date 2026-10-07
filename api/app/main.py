import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.errors import error_body, install_error_handlers
from app.followup.router import router as follow_up_router
from app.logging_setup import CorrelationAndAccessLogMiddleware, configure_logging

log = logging.getLogger("carelink.app")
SWAGGER_ASSETS = Path("/opt/swagger-ui")  # downloaded at image build time (see Dockerfile)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    self_hosted_docs = SWAGGER_ASSETS.is_dir()
    app = FastAPI(
        docs_url=None if self_hosted_docs else "/docs",
        title="CareLink Follow-Up API",
        version="1.0.0",
        description="Patients who missed a follow-up appointment. "
                    "Authorize with a demo bearer token from .env.example.",
    )
    app.add_middleware(CorrelationAndAccessLogMiddleware)
    install_error_handlers(app)
    app.include_router(follow_up_router)

    if self_hosted_docs:
        app.mount("/docs-assets", StaticFiles(directory=SWAGGER_ASSETS), name="docs-assets")

        @app.get("/docs", include_in_schema=False)
        def docs() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=app.openapi_url or "/openapi.json",
                title=f"{app.title} · docs",
                swagger_js_url="/docs-assets/swagger-ui-bundle.js",
                swagger_css_url="/docs-assets/swagger-ui.css",
                swagger_favicon_url="data:,",
                swagger_ui_parameters={"persistAuthorization": True},
            )

    @app.get("/api/health", include_in_schema=False)
    def health() -> JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("health_check_failed", extra={"event": "health_check_failed"})
            return JSONResponse(error_body("DATABASE_UNAVAILABLE", "Database is unreachable."),
                                status_code=503)
        return JSONResponse({"status": "ok", "as_of": settings.today().isoformat()})

    return app


app = create_app()
