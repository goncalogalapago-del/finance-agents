from fastapi import FastAPI

from app.api.agents import router as agents_router
from app.api.channels import router as channels_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(agents_router)
    app.include_router(channels_router)
    return app


app = create_app()
