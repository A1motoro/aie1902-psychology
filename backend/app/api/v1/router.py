from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.domain import SessionInternal, to_public_snapshot
from app.reporting import build_report
from app.services.orchestrator import (
    Orchestrator,
    session_meta_response,
    session_to_create_response,
)

router = APIRouter()


def _orch(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def _settings(request: Request):
    return request.app.state.settings


def _err(code: str, message: str, status: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


class CreateSessionBody(BaseModel):
    locale: str = "zh-CN"
    user_pseudo_id: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)


class PostMessageBody(BaseModel):
    role: str = "user"
    content: str
    client_message_id: str | None = None


def _message_public(m) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat().replace("+00:00", "Z"),
    }


def _snapshot_public(sess: SessionInternal) -> dict:
    return to_public_snapshot(sess.item_states).model_dump()


@router.post("/sessions")
async def create_session(
    request: Request,
    body: CreateSessionBody,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    _ = idempotency_key
    orch = _orch(request)
    tone = (body.preferences or {}).get("tone", "supportive")
    disc = bool((body.preferences or {}).get("disclaimer_acknowledged", False))
    sess = await orch.create_session(
        locale=body.locale,
        user_pseudo_id=body.user_pseudo_id,
        preferences_tone=str(tone),
        disclaimer_acknowledged=disc,
    )
    return session_to_create_response(sess)


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    repo = request.app.state.repo
    sess = repo.get(session_id)
    if sess is None:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    return session_meta_response(sess)


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    repo = request.app.state.repo
    ok = repo.delete_soft(session_id)
    if not ok:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    return {"ok": True}


@router.post("/sessions/{session_id}/messages")
async def post_message(request: Request, session_id: str, body: PostMessageBody):
    if body.role != "user":
        return _err("INVALID_MESSAGE", "仅支持 role=user", 400)
    orch = _orch(request)
    try:
        sess, _reply, _dup = await orch.handle_user_message(
            session_id, body.content, body.client_message_id
        )
    except LookupError:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    except PermissionError:
        return _err("SESSION_ARCHIVED", "会话已归档，无法发送消息", 400)

    assistant = sess.messages[-1]
    return {
        "messages": [_message_public(assistant)],
        "gad7_snapshot": _snapshot_public(sess),
    }


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    request: Request,
    session_id: str,
    limit: int = 50,
    offset: int = 0,
):
    repo = request.app.state.repo
    sess = repo.get(session_id)
    if sess is None:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    msgs = sess.messages[offset : offset + limit]
    return {"messages": [_message_public(m) for m in msgs], "total": len(sess.messages)}


@router.post("/sessions/{session_id}/messages:stream")
async def post_message_stream(request: Request, session_id: str, body: PostMessageBody):
    if body.role != "user":
        return _err("INVALID_MESSAGE", "仅支持 role=user", 400)

    orch = _orch(request)

    async def event_gen():
        try:
            sess, reply, _dup = await orch.handle_user_message(
                session_id, body.content, body.client_message_id
            )
        except LookupError:
            yield f"data: {json.dumps({'event': 'error', 'code': 'INVALID_SESSION'})}\n\n"
            return
        except PermissionError:
            yield f"data: {json.dumps({'event': 'error', 'code': 'SESSION_ARCHIVED'})}\n\n"
            return

        assistant = sess.messages[-1]
        step = max(1, len(reply) // 12 or 1)
        for i in range(0, len(reply), step):
            chunk = reply[i : i + step]
            yield f"data: {json.dumps({'event': 'token', 'delta': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'message_complete', 'message': _message_public(assistant)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'gad7_update', 'gad7_snapshot': _snapshot_public(sess)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/gad7/score")
async def gad7_rescore(request: Request, session_id: str):
    orch = _orch(request)
    try:
        sess = await orch.rescore(session_id)
    except LookupError:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    return {"gad7_snapshot": _snapshot_public(sess), "snapshot_version": sess.snapshot_version}


@router.get("/sessions/{session_id}/gad7/report")
async def gad7_report(request: Request, session_id: str):
    repo = request.app.state.repo
    settings = _settings(request)
    sess = repo.get(session_id)
    if sess is None:
        return _err("INVALID_SESSION", "会话不存在或已过期", 404)
    return build_report(sess, settings.disclaimer_zh)
