/**
 * GAD-7 前端 — 对接 /v1 API（spec.md）
 */
const API_PREFIX = "/v1";

const GAD7_LABELS = {
  Q1: "紧张、不安或易怒",
  Q2: "无法停止或控制担忧",
  Q3: "对各类事务过度担忧",
  Q4: "难以放松",
  Q5: "坐立不安",
  Q6: "易激惹或烦躁",
  Q7: "感到害怕",
};

const SEVERITY_ZH = {
  minimal: "最小焦虑",
  mild: "轻度",
  moderate: "中度",
  severe: "重度",
};

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

async function apiJson(path, options = {}) {
  const res = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg = data?.error?.message || res.statusText || "请求失败";
    const code = data?.error?.code || String(res.status);
    const err = new Error(msg);
    err.code = code;
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data;
}

function el(tag, className, html) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (html != null) n.innerHTML = html;
  return n;
}

function formatItemStatus(item) {
  if (item.score != null && !item.needs_clarification) {
    return `已锁定 · ${item.score}`;
  }
  if (item.score != null && item.needs_clarification) {
    return `待澄清 · ${item.score}`;
  }
  if (item.needs_clarification) {
    return "需澄清";
  }
  return "未打分";
}

function renderSnapshot(sidebarList, snapshot) {
  sidebarList.innerHTML = "";
  if (!snapshot || !snapshot.items) return;
  const order = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"];
  for (const q of order) {
    const item = snapshot.items[q] || {};
    const li = el("li", "snapshot-item");
    if (item.score != null && !item.needs_clarification) li.classList.add("snapshot-item--done");
    else if (item.needs_clarification) li.classList.add("snapshot-item--clarify");

    const left = el("div", null);
    left.appendChild(el("span", "snapshot-item__id", q));
    const cap = el("div", null);
    cap.style.fontSize = "11px";
    cap.style.color = "var(--text-quaternary)";
    cap.style.marginTop = "2px";
    cap.textContent = GAD7_LABELS[q] || "";
    left.appendChild(cap);

    const right = el("div", "snapshot-item__meta", formatItemStatus(item));
    li.appendChild(left);
    li.appendChild(right);
    sidebarList.appendChild(li);
  }
}

function appendMessage(container, role, content, streaming = false) {
  const wrap = el("div", `msg msg--${role === "user" ? "user" : "assistant"}`);
  wrap.appendChild(el("div", "msg__role", role === "user" ? "你" : "助手"));
  const body = el("div", "msg-body");
  body.textContent = content;
  wrap.appendChild(body);
  if (streaming) wrap.dataset.streaming = "1";
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
  return { wrap, body };
}

function setStreamingMessage(bodyEl, text) {
  bodyEl.textContent = text;
  const container = bodyEl.closest(".messages");
  if (container) container.scrollTop = container.scrollHeight;
}

async function readSseStream(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const lines = chunk.split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let evt;
        try {
          evt = JSON.parse(raw);
        } catch {
          continue;
        }
        const type = evt.event;
        if (type === "token" && handlers.onToken) handlers.onToken(evt.delta || "");
        if (type === "message_complete" && handlers.onMessageComplete) handlers.onMessageComplete(evt.message);
        if (type === "gad7_update" && handlers.onGad7) handlers.onGad7(evt.gad7_snapshot);
        if (type === "done" && handlers.onDone) handlers.onDone();
        if (type === "error") {
          throw new Error(evt.code || evt.message || "STREAM_ERROR");
        }
      }
    }
  }
}

const state = {
  sessionId: null,
  snapshot: null,
  busy: false,
};

function init() {
  const ack = document.getElementById("disclaimer-ack");
  const btnStart = document.getElementById("btn-start");
  const btnReport = document.getElementById("btn-report");
  const btnNew = document.getElementById("btn-new-session");
  const messagesEl = document.getElementById("messages");
  const sidebarList = document.getElementById("snapshot-items");
  const input = document.getElementById("message-input");
  const btnSend = document.getElementById("btn-send");
  const statusEl = document.getElementById("status");
  const composer = document.getElementById("composer");

  const modal = document.getElementById("report-modal");
  const modalBody = document.getElementById("report-modal-body");
  const modalClose = document.getElementById("report-modal-close");

  function setStatus(text, isError = false) {
    statusEl.textContent = text || "";
    statusEl.classList.toggle("status-bar--error", isError);
  }

  function updateChrome() {
    const hasSession = !!state.sessionId;
    btnSend.disabled = state.busy || !hasSession;
    input.disabled = state.busy || !hasSession;
    btnReport.disabled = !hasSession || !(state.snapshot && state.snapshot.ready_for_summary);
    composer.style.display = hasSession ? "" : "none";
 }

  async function loadHistory() {
    if (!state.sessionId) return;
    const data = await apiJson(`/sessions/${state.sessionId}/messages?limit=200`);
    messagesEl.innerHTML = "";
    for (const m of data.messages || []) {
      appendMessage(messagesEl, m.role, m.content);
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function refreshMeta() {
    if (!state.sessionId) return;
    try {
      const meta = await apiJson(`/sessions/${state.sessionId}`);
      if (meta.model_id) {
        const mid = document.getElementById("model-id");
        if (mid) mid.textContent = meta.model_id;
      }
    } catch {
      /* ignore */
    }
  }

  btnStart.addEventListener("click", async () => {
    if (!ack.checked) {
      setStatus("请先阅读并勾选免责声明。", true);
      return;
    }
    setStatus("");
    btnStart.disabled = true;
    state.busy = true;
    updateChrome();
    try {
      const created = await apiJson("/sessions", {
        method: "POST",
        body: JSON.stringify({
          locale: "zh-CN",
          preferences: {
            tone: "supportive",
            disclaimer_acknowledged: true,
          },
        }),
      });
      state.sessionId = created.session_id;
      state.snapshot = null;
      renderSnapshot(sidebarList, { items: {} });
      await loadHistory();
      await refreshMeta();
      setStatus("会话已创建，可直接在下方输入回复。");
    } catch (e) {
      setStatus(e.message || "创建会话失败", true);
    } finally {
      state.busy = false;
      btnStart.disabled = false;
      updateChrome();
    }
  });

  btnNew.addEventListener("click", async () => {
    if (state.sessionId && !confirm("结束当前会话并开始新的？（旧会话仍保留在服务端）")) return;
    state.sessionId = null;
    state.snapshot = null;
    messagesEl.innerHTML = "";
    renderSnapshot(sidebarList, { items: {} });
    setStatus("");
    updateChrome();
    document.querySelector(".hero")?.scrollIntoView({ behavior: "smooth" });
  });

  async function sendMessage() {
    const text = (input.value || "").trim();
    if (!text || !state.sessionId || state.busy) return;
    const clientId = uuid();
    appendMessage(messagesEl, "user", text);
    input.value = "";
    state.busy = true;
    updateChrome();
    setStatus("正在生成回复…");

    let streamMsg = null;
    let streamBody = null;
    let acc = "";

    try {
      const res = await fetch(`${API_PREFIX}/sessions/${state.sessionId}/messages:stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: "user",
          content: text,
          client_message_id: clientId,
        }),
      });

      if (!res.ok) {
        const t = await res.text();
        let errMsg = res.statusText;
        try {
          const j = JSON.parse(t);
          errMsg = j?.error?.message || errMsg;
        } catch {
          /* noop */
        }
        throw new Error(errMsg);
      }

      streamMsg = appendMessage(messagesEl, "assistant", "", true);
      streamBody = streamMsg.body;

      await readSseStream(res, {
        onToken(delta) {
          acc += delta;
          setStreamingMessage(streamBody, acc);
        },
        onMessageComplete(msg) {
          if (msg && typeof msg.content === "string") {
            acc = msg.content;
            setStreamingMessage(streamBody, acc);
          }
        },
        onGad7(snap) {
          state.snapshot = snap;
          renderSnapshot(sidebarList, snap);
        },
        onDone() {},
      });

      if (streamMsg && streamMsg.wrap) delete streamMsg.wrap.dataset.streaming;
      setStatus("");
 } catch (e) {
      if (streamMsg && streamMsg.wrap) streamMsg.wrap.remove();
      setStatus(e.message || "发送失败", true);
    } finally {
      state.busy = false;
      updateChrome();
    }
  }

  btnSend.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendMessage();
    }
  });

  btnReport.addEventListener("click", async () => {
    if (!state.sessionId) return;
    setStatus("加载报告…");
    try {
      const report = await apiJson(`/sessions/${state.sessionId}/gad7/report`);
      const band = report.severity_band ? SEVERITY_ZH[report.severity_band] || report.severity_band : "—";
      const total = report.total != null ? report.total : "—";
      modalBody.innerHTML = "";

      const sum = el("div", "report-summary");
      sum.innerHTML = `<strong>总分</strong>：${total} &nbsp;·&nbsp; <strong>严重度（参考）</strong>：${band}<br/><span style="color:var(--text-tertiary);font-size:13px;margin-top:8px;display:inline-block">${escapeHtml(report.summary_text || "")}</span>`;
      modalBody.appendChild(sum);

      const ul = el("ul", "report-items");
      for (const it of report.items || []) {
        const li = el("li", "report-item");
        const score = it.score != null ? it.score : "—";
        li.innerHTML = `<strong>${escapeHtml(it.id)}</strong> · 分 ${score}<div style="margin-top:6px;color:var(--text-tertiary);font-size:13px">${escapeHtml(it.rationale || "")}</div>`;
        ul.appendChild(li);
      }
      modalBody.appendChild(ul);

      const disc = el("div", "report-disclaimer", escapeHtml(report.disclaimer || ""));
      modalBody.appendChild(disc);

      openReportModal(true);
      setStatus("");
    } catch (e) {
      setStatus(e.message || "无法加载报告", true);
    }
  });

  function openReportModal(open) {
    modal.hidden = !open;
    modal.setAttribute("aria-hidden", open ? "false" : "true");
  }

  modalClose.addEventListener("click", () => {
    openReportModal(false);
  });
  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) openReportModal(false);
  });

  renderSnapshot(sidebarList, { items: {} });
  updateChrome();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", init);
