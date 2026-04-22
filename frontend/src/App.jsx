import { useCallback, useEffect, useRef, useState } from "react";
import { apiJson, readSseStream, uuid } from "./api.js";
import { API_PREFIX, GAD7_LABELS, GAD7_ORDER, LOCALES, SEVERITY_TEXT } from "./constants.js";

const I18N = {
  "zh-CN": {
    pageTitle: "GAD-7评估",
    report: "查看报告",
    newSession: "新会话",
    reportTitle: "结构化评估",
    close: "关闭",
    totalScore: "总分",
    severityRef: "严重度（参考）",
    notConnected: "未连接",
    startTitle: "通过对话完成筛查",
    startDesc:
      "本工具基于 GAD-7 量表思路，用自然语言引导你描述过去两周的感受；服务端会同步更新各题打分快照。结果仅供教育与自助参考，不能替代专业诊断。",
    disclaimer:
      "我已阅读并理解：本服务非医疗诊断；若你有自伤/伤人风险或严重痛苦，请立即联系当地紧急服务或专业机构。",
    startEval: "开始评估",
    sessionOn: "评估进行中",
    sessionRange: "范围：最近两周",
    nonDiagnosis: "结果仅供参考，非诊断",
    model: "模型",
    chatAria: "对话",
    emptyHint: "开始会话后，助手会先发言。",
    roleUser: "你",
    roleAssistant: "助手",
    inputLabel: "你的回复",
    inputPlaceholder: "用自然语言描述你的情况，Enter 发送，Shift+Enter 换行",
    send: "发送",
    networkHint: "网络或模型异常时会显示提示，可稍后重试。",
    snapshotTitle: "量表快照",
    snapshotLegend: "图标含义：已锁定表示该项分值可信；需澄清表示助手可能会继续追问频率细节。",
    statusLocked: "已锁定",
    statusPending: "待澄清",
    statusNeedClarify: "需澄清",
    statusUnscored: "未打分",
    mustAck: "请先阅读并勾选免责声明。",
    sessionReady: "会话已创建，可直接在下方输入回复。",
    createFail: "创建会话失败",
    confirmNewSession: "结束当前会话并开始新的？（旧会话仍保留在服务端）",
    generating: "正在生成回复…",
    sendFail: "发送失败",
    loadingReport: "加载报告…",
    reportFail: "无法加载报告",
    jumpLatest: "回到底部",
    themeLight: "亮色",
    themeDark: "暗色",
    langZh: "中文",
    langEn: "English",
    na: "—",
    score: "分",
  },
  "en-US": {
    pageTitle: "GAD-7 Assessment",
    report: "Report",
    newSession: "New Session",
    reportTitle: "Structured Report",
    close: "Close",
    totalScore: "Total Score",
    severityRef: "Severity (reference)",
    notConnected: "Offline",
    startTitle: "Complete Screening by Chat",
    startDesc:
      "This tool follows GAD-7 and uses natural dialogue to understand your feelings over the past two weeks. Item snapshots update on the server in real time. Results are for educational and self-help use only, not a medical diagnosis.",
    disclaimer:
      "I understand this service is not a medical diagnosis. If you have self-harm/harm-to-others risk or severe distress, please contact local emergency services or professional support immediately.",
    startEval: "Start Assessment",
    sessionOn: "Assessment in Progress",
    sessionRange: "Window: Last 2 weeks",
    nonDiagnosis: "For reference only, not diagnosis",
    model: "Model",
    chatAria: "Conversation",
    emptyHint: "The assistant will speak first after session starts.",
    roleUser: "You",
    roleAssistant: "Assistant",
    inputLabel: "Your reply",
    inputPlaceholder: "Describe your situation naturally. Enter to send, Shift+Enter for newline",
    send: "Send",
    networkHint: "Network/model errors will be shown here. You can retry later.",
    snapshotTitle: "Questionnaire Snapshot",
    snapshotLegend:
      "Legend: Locked means the item score is reliable; Needs clarification means the assistant may ask follow-up frequency details.",
    statusLocked: "Locked",
    statusPending: "Pending",
    statusNeedClarify: "Needs clarification",
    statusUnscored: "Unscored",
    mustAck: "Please read and check the disclaimer first.",
    sessionReady: "Session created. You can start replying below.",
    createFail: "Failed to create session",
    confirmNewSession: "End current session and start a new one? (Old session remains on server)",
    generating: "Generating response…",
    sendFail: "Failed to send",
    loadingReport: "Loading report…",
    reportFail: "Unable to load report",
    jumpLatest: "Jump to latest",
    themeLight: "Light",
    themeDark: "Dark",
    langZh: "中文",
    langEn: "English",
    na: "—",
    score: "Score",
  },
};

function formatItemStatus(item, t) {
  if (item.score != null && !item.needs_clarification) {
    return `${t.statusLocked} · ${item.score}`;
  }
  if (item.score != null && item.needs_clarification) {
    return `${t.statusPending} · ${item.score}`;
  }
  if (item.needs_clarification) {
    return t.statusNeedClarify;
  }
  return t.statusUnscored;
}

function SnapshotSidebar({ snapshot, locale, t }) {
  const items = snapshot?.items || {};
  const labels = GAD7_LABELS[locale] || GAD7_LABELS["zh-CN"];
  return (
    <aside className="sidebar" aria-label={t.snapshotTitle}>
      <h2 className="sidebar__title">{t.snapshotTitle}</h2>
      <ul className="snapshot-list" id="snapshot-items">
        {GAD7_ORDER.map((q) => {
          const item = items[q] || {};
          const cls = ["snapshot-item"];
          if (item.score != null && !item.needs_clarification) cls.push("snapshot-item--done");
          else if (item.needs_clarification) cls.push("snapshot-item--clarify");
          return (
            <li key={q} className={cls.join(" ")}>
              <div>
                <span className="snapshot-item__id">{q}</span>
                <div
                  style={{
                    fontSize: "11px",
                    color: "var(--text-quaternary)",
                    marginTop: "2px",
                  }}
                >
                  {labels[q] || ""}
                </div>
              </div>
              <div className="snapshot-item__meta">{formatItemStatus(item, t)}</div>
            </li>
          );
        })}
      </ul>
      <p
        style={{
          margin: "16px 0 0",
          fontSize: "12px",
          color: "var(--text-quaternary)",
          lineHeight: 1.5,
        }}
      >
        {t.snapshotLegend}
      </p>
    </aside>
  );
}

function ReportModal({ open, report, onClose, locale, t }) {
  if (!open || !report) return null;
  const sev = SEVERITY_TEXT[locale] || SEVERITY_TEXT["zh-CN"];
  const band = report.severity_band ? sev[report.severity_band] || report.severity_band : t.na;
  const total = report.total != null ? report.total : t.na;

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal">
        <div className="modal__head">
          <h2 id="report-title">{t.reportTitle}</h2>
          <button type="button" className="btn btn--ghost btn--small" onClick={onClose}>
            {t.close}
          </button>
        </div>
        <div className="modal__body">
          <div className="report-summary">
            <strong>{t.totalScore}</strong>：{total} &nbsp;·&nbsp; <strong>{t.severityRef}</strong>：{band}
            <br />
            <span style={{ color: "var(--text-tertiary)", fontSize: "13px", marginTop: "8px", display: "inline-block" }}>
              {report.summary_text || ""}
            </span>
          </div>
          <ul className="report-items">
            {(report.items || []).map((it) => (
              <li key={it.id} className="report-item">
                <strong>{it.id}</strong> · {t.score} {it.score != null ? it.score : t.na}
                <div style={{ marginTop: "6px", color: "var(--text-tertiary)", fontSize: "13px" }}>{it.rationale || ""}</div>
              </li>
            ))}
          </ul>
          <div className="report-disclaimer">{report.disclaimer || ""}</div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [locale, setLocale] = useState(() => localStorage.getItem("gad7_locale") || "zh-CN");
  const [theme, setTheme] = useState(() => localStorage.getItem("gad7_theme") || "dark");
  const [disclaimerAck, setDisclaimerAck] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [statusError, setStatusError] = useState(false);
  const [modelId, setModelId] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState(null);
  const [startLoading, setStartLoading] = useState(false);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const messagesRef = useRef(null);
  const t = I18N[locale] || I18N["zh-CN"];

  useEffect(() => {
    const safeLocale = LOCALES.includes(locale) ? locale : "zh-CN";
    localStorage.setItem("gad7_locale", safeLocale);
    document.documentElement.lang = safeLocale === "zh-CN" ? "zh-CN" : "en";
  }, [locale]);

  useEffect(() => {
    const safeTheme = theme === "light" ? "light" : "dark";
    localStorage.setItem("gad7_theme", safeTheme);
    document.documentElement.setAttribute("data-theme", safeTheme);
  }, [theme]);

  const shouldStickToBottomRef = useRef(true);

  function isNearBottom(el) {
    if (!el) return true;
    const threshold = 56;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distance <= threshold;
  }

  const scrollMessagesToEnd = useCallback(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    if (shouldStickToBottomRef.current) {
      scrollMessagesToEnd();
      setShowJumpToLatest(false);
    }
  }, [messages, scrollMessagesToEnd]);

  function handleMessagesScroll() {
    const el = messagesRef.current;
    const nearBottom = isNearBottom(el);
    shouldStickToBottomRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }

  function jumpToLatest() {
    shouldStickToBottomRef.current = true;
    scrollMessagesToEnd();
    setShowJumpToLatest(false);
  }

  const hasSession = !!sessionId;
  const readyForSummary = !!(snapshot && snapshot.ready_for_summary);

  async function refreshMeta(sid) {
    if (!sid) return;
    try {
      const meta = await apiJson(`/sessions/${sid}`);
      if (meta.model_id) setModelId(meta.model_id);
    } catch {
      /* ignore */
    }
  }

  async function loadHistory(sid) {
    const data = await apiJson(`/sessions/${sid}/messages?limit=200`);
    shouldStickToBottomRef.current = true;
    setMessages(
      (data.messages || []).map((m) => ({
        key: m.id || uuid(),
        role: m.role,
        content: m.content,
        streaming: false,
      }))
    );
  }

  async function handleStart() {
    if (!disclaimerAck) {
      setStatus(t.mustAck);
      setStatusError(true);
      return;
    }
    setStatus("");
    setStatusError(false);
    setStartLoading(true);
    setBusy(true);
    try {
      const created = await apiJson("/sessions", {
        method: "POST",
        body: JSON.stringify({
          locale,
          preferences: {
            tone: "supportive",
            disclaimer_acknowledged: true,
          },
        }),
      });
      setSessionId(created.session_id);
      setSnapshot(null);
      await loadHistory(created.session_id);
      await refreshMeta(created.session_id);
      setStatus(t.sessionReady);
    } catch (e) {
      setStatus(e.message || t.createFail);
      setStatusError(true);
    } finally {
      setBusy(false);
      setStartLoading(false);
    }
  }

  async function handleNewSession() {
    if (sessionId && !window.confirm(t.confirmNewSession)) return;
    setSessionId(null);
    setSnapshot(null);
    setMessages([]);
    setStatus("");
    setStatusError(false);
    setModelId("");
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || !sessionId || busy) return;
    const clientId = uuid();
    const userKey = uuid();
    shouldStickToBottomRef.current = true;
    setInput("");
    setMessages((m) => [...m, { key: userKey, role: "user", content: text, streaming: false }]);
    setBusy(true);
    setStatus(t.generating);
    setStatusError(false);

    const streamKey = uuid();
    setMessages((m) => [...m, { key: streamKey, role: "assistant", content: "", streaming: true }]);

    let acc = "";

    try {
      const res = await fetch(`${API_PREFIX}/sessions/${sessionId}/messages:stream`, {
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

      await readSseStream(res, {
        onToken(delta) {
          acc += delta;
          setMessages((m) =>
            m.map((row) => (row.key === streamKey ? { ...row, content: acc } : row))
          );
        },
        onMessageComplete(msg) {
          if (msg && typeof msg.content === "string") {
            acc = msg.content;
            setMessages((m) =>
              m.map((row) => (row.key === streamKey ? { ...row, content: acc } : row))
            );
          }
        },
        onGad7(snap) {
          setSnapshot(snap);
        },
        onDone() {},
      });

      setMessages((m) =>
        m.map((row) => (row.key === streamKey ? { ...row, streaming: false } : row))
      );
      setStatus("");
    } catch (e) {
      setMessages((m) => m.filter((row) => row.key !== streamKey));
      setStatus(e.message || t.sendFail);
      setStatusError(true);
    } finally {
      setBusy(false);
    }
  }

  async function handleReport() {
    if (!sessionId) return;
    setStatus(t.loadingReport);
    setStatusError(false);
    try {
      const r = await apiJson(`/sessions/${sessionId}/gad7/report`);
      setReport(r);
      setReportOpen(true);
      setStatus("");
    } catch (e) {
      setStatus(e.message || t.reportFail);
      setStatusError(true);
    }
  }

  function onKeyDown(ev) {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendMessage();
    }
  }

  return (
    <>
      <header className="app-header">
        <div className="app-brand">
          <h1 className="app-brand__title">{t.pageTitle}</h1>
          <span className="app-brand__badge" aria-live="polite">
            {modelId || t.notConnected}
          </span>
        </div>
        <div className="app-header__actions">
          <div className="segmented-control" role="group" aria-label="language">
            <button
              type="button"
              className={`segmented-control__btn${locale === "zh-CN" ? " is-active" : ""}`}
              onClick={() => setLocale("zh-CN")}
            >
              {t.langZh}
            </button>
            <button
              type="button"
              className={`segmented-control__btn${locale === "en-US" ? " is-active" : ""}`}
              onClick={() => setLocale("en-US")}
            >
              {t.langEn}
            </button>
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={() => setTheme((x) => (x === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? t.themeLight : t.themeDark}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--small"
            disabled={!hasSession || !readyForSummary}
            onClick={handleReport}
          >
            {t.report}
          </button>
          <button type="button" className="btn btn--ghost btn--small" onClick={handleNewSession}>
            {t.newSession}
          </button>
        </div>
      </header>

      <div className="app-layout">
        <main className="main">
          {!hasSession ? (
            <section className="hero">
              <h1>{t.startTitle}</h1>
              <p>
                {t.startDesc}
              </p>
              <div className="disclaimer-box">
                <label>
                  <input
                    type="checkbox"
                    checked={disclaimerAck}
                    onChange={(e) => setDisclaimerAck(e.target.checked)}
                  />
                  <span>
                    {t.disclaimer}
                  </span>
                </label>
              </div>
              <div style={{ marginTop: "20px" }}>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={startLoading || busy}
                  onClick={handleStart}
                >
                  {t.startEval}
                </button>
              </div>
            </section>
          ) : (
            <section className="session-compact" aria-label="会话关键信息">
              <span className="session-chip">{t.sessionOn}</span>
              <span className="session-chip">{t.sessionRange}</span>
              <span className="session-chip">{t.nonDiagnosis}</span>
              <span className="session-chip">
                {t.model}：{modelId || t.notConnected}
              </span>
            </section>
          )}

          <section className="chat" aria-label={t.chatAria}>
            <div
              className="messages"
              id="messages"
              role="log"
              aria-live="polite"
              ref={messagesRef}
              onScroll={handleMessagesScroll}
            >
              {messages.length === 0 && (
                <div className="empty-state">{t.emptyHint}</div>
              )}
              {messages.map((m) => (
                <div
                  key={m.key}
                  className={`msg msg--${m.role === "user" ? "user" : "assistant"}`}
                  data-streaming={m.streaming ? "1" : undefined}
                >
                  <div className="msg__role">{m.role === "user" ? t.roleUser : t.roleAssistant}</div>
                  <div className="msg-body">{m.content}</div>
                </div>
              ))}
            </div>
            {showJumpToLatest && (
              <button
                type="button"
                className="btn btn--ghost btn--small scroll-to-latest"
                onClick={jumpToLatest}
                style={{ bottom: hasSession ? "98px" : "20px" }}
              >
                {t.jumpLatest}
              </button>
            )}
            {hasSession && (
              <div className="composer">
                <div className="composer__row">
                  <label className="sr-only" htmlFor="message-input">
                    {t.inputLabel}
                  </label>
                  <textarea
                    id="message-input"
                    className="composer__input"
                    rows={2}
                    placeholder={t.inputPlaceholder}
                    autoComplete="off"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={onKeyDown}
                    disabled={busy}
                  />
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={busy}
                    onClick={sendMessage}
                  >
                    {t.send}
                  </button>
                </div>
                <div className="composer__hint">{t.networkHint}</div>
                <div className={`status-bar${statusError ? " status-bar--error" : ""}`} role="status">
                  {status}
                </div>
              </div>
            )}
          </section>
        </main>

        <SnapshotSidebar snapshot={snapshot} locale={locale} t={t} />
      </div>

      <ReportModal open={reportOpen} report={report} onClose={() => setReportOpen(false)} locale={locale} t={t} />
    </>
  );
}
