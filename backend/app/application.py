"""FastAPI application factory.

Wiring order matters:
    1. create the app + CORS
    2. on startup: create the schema, print the integration banner, start the cron
    3. on shutdown: stop the scheduler cleanly
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS
from .database import init_db
from .diagnostics import startup_report
from .routes import router
from .scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    startup_report()
    start_scheduler()
    yield
    shutdown_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Executive Assistant API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        # Wildcard origins cannot be combined with credentials; the UI sends none.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app
