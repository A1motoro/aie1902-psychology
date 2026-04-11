"""GAD-7 规则校验与锁定（spec §4）"""

from __future__ import annotations

from app.config import Settings
from app.domain import GAD7_ITEM_IDS, ItemInternal
from app.services.ai_client import GAD7ExtractItem, GAD7ExtractResult


def _valid_score(v: int | None) -> bool:
    return v is None or (0 <= v <= 3)


def _first_unlocked_q(item_states: dict[str, ItemInternal]) -> str | None:
    for q in GAD7_ITEM_IDS:
        if not item_states[q].locked:
            return q
    return None


def apply_extract(
    item_states: dict[str, ItemInternal],
    extract: GAD7ExtractResult,
    settings: Settings,
    *,
    focus_only: bool = False,
) -> None:
    """
    focus_only=True（默认对话轮次）：只根据抽取结果更新「当前未完成的第一题」，
    防止模型用笼统表述一次性填满 Q1～Q7。
    focus_only=False（如 rescore）：对全部未锁定项照常应用抽取结果。
    """
    tau_h, tau_l = settings.tau_high, settings.tau_low
    focus_q = _first_unlocked_q(item_states) if focus_only else None
    for q in GAD7_ITEM_IDS:
        cur = item_states[q]
        if cur.locked:
            continue
        if focus_only and focus_q is not None and q != focus_q:
            continue
        cand: GAD7ExtractItem | None = extract.items.get(q)
        if cand is None:
            continue
        score, conf = cand.score, cand.confidence
        if not _valid_score(score):
            continue
        if conf >= tau_h and score is not None:
            cur.score = score
            cur.confidence = conf
            cur.needs_clarification = False
            cur.locked = True
        elif conf >= tau_l:
            if score is not None:
                cur.score = score
            cur.confidence = conf
            cur.needs_clarification = True
        else:
            cur.confidence = conf
            cur.needs_clarification = True
            if score is not None and conf < tau_l:
                cur.score = None
