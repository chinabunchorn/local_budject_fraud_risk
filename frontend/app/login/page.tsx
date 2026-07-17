"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DISCLAIMER_TH } from "@/components/app-shell";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, token, ready } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && token) router.replace("/");
  }, [ready, token, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/40 px-6">
      <div className="w-full max-w-sm rounded-lg border border-border bg-white p-8">
        <div className="mb-6 flex items-center gap-3">
          <span
            className="flex size-10 items-center justify-center rounded bg-primary text-base font-bold text-primary-foreground"
            aria-hidden
          >
            ตส
          </span>
          <div className="leading-tight">
            <div className="font-semibold text-foreground">
              ระบบช่วยวิเคราะห์ความเสี่ยงงบประมาณท้องถิ่น
            </div>
            <div className="text-xs text-muted-foreground">สำหรับเจ้าหน้าที่ตรวจสอบ</div>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">ชื่อผู้ใช้</Label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">รหัสผ่าน</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? (
            <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "กำลังเข้าสู่ระบบ…" : "เข้าสู่ระบบ"}
          </Button>
        </form>
      </div>
      <p className="mt-6 max-w-md text-center text-xs text-muted-foreground">{DISCLAIMER_TH}</p>
    </div>
  );
}
