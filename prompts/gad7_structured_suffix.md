# GAD-7 结构化侧车 — 追加到 System/Developer 的片段

当采用 **JSON 侧车（spec 模式 A）** 时，在 `gad7_system.md` 的主 system **之后**追加本段（或作为独立 `developer` 消息），要求模型在**不展示给用户**的通道输出结构化结果。具体实现取决于你们的推理服务：例如 `response_format`、tool call、或要求模型在 `<gad7_json>...</gad7_json>` 中输出并由网关剥离。

---

## 追加片段（中文指令）

```
【结构化输出（仅服务端解析，禁止出现在对用户可见的正文里）】
每一轮你在生成完给用户看的自然语言之后，必须额外输出一段可被程序解析的 JSON（放在单独字段或由网关截取），严格符合下列语义：

{
  "current_focus": "Q1" | "Q2" | ... | "Q7" | "done",
  "items": {
    "Q1": { "score": null | 0 | 1 | 2 | 3, "confidence": 0.0-1.0, "needs_clarification": true | false, "brief_reason": "10字内，供日志" },
    "Q2": { ... },
    ...
 "Q7": { ... }
  },
  "ready_for_summary": true | false,
  "off_topic_redirected": true | false
}

规则：
- 仅当满足「过去两周 + 频率四档之一 + 无矛盾」时，将对应 Qi 的 score 填 0–3，confidence 取高；否则 score 为 null，needs_clarification 为 true。
- 若本轮用户内容主要为跑题，items 可不变，off_topic_redirected 为 true。
- 七项 score 均非 null 时，ready_for_summary 为 true，current_focus 为 "done"。
- brief_reason 不得包含用户敏感原文长引述。
```

---

## JSON Schema 草案（供 `response_format` 或校验器）

```json
{
  "type": "object",
  "required": ["current_focus", "items", "ready_for_summary", "off_topic_redirected"],
  "properties": {
    "current_focus": {
      "type": "string",
      "enum": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "done"]
    },
    "items": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["score", "confidence", "needs_clarification", "brief_reason"],
        "properties": {
          "score": { "type": ["integer", "null"], "minimum": 0, "maximum": 3 },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
          "needs_clarification": { "type": "boolean" },
          "brief_reason": { "type": "string", "maxLength": 64 }
        }
      }
    },
    "ready_for_summary": { "type": "boolean" },
    "off_topic_redirected": { "type": "boolean" }
  }
}
```
