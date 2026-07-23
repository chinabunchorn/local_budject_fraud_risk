"use client";

/**
 * Live RAG chat — the one feature that calls inference through the LANTA tunnel.
 * Streams a cited Thai answer; every [C#] marker opens the real source (PDF page
 * or regulation text). When the tunnel is down it shows the designed
 * "outside demonstration window" state and points back to the dashboard. A live
 * telemetry panel under each answer carries the streaming-optimization metrics.
 */

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { FileText, Scale, Send, ShieldAlert, Sparkles } from "lucide-react";

import { DocumentViewerDialog, useDocumentViewer } from "@/components/document-viewer";
import { TelemetryPanel } from "@/components/telemetry-panel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { api, type RegulationOut } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  streamChat,
  type ChatCitation,
  type ChatMessageIn,
  type ChatTelemetry,
} from "@/lib/chat";

interface AssistantMsg {
  id: string;
  role: "assistant";
  text: string;
  blocked: boolean;
  citations: ChatCitation[];
  telemetry: ChatTelemetry | null;
  degraded: boolean;
  degradedMsg: string;
  error: string | null;
  streaming: boolean;
}
interface UserMsg {
  id: string;
  role: "user";
  text: string;
}
type Msg = UserMsg | AssistantMsg;

const SUGGESTIONS = [
  "งบประมาณโครงการถนนบ้านวัดไทร หมู่ ๔ ตำบลหัวเขา ปี ๒๕๖๘ เพิ่มขึ้นจากปีก่อนเท่าไร",
  "ราคาต่อหน่วยของถังน้ำพลาสติกขนาด ๒,๐๐๐ ลิตร ปี ๖๗ กับปี ๖๘ ต่างกันอย่างไร",
  "มาตรา ๓๗ แห่งพระราชบัญญัติวินัยการเงินการคลังของรัฐ กล่าวถึงเรื่องใด",
  "วิธีจัดซื้อจัดจ้างแบบเฉพาะเจาะจงใช้ได้ในกรณีใดตามระเบียบ",
];

const CITATION_RE = /(\[C\d+\])/g;

export default function ChatPage() {
  const { token } = useAuth();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const viewer = useDocumentViewer();
  const [regOpen, setRegOpen] = useState(false);
  const [regulation, setRegulation] = useState<RegulationOut | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchAssistant = useCallback(
    (id: string, patch: Partial<AssistantMsg>) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id && m.role === "assistant" ? { ...m, ...patch } : m,
        ),
      );
    },
    [],
  );

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || sending || !token) return;

      const history: ChatMessageIn[] = messages
        .filter((m) => (m.role === "user" ? true : !m.error && !m.degraded))
        .map((m) => ({ role: m.role, content: m.text }))
        .filter((m) => m.content.trim().length > 0);

      const userMsg: UserMsg = { id: crypto.randomUUID(), role: "user", text: q };
      const aid = crypto.randomUUID();
      const assistant: AssistantMsg = {
        id: aid,
        role: "assistant",
        text: "",
        blocked: false,
        citations: [],
        telemetry: null,
        degraded: false,
        degradedMsg: "",
        error: null,
        streaming: true,
      };
      setMessages((prev) => [...prev, userMsg, assistant]);
      setInput("");
      setSending(true);

      const controller = new AbortController();
      abortRef.current = controller;
      await streamChat(
        token,
        q,
        history,
        {
          onToken: (text, blocked) =>
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aid && m.role === "assistant"
                  ? { ...m, text: m.text + text, blocked: m.blocked || blocked }
                  : m,
              ),
            ),
          onCitations: (citations) => patchAssistant(aid, { citations }),
          onTelemetry: (telemetry) => patchAssistant(aid, { telemetry }),
          onDegraded: (message) =>
            patchAssistant(aid, { degraded: true, degradedMsg: message }),
          onError: (message) => patchAssistant(aid, { error: message }),
          onDone: () => patchAssistant(aid, { streaming: false }),
        },
        controller.signal,
      );
      patchAssistant(aid, { streaming: false });
      setSending(false);
    },
    [messages, sending, token, patchAssistant],
  );

  async function openCitation(c: ChatCitation) {
    if (c.kind === "regulation" && c.regulation_code) {
      setRegulation(null);
      setRegOpen(true);
      try {
        setRegulation(
          await api<RegulationOut>(`/regulations/${c.regulation_code}`, token),
        );
      } catch {
        /* leave dialog in loading state on failure */
      }
    } else if (c.document_id) {
      viewer.openDocument(c.document_id, c.source_label_th, c.page);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">ถาม-ตอบเอกสาร (ผู้ช่วยสด)</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          ถามเป็นภาษาไทยเกี่ยวกับเอกสารโครงการและระเบียบที่เกี่ยวข้อง คำตอบทุกข้อจะอ้างอิงแหล่งที่มา
          ที่เปิดตรวจได้ · ผู้ช่วยนี้ทำงานผ่านการเชื่อมต่อสด จึงพร้อมใช้งานเฉพาะช่วงสาธิต
        </p>
      </div>

      <div
        ref={scrollRef}
        className="flex min-h-[46vh] flex-col gap-4 overflow-y-auto rounded-lg border border-border bg-secondary/30 p-4"
      >
        {messages.length === 0 ? (
          <div className="m-auto max-w-lg text-center">
            <Sparkles className="mx-auto mb-3 size-6 text-primary" aria-hidden />
            <p className="mb-4 text-sm text-muted-foreground">
              เริ่มต้นด้วยคำถามตัวอย่าง หรือพิมพ์คำถามของคุณด้านล่าง
            </p>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-md border border-border bg-white px-3 py-2 text-left text-sm text-foreground hover:border-primary hover:bg-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-lg rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex flex-col">
                <div className="max-w-[92%] rounded-lg rounded-bl-sm border border-border bg-white px-4 py-3">
                  {m.degraded ? (
                    <Alert>
                      <ShieldAlert className="size-4" aria-hidden />
                      <AlertTitle>ผู้ช่วยสดไม่พร้อมใช้งานขณะนี้</AlertTitle>
                      <AlertDescription>{m.degradedMsg}</AlertDescription>
                    </Alert>
                  ) : m.error ? (
                    <p className="text-sm text-destructive">{m.error}</p>
                  ) : (
                    <AnswerBody
                      text={m.text}
                      streaming={m.streaming}
                      citations={m.citations}
                      onOpen={openCitation}
                    />
                  )}
                  {m.citations.length > 0 ? (
                    <CitationList citations={m.citations} onOpen={openCitation} />
                  ) : null}
                </div>
                {m.telemetry ? <TelemetryPanel telemetry={m.telemetry} /> : null}
              </div>
            ),
          )
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-end gap-2"
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={2}
          placeholder="พิมพ์คำถามเป็นภาษาไทย… (Enter เพื่อส่ง, Shift+Enter ขึ้นบรรทัดใหม่)"
          className="min-h-0 resize-none"
        />
        <Button type="submit" disabled={sending || !input.trim()} className="h-10">
          <Send className="size-4" aria-hidden />
          ส่ง
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        ผู้ช่วยแจ้งจุดที่ควรตรวจสอบจากเอกสารเท่านั้น ไม่ใช่ข้อสรุป — การวินิจฉัยขั้นสุดท้ายเป็นของผู้ตรวจสอบ
      </p>

      <DocumentViewerDialog
        open={viewer.open}
        onOpenChange={viewer.setOpen}
        documentId={viewer.documentId}
        filename={viewer.filename}
        page={viewer.page}
        token={token}
      />
      <Dialog open={regOpen} onOpenChange={setRegOpen}>
        <DialogContent className="max-w-2xl sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {regulation
                ? `${regulation.act_name_th} · มาตรา/ข้อ ${regulation.section_no}`
                : "กำลังโหลดข้อกฎหมาย…"}
            </DialogTitle>
            {regulation?.section_title_th ? (
              <DialogDescription>{regulation.section_title_th}</DialogDescription>
            ) : null}
          </DialogHeader>
          {regulation ? (
            <p className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {regulation.text}
            </p>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AnswerBody({
  text,
  streaming,
  citations,
  onOpen,
}: {
  text: string;
  streaming: boolean;
  citations: ChatCitation[];
  onOpen: (c: ChatCitation) => void;
}) {
  const byLabel = new Map(citations.map((c) => [c.label, c]));
  const parts = text.split(CITATION_RE);
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
      {parts.map((part, i) => {
        const match = /^\[C(\d+)\]$/.exec(part);
        if (!match) return <Fragment key={i}>{part}</Fragment>;
        const label = Number(match[1]);
        const c = byLabel.get(label);
        return (
          <button
            key={i}
            type="button"
            disabled={!c}
            onClick={() => c && onOpen(c)}
            title={c?.source_label_th}
            className="mx-0.5 inline-flex items-center rounded bg-accent px-1 text-[11px] font-medium text-accent-foreground align-baseline enabled:hover:bg-primary enabled:hover:text-primary-foreground disabled:opacity-70"
          >
            C{label}
          </button>
        );
      })}
      {streaming ? <span className="ml-0.5 inline-block animate-pulse">▋</span> : null}
    </p>
  );
}

function CitationList({
  citations,
  onOpen,
}: {
  citations: ChatCitation[];
  onOpen: (c: ChatCitation) => void;
}) {
  return (
    <div className="mt-3 border-t border-border pt-2">
      <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">
        แหล่งอ้างอิง (คลิกเพื่อเปิดต้นฉบับ)
      </div>
      <ul className="flex flex-col gap-1">
        {citations.map((c) => (
          <li key={c.label}>
            <button
              type="button"
              onClick={() => onOpen(c)}
              className="flex w-full items-start gap-2 rounded-md px-2 py-1 text-left text-xs hover:bg-accent"
            >
              <span className="mt-0.5 shrink-0 rounded bg-accent px-1 text-[11px] font-medium text-accent-foreground">
                C{c.label}
              </span>
              {c.kind === "regulation" ? (
                <Scale className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              ) : (
                <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              )}
              <span className="text-foreground">{c.source_label_th}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
