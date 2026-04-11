"""GET /gad7/report 结构化报告（spec §3.5）"""

from __future__ import annotations

from app.domain import GAD7_ITEM_IDS, SessionInternal, to_public_snapshot


def _rationale_zh(qid: str, score: int | None) -> str:
    if score is None:
        return "该项尚不足以锁定分值，需补充或澄清频率信息。"
    freq = ("几乎没有", "有几天", "超过一半天数", "几乎每天")[score]
    return f"根据用户表述映射到频率档「{freq}」，对应 {qid} 分值 {score}。"


def _summary_zh(total: int | None, band: str | None) -> str:
    if total is None or band is None:
        return "评估尚未完成，请继续完成对话或等待更多信息。"
    band_zh = {
        "minimal": "最小焦虑",
        "mild": "轻度",
        "moderate": "中度",
        "severe": "重度",
    }.get(band, band)
    return f"过去两周 GAD-7 总分为 {total}，严重度参考：{band_zh}。此结果仅供筛查参考。"


def build_report(sess: SessionInternal, disclaimer: str) -> dict:
    snap = to_public_snapshot(sess.item_states)
    last_user = next((m for m in reversed(sess.messages) if m.role == "user"), None)
    items_out: list[dict] = []
    for q in GAD7_ITEM_IDS:
        st = snap.items[q]
        spans: list[dict] = []
        if last_user is not None and st.score is not None:
            spans.append(
                {
                    "message_id": last_user.id,
                    "start": 0,
                    "end": len(last_user.content),
                }
            )
        items_out.append(
            {
                "id": q,
                "prompt_ref": "official_zh_short",
                "score": st.score,
                "evidence_spans": spans,
                "rationale": _rationale_zh(q, st.score),
            }
        )
    return {
        "questionnaire": "GAD-7",
        "items": items_out,
        "total": snap.total,
        "severity_band": snap.severity_band,
        "summary_text": _summary_zh(snap.total, snap.severity_band),
        "disclaimer": disclaimer,
    }
