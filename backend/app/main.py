"""FastAPI application — Phase 3 read API over pre-computed risk data.

Offline-first: everything served here comes from PostgreSQL (guardrails-
validated JSON + deterministic Phase-F facts). No endpoint in this app calls
live inference; the chatbot (Phase 4) will be the only feature allowed to.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, dashboard, projects, references
from app.core.settings import get_settings
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Mission 3 — Local Budget Risk Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (auth.router, dashboard.router, projects.router, references.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            database = "up"
        except Exception:
            database = "down"
        return {"status": "ok" if database == "up" else "degraded", "database": database}

    return app


app = create_app()
