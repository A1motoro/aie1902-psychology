from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.db import get_connection, init_db
from app.repository import SessionRepository
from app.services.ai_client import build_ai_client
from app.services.orchestrator import Orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    repo = SessionRepository()
    ai = build_ai_client(settings)
    app.state.settings = settings
    app.state.repo = repo
    app.state.ai_client = ai
    app.state.orchestrator = Orchestrator(repo=repo, ai=ai, settings=settings)
    try:
        yield
    finally:
        aclose = getattr(ai, "aclose", None)
        if callable(aclose):
            await aclose()


app = FastAPI(
    title="GAD-7 AI辅助评估 API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(v1_router, prefix="/v1")


def _err(code: str, message: str, status: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


class RolloutBody(BaseModel):
    percent: int = Field(default=100, ge=0, le=100)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except OSError:
        return _err("NOT_READY", "存储不可用", 503)
    s = get_settings()
    return {
        "ready": True,
        "ai_backend": s.ai_backend,
        "model_gateway": "http" if s.ai_backend.lower() == "http" else "stub",
    }


@app.get("/admin/models")
async def admin_models(request: Request):
    s = request.app.state.settings
    if str(s.ai_backend).lower() == "http":
        mid = s.llm_model
        endpoint = s.llm_base_url.rstrip("/") + "/chat/completions"
    else:
        mid = s.default_model_id
        endpoint = "stub://inference"
    return {
        "models": [
            {
                "model_id": mid,
                "endpoint": endpoint,
                "capabilities": ["chat_reply", "gad7_extract"],
            }
        ]
    }


@app.post("/admin/models/{model_id}/rollout")
async def admin_rollout(request: Request, model_id: str, body: RolloutBody):
    s = request.app.state.settings
    allowed = {s.default_model_id}
    if str(s.ai_backend).lower() == "http":
        allowed.add(s.llm_model)
    if model_id not in allowed:
        return _err("INVALID_MODEL", "未知 model_id", 404)
    _ = body.percent
    return {"accepted": True, "model_id": model_id, "note": "占位：接入真实灰度后写入配置中心"}


def get_app() -> FastAPI:
    return app


_STATIC_ROOT = Path(__file__).resolve().parent.parent.parent / "static"
if _STATIC_ROOT.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_ROOT), html=True), name="static")
