import { API_PREFIX } from "./constants.js";

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function apiJson(path, options = {}) {
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
    const err = new Error(msg);
    err.code = data?.error?.code || String(res.status);
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data;
}

export async function readSseStream(response, handlers) {
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
