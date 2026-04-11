from __future__ import annotations

from app.config import Settings
from app.domain import (
    GAD7_ITEM_IDS,
    ItemInternal,
    MessageRow,
    Preferences,
    SessionInternal,
    SessionMeta,
    SessionState,
    gad7_progress_from_states,
    utc_now,
)
from app.repository import SessionRepository, new_message_id, new_session_id
from app.services.ai_client import AIClient
from app.services.scoring import apply_extract


class Orchestrator:
    def __init__(
        self,
        repo: SessionRepository,
        ai: AIClient,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._ai = ai
        self._settings = settings

    async def create_session(
        self,
        *,
        locale: str,
        user_pseudo_id: str | None,
        preferences_tone: str,
        disclaimer_acknowledged: bool,
    ) -> SessionInternal:
        sid = new_session_id()
        mid = (
            self._settings.llm_model
            if str(self._settings.ai_backend).lower() == "http"
            else self._settings.default_model_id
        )
        meta = SessionMeta(
            session_id=sid,
            created_at=utc_now(),
            state=SessionState.collecting,
            model_id=mid,
            locale=locale,
            user_pseudo_id=user_pseudo_id,
            preferences=Preferences(
                tone=preferences_tone,
                disclaimer_acknowledged=disclaimer_acknowledged,
            ),
        )
        sess = SessionInternal(meta=meta, messages=[], item_states={})
        opening = await self._ai.initial_assistant_content(locale=locale)
        sess.messages.append(
            MessageRow(
                id=new_message_id(),
                role="assistant",
                content=opening,
                created_at=utc_now(),
                client_message_id=None,
            )
        )
        self._repo.save(sess)
        return sess

    def _find_idempotent_assistant(
        self, sess: SessionInternal, client_message_id: str | None
    ) -> str | None:
        if not client_message_id:
            return None
        for i, m in enumerate(sess.messages):
            if m.role == "user" and m.client_message_id == client_message_id:
                if i + 1 < len(sess.messages) and sess.messages[i + 1].role == "assistant":
                    return sess.messages[i + 1].content
        return None

    async def handle_user_message(
        self,
        session_id: str,
        content: str,
        client_message_id: str | None,
        skip_ai_if_duplicate: bool = True,
    ) -> tuple[SessionInternal, str, bool]:
        """Returns: (session, assistant_content, from_duplicate)"""
        sess = self._repo.get(session_id)
        if sess is None:
            raise LookupError("INVALID_SESSION")
        if sess.meta.state == SessionState.archived:
            raise PermissionError("SESSION_ARCHIVED")

        if skip_ai_if_duplicate and client_message_id:
            cached = self._find_idempotent_assistant(sess, client_message_id)
            if cached is not None:
                return sess, cached, True

        sess.messages.append(
            MessageRow(
                id=new_message_id(),
                role="user",
                content=content,
                created_at=utc_now(),
                client_message_id=client_message_id,
            )
        )

        extract = await self._ai.extract_gad7(session=sess)
        apply_extract(sess.item_states, extract, self._settings, focus_only=True)
        reply = await self._ai.chat_user_reply(session=sess, user_content=content)

        if all(sess.item_states[q].locked for q in GAD7_ITEM_IDS):
            sess.meta.state = SessionState.completed

        sess.snapshot_version += 1
        sess.messages.append(
            MessageRow(
                id=new_message_id(),
                role="assistant",
                content=reply,
                created_at=utc_now(),
                client_message_id=None,
            )
        )
        self._repo.save(sess)
        return sess, reply, False

    async def rescore(self, session_id: str) -> SessionInternal:
        """调试/复核：解锁全部项后按当前对话重新跑抽取 + 规则锁定。"""
        sess = self._repo.get(session_id)
        if sess is None:
            raise LookupError("INVALID_SESSION")
        for q in GAD7_ITEM_IDS:
            sess.item_states[q] = ItemInternal(needs_clarification=True)
        extract = await self._ai.extract_gad7(session=sess)
        apply_extract(sess.item_states, extract, self._settings, focus_only=False)
        sess.snapshot_version += 1
        if all(sess.item_states[q].locked for q in GAD7_ITEM_IDS):
            sess.meta.state = SessionState.completed
        else:
            sess.meta.state = SessionState.collecting
        self._repo.save(sess)
        return sess


def session_to_create_response(sess: SessionInternal) -> dict:
    prog = gad7_progress_from_states(sess.item_states)
    return {
        "session_id": sess.meta.session_id,
        "created_at": sess.meta.created_at.isoformat().replace("+00:00", "Z"),
        "state": sess.meta.state.value,
        "gad7_progress": {
            "answered_items": prog.answered_items,
            "pending_items": prog.pending_items,
        },
    }


def session_meta_response(sess: SessionInternal) -> dict:
    prog = gad7_progress_from_states(sess.item_states)
    return {
        "session_id": sess.meta.session_id,
        "created_at": sess.meta.created_at.isoformat().replace("+00:00", "Z"),
        "state": sess.meta.state.value,
        "model_id": sess.meta.model_id,
        "gad7_progress": {
            "answered_items": prog.answered_items,
            "pending_items": prog.pending_items,
        },
    }
