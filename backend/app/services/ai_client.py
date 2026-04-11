"""
自研模型推理接口占位 + OpenAI 兼容 HTTP 客户端（测试用）。

实现 `AIClient` 的其它网关：保持三方法签名一致，在 main.py lifespan 注入即可。
"""

from __future__ import annotations

import json
import re
from typing import Optional, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field

from app.config import Settings
from app.domain import GAD7_ITEM_IDS, SessionInternal


SYSTEM_INTERVIEWER_ZH = """你是 GAD-7 焦虑筛查对话助手（简体中文）。评估窗口为「过去两周」内症状出现的频繁程度，不做诊断与治疗建议。
用户可以用自然语言自由描述，不必套用固定话术。必须按 Q1→Q7 顺序一次只推进一题：未完成当前题前不要主动跳到下一题或一次性追问多题。语气自然、共情、简短。回复中不要输出 JSON、不要列出分值。
由你在内心对照量表四档（0 几乎没有发生；1 有几天；2 超过一半天数；3 几乎每天）判断用户表述是否已足够具体：若仍模糊，用非诱导方式追问「频率/多久一次」，避免重复同一段模板。"""

SYSTEM_EXTRACT_ZH = """你是 GAD-7 辅助抽取模块。只根据对话内容，为 Q1～Q7 输出 JSON（不要其它文字）。
访谈按 Q1→Q7 顺序逐题收集。用户消息中会标明「当前仅评估」的题号：只有该题允许根据对话给出非 null 的 score；其它题若尚未单独讨论到对应维度，必须 score=null、needs_clarification=true，禁止用「每天都焦虑」「很难受」等笼统表述去推断未讨论过的题目。
Q1 紧张焦虑急切；Q2 无法停止担忧；Q3 对很多事过度担忧；Q4 难以放松；Q5 坐立不安；Q6 易怒；Q7 害怕坏事发生。
评分锚点（过去两周）：0=几乎没有；1=有几天；2=超过一半天数；3=几乎每天。请根据自然语言判断是否已能合理映射到其中一档。
每项输出：score 为 0–3 的整数或 null；confidence 为 0–1；needs_clarification 为布尔。
若当前题表述已足以映射到某一档，给出 score 与较高 confidence（通常≥0.85），needs_clarification=false；否则 score=null。
严格 JSON 形状：{"items":{"Q1":{"score":null,"confidence":0.0,"needs_clarification":true},...,"Q7":{...}}}"""


class GAD7ExtractItem(BaseModel):
    score: Optional[int] = None
    confidence: float = 0.0
    needs_clarification: bool = True


class GAD7ExtractResult(BaseModel):
    """模式 A：结构化抽取侧车（NLU），经规则校验后写入快照。"""

    items: dict[str, GAD7ExtractItem] = Field(default_factory=dict)


@runtime_checkable
class AIClient(Protocol):
    """对外部推理服务的抽象。生产环境请替换为真实客户端。"""

    async def initial_assistant_content(self, *, locale: str) -> str:
        """创建会话后的首条 assistant 话术。"""

    async def chat_user_reply(
        self,
        *,
        session: SessionInternal,
        user_content: str,
    ) -> str:
        """根据当前会话生成面向用户的下一条回复（自然语言，不含打分 JSON）。"""

    async def extract_gad7(self, *, session: SessionInternal) -> GAD7ExtractResult:
        """基于当前完整对话历史输出分项候选分与置信度（由打分引擎再做阈值与锁定）。"""


def _focus_item(session: SessionInternal) -> Optional[str]:
    for q in GAD7_ITEM_IDS:
        st = session.item_states[q]
        if not st.locked:
            return q
    return None


def _heuristic_score(text: str) -> tuple[Optional[int], float]:
    """极简中文关键词演示逻辑，便于无模型时联调；上线后删除或移出。"""
    t = text.strip()
    if not t:
        return None, 0.0
    if re.search(r"几乎每天|每天都|天天", t):
        return 3, 0.88
    if re.search(r"一半以上|大半|超过一半|多数日子", t):
        return 2, 0.86
    if re.search(r"有几天|好几天|偶尔|有时", t):
        return 1, 0.82
    if re.search(r"几乎没有|基本没有|完全没有|从没有|一点也没有|不会|没什么", t):
        return 0, 0.87
    if re.search(r"总是|老是|一直|每次|经常|频繁", t):
        return 3, 0.84
    if re.search(r"很少|难得|几乎不|不怎么|不太", t):
        return 0, 0.83
    if re.search(r"有时候|间断|一阵一阵", t):
        return 1, 0.80
    if len(t) < 4:
        return None, 0.35
    return None, 0.45


class StubAIClient:
    """
    占位实现：返回固定话术 + 关键词启发式抽取。
    替换为真实模型时保持方法签名不变即可。
    """

    async def initial_assistant_content(self, *, locale: str) -> str:
        _ = locale
        return (
            "您好，我是 GAD-7 焦虑筛查对话助手。接下来会围绕「过去两周」的感受问您几个与频率相关的问题，"
            "结果仅作自助参考，不能替代专业诊断。\n\n"
            "我们先从第一项开始：在最近两周里，您是否经常感到紧张、焦虑或急切？"
            "请按您的真实感受用自然语言描述即可。"
        )

    async def chat_user_reply(
        self,
        *,
        session: SessionInternal,
        user_content: str,
    ) -> str:
        _ = user_content
        focus = _focus_item(session)
        if focus is None:
            snap = session.item_states
            if all(snap[q].locked for q in GAD7_ITEM_IDS):
                return (
                    "感谢您的回答，七项信息已齐。您可以在报告页查看汇总与说明；"
                    "若症状困扰明显，建议向专业医疗或心理机构进一步咨询。"
                )
            return "我这边收到了。我们再确认一下上一项的频率好吗？"
        # 与 spec 附录 Q1–Q7 含义对齐（口语转述）
        question_line = {
            "Q1": "您是否经常感到紧张、焦虑或急切？",
            "Q2": "您是否感到无法停止或控制担忧？",
            "Q3": "您是否对很多事情都过度担忧？",
            "Q4": "您是否很难放松下来？",
            "Q5": "您是否因内心不安而难以静坐或感到坐立不安？",
            "Q6": "您是否变得容易烦躁或易被激怒？",
            "Q7": "您是否常感到好像将有可怕的事情发生而感到害怕？",
        }
        st = session.item_states[focus]
        if st.needs_clarification and not st.locked:
            return (
                "我听到了。如果方便，可以再具体一点：这种感觉在最近两周里大概是偶尔才有、"
                "还是比较常见？用您习惯的表达方式就行。"
            )
        qtext = question_line.get(focus, "")
        return (
            f"谢谢。下一项：在最近两周里，{qtext}请仍用自然语言描述您的感受。"
        )

    async def extract_gad7(self, *, session: SessionInternal) -> GAD7ExtractResult:
        last_user = next((m.content for m in reversed(session.messages) if m.role == "user"), "")
        focus = _focus_item(session)
        items: dict[str, GAD7ExtractItem] = {}
        for q in GAD7_ITEM_IDS:
            if q == focus:
                continue
            items[q] = GAD7ExtractItem(needs_clarification=False)
        if focus and last_user:
            score, conf = _heuristic_score(last_user)
            needs = conf < 0.85 or score is None
            items[focus] = GAD7ExtractItem(
                score=score,
                confidence=conf,
                needs_clarification=needs,
            )
        elif focus:
            items[focus] = GAD7ExtractItem(needs_clarification=True)
        return GAD7ExtractResult(items=items)


def _state_hint(session: SessionInternal) -> str:
    lines: list[str] = []
    for q in GAD7_ITEM_IDS:
        st = session.item_states[q]
        if st.locked and st.score is not None:
            lines.append(f"{q} 已锁定 score={st.score}")
        elif st.needs_clarification and not st.locked:
            lines.append(f"{q} 待澄清")
    return "\n".join(lines) if lines else "尚无量表项锁定。"


def _session_to_chat_messages(session: SessionInternal, locale: str) -> list[dict[str, str]]:
    loc = "简体中文" if locale.lower().startswith("zh") else locale
    msgs: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_INTERVIEWER_ZH},
        {
            "role": "system",
            "content": f"使用 {loc} 回复用户。\n内部状态（勿向用户复述）：\n{_state_hint(session)}",
        },
    ]
    for m in session.messages:
        r = "assistant" if m.role == "assistant" else "user"
        msgs.append({"role": r, "content": m.content})
    return msgs


def _parse_json_object(raw: str) -> dict:
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


def _extract_user_payload(session: SessionInternal) -> str:
    focus = _focus_item(session)
    lines = [
        "对话记录（按时间顺序）：",
        *[f"{m.role}: {m.content}" for m in session.messages],
        "",
        "已锁定项（抽取时保持与之一致，若对话未推翻可继续视为有效）：",
    ]
    for q in GAD7_ITEM_IDS:
        st = session.item_states[q]
        if st.locked and st.score is not None:
            lines.append(f"{q} score={st.score}")
    lines.append("")
    if focus:
        lines.append(
            f"【当前仅评估 {focus}】本条用户发言优先映射到该题维度；"
            "除已锁定项外，其它未单独讨论到的题号在 JSON 中必须 score=null、needs_clarification=true，"
            "不得因泛化情绪或「每天都很糟」等推断 Q2～Q7。"
        )
    lines.append("请输出 JSON。")
    return "\n".join(lines)


class HttpOpenAICompatibleClient:
    """
    调用 OpenAI 兼容接口：POST {base}/chat/completions。
    适用于 OpenAI、DeepSeek（https://api.deepseek.com/v1）、One-API 等。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.llm_model
        self._base = settings.llm_base_url.rstrip("/")
        timeout = httpx.Timeout(settings.llm_timeout_seconds)
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    async def _chat_completions(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        json_mode: bool,
    ) -> str:
        url = f"{self._base}/chat/completions"
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode and self._settings.llm_json_response_format:
            payload["response_format"] = {"type": "json_object"}
        resp = await self._client.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"LLM 响应结构异常: {data!r}") from e

    async def initial_assistant_content(self, *, locale: str) -> str:
        loc = "简体中文" if locale.lower().startswith("zh") else locale
        messages = [
            {"role": "system", "content": SYSTEM_INTERVIEWER_ZH},
            {
                "role": "user",
                "content": (
                    f"请用 {loc} 写出本会话第一条 assistant 消息："
                    "简短说明筛查目的与免责声明要点，然后开始引导用户回答 GAD-7 第一项（过去两周紧张/焦虑/急切相关感受）。"
                    "邀请用户用自然语言自由描述即可，不要要求用户必须从四档固定用语里选词。只输出给用户看的正文。"
                ),
            },
        ]
        return (await self._chat_completions(messages, temperature=self._settings.llm_temperature_chat, json_mode=False)).strip()

    async def chat_user_reply(
        self,
        *,
        session: SessionInternal,
        user_content: str,
    ) -> str:
        _ = user_content
        messages = _session_to_chat_messages(session, session.meta.locale)
        return (
            await self._chat_completions(
                messages,
                temperature=self._settings.llm_temperature_chat,
                json_mode=False,
            )
        ).strip()

    async def extract_gad7(self, *, session: SessionInternal) -> GAD7ExtractResult:
        messages = [
            {"role": "system", "content": SYSTEM_EXTRACT_ZH},
            {"role": "user", "content": _extract_user_payload(session)},
        ]
        raw = await self._chat_completions(
            messages,
            temperature=self._settings.llm_temperature_extract,
            json_mode=True,
        )
        try:
            obj = _parse_json_object(raw)
            items_raw = obj.get("items") or {}
        except (json.JSONDecodeError, TypeError) as e:
            raise RuntimeError(f"抽取 JSON 解析失败，模型原文：{raw[:2000]!r}") from e

        items: dict[str, GAD7ExtractItem] = {}
        for q in GAD7_ITEM_IDS:
            cell = items_raw.get(q)
            if not isinstance(cell, dict):
                items[q] = GAD7ExtractItem(needs_clarification=True)
                continue
            score = cell.get("score")
            if score is not None:
                try:
                    score = int(score)
                except (TypeError, ValueError):
                    score = None
            conf = cell.get("confidence")
            try:
                conf_f = float(conf) if conf is not None else 0.0
            except (TypeError, ValueError):
                conf_f = 0.0
            needs = bool(cell.get("needs_clarification", True))
            items[q] = GAD7ExtractItem(score=score, confidence=conf_f, needs_clarification=needs)
        return GAD7ExtractResult(items=items)


def build_ai_client(settings: Settings) -> AIClient:
    if str(settings.ai_backend).lower() == "http":
        if not str(settings.llm_base_url).strip() or not str(settings.llm_api_key).strip():
            raise ValueError(
                "GAD7_AI_BACKEND=http 时必须配置 GAD7_LLM_BASE_URL 与 GAD7_LLM_API_KEY",
            )
        return HttpOpenAICompatibleClient(settings)
    return StubAIClient()
