"""FastAPI application entrypoint for the Procurement Data Generator MVP."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import artifact_routes, pipeline_routes, ui_routes


APP_ROOT = Path(__file__).resolve().parent


app = FastAPI(title="Procurement Data Generator", version="14.0.0")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")
app.include_router(ui_routes.router)
app.include_router(pipeline_routes.router)
app.include_router(artifact_routes.router)
