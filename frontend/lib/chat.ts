/**
 * SSE client for the live RAG chat endpoint (POST /api/chat).
 *
 * This is the ONE place in the frontend that touches live inference. The
 * dashboard `api()` helper reads JSON; chat streams Server-Sent Events, so we
 * read the response body ourselves and dispatch each event to a handler.
 *
 * Event contract (backend/app/api/chat.py):
 *   token      {text, blocked}   — a lexicon-checked answer segment
 *   citations  {citations:[…]}   — verified sources, sent once at the end
 *   telemetry  {…}               — streaming metrics for the live panel
 *   degraded   {message}         — tunnel down: outside demonstration window
 *   error      {message}
 *   done       {disclaimer_th}
 */

import { API_BASE } from "@/lib/api";

export interface ChatCitation {
  label: number;
  kind: "document" | "regulation";
  source_label_th: string;
  quote_th: string;
  document_id: string | null;
  page: number | null;
  regulation_code: string | null;
}

export interface ChatTelemetry {
  ttft_raw_ms: number | null;
  ttft_backend_ms: number | null;
  ttft_display_ms: number | null;
  queue_wait_ms: number | null;
  prefill_ms: number | null;
  decode_tokens_per_sec: number | null;
  inter_token_p50_ms: number | null;
  inter_token_p95_ms: number | null;
  output_tokens: number | null;
  e2e_ms: number | null;
  stages_ms: Record<string, number>;
  degraded: boolean;
}

export interface ChatMessageIn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatHandlers {
  onToken: (text: string, blocked: boolean) => void;
  onCitations: (citations: ChatCitation[]) => void;
  onTelemetry: (telemetry: ChatTelemetry) => void;
  onDegraded: (message: string) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

function dispatch(event: string, data: string, h: ChatHandlers) {
  let payload: Record<string, unknown> = {};
  if (data) {
    try {
      payload = JSON.parse(data);
    } catch {
      return;
    }
  }
  switch (event) {
    case "token":
      h.onToken(String(payload.text ?? ""), Boolean(payload.blocked));
      break;
    case "citations":
      h.onCitations((payload.citations as ChatCitation[]) ?? []);
      break;
    case "telemetry":
      h.onTelemetry(payload as unknown as ChatTelemetry);
      break;
    case "degraded":
      h.onDegraded(String(payload.message ?? ""));
      break;
    case "error":
      h.onError(String(payload.message ?? "เกิดข้อผิดพลาด"));
      break;
    case "done":
      h.onDone();
      break;
  }
}

export async function streamChat(
  token: string,
  question: string,
  history: ChatMessageIn[],
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ question, history }),
      signal,
    });
  } catch {
    handlers.onError("เชื่อมต่อระบบไม่สำเร็จ");
    return;
  }

  if (!res.ok || !res.body) {
    handlers.onError(res.status === 401 ? "หมดสิทธิ์การเข้าใช้งาน" : "ระบบขัดข้อง");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      break; // aborted or connection dropped mid-stream
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (event) dispatch(event, data, handlers);
    }
  }
}
