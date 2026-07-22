"use client";

/**
 * The citation viewer: renders the real source PDF — not just extracted
 * text — jumped to the cited page via the `#page=N` fragment that browsers'
 * built-in PDF viewers honor. A plain `<iframe src>` can't carry an
 * Authorization header, so the file is fetched as a blob first and the
 * fragment is applied to that blob: URL.
 */

import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { API_BASE } from "@/lib/api";

export function DocumentViewerDialog({
  open,
  onOpenChange,
  documentId,
  filename,
  page,
  token,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  filename: string | null;
  page: number | null;
  token: string | null;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !documentId || !token) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    Promise.resolve()
      .then(() => {
        if (cancelled) return null;
        setBlobUrl(null);
        setError(null);
        return fetch(`${API_BASE}/documents/${documentId}/file`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      })
      .then((res) => {
        if (!res || cancelled) return null;
        if (!res.ok) throw new Error("โหลดเอกสารไม่สำเร็จ");
        return res.blob();
      })
      .then((blob) => {
        if (cancelled || !blob) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setError("ไม่สามารถโหลดเอกสารต้นฉบับได้ในขณะนี้");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [open, documentId, token]);

  const src = blobUrl ? `${blobUrl}#page=${page ?? 1}` : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] w-[95vw] max-w-6xl flex-col sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>เอกสารต้นฉบับ</DialogTitle>
          <DialogDescription>
            {filename ?? "กำลังโหลด…"}
            {page ? ` · เปิดที่หน้า ${page}` : ""}
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : src ? (
          <iframe
            key={src}
            src={src}
            title={`เอกสารต้นฉบับ: ${filename ?? ""}`}
            className="min-h-0 w-full flex-1 rounded-md border border-border bg-muted/20"
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            กำลังโหลดเอกสาร…
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** State hook for driving one DocumentViewerDialog per page. */
export function useDocumentViewer() {
  const [open, setOpen] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [page, setPage] = useState<number | null>(null);

  function openDocument(id: string, name: string | null, atPage: number | null) {
    setDocumentId(id);
    setFilename(name);
    setPage(atPage);
    setOpen(true);
  }

  return { open, setOpen, documentId, filename, page, openDocument };
}
