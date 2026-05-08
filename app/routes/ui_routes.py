"""HTML UI routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


APP_ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=APP_ROOT / "templates")
router = APIRouter()


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})
