from __future__ import annotations

import json
import uuid
from datetime import datetime

from app.domain import (
    GAD7_ITEM_IDS,
    ItemInternal,
    MessageRow,
    Preferences,
    SessionInternal,
    SessionMeta,
    SessionState,
    utc_now,
)
from app.db import get_connection


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _session_to_json(sess: SessionInternal) -> str:
    data = {
        "meta": {
            "session_id": sess.meta.session_id,
            "created_at": _iso(sess.meta.created_at),
            "state": sess.meta.state.value,
            "model_id": sess.meta.model_id,
            "locale": sess.meta.locale,
            "user_pseudo_id": sess.meta.user_pseudo_id,
            "preferences": sess.meta.preferences.model_dump(),
            "closed_at": _iso(sess.meta.closed_at) if sess.meta.closed_at else None,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": _iso(m.created_at),
                "client_message_id": m.client_message_id,
            }
            for m in sess.messages
        ],
        "item_states": {k: v.model_dump() for k, v in sess.item_states.items()},
        "snapshot_version": sess.snapshot_version,
    }
    return json.dumps(data, ensure_ascii=False)


def _session_from_json(raw: str) -> SessionInternal:
    data = json.loads(raw)
    m = data["meta"]
    meta = SessionMeta(
        session_id=m["session_id"],
        created_at=_parse_iso(m["created_at"]),
        state=SessionState(m["state"]),
        model_id=m["model_id"],
        locale=m.get("locale", "zh-CN"),
        user_pseudo_id=m.get("user_pseudo_id"),
        preferences=Preferences(**m.get("preferences", {})),
        closed_at=_parse_iso(m["closed_at"]) if m.get("closed_at") else None,
    )
    messages = [
        MessageRow(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=_parse_iso(row["created_at"]),
            client_message_id=row.get("client_message_id"),
        )
        for row in data.get("messages", [])
    ]
    item_states = {k: ItemInternal(**v) for k, v in data.get("item_states", {}).items()}
    return SessionInternal(
        meta=meta,
        messages=messages,
        item_states=item_states,
        snapshot_version=int(data.get("snapshot_version", 0)),
    )


class SessionRepository:
    def get(self, session_id: str) -> SessionInternal | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return _session_from_json(row["payload"])
        finally:
            conn.close()

    def save(self, sess: SessionInternal) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO sessions(session_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (sess.meta.session_id, _session_to_json(sess), _iso(utc_now())),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_soft(self, session_id: str) -> bool:
        sess = self.get(session_id)
        if sess is None:
            return False
        sess.meta.state = SessionState.archived
        sess.meta.closed_at = utc_now()
        self.save(sess)
        return True


def new_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:24]}"


def new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


def ensure_gad7_keys(item_states: dict) -> None:
    for q in GAD7_ITEM_IDS:
        if q not in item_states:
            item_states[q] = ItemInternal()
