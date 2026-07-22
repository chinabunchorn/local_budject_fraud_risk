"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

// Mirrors backend DISCLAIMER_TH — the persistent responsible-AI statement.
export const DISCLAIMER_TH =
  "ผลการวิเคราะห์นี้เป็นการแจ้งจุดที่ควรตรวจสอบเพิ่มเติมจากระบบช่วยวิเคราะห์เท่านั้น " +
  "ไม่ใช่ข้อสรุปหรือคำตัดสินใด ๆ ผู้ตรวจสอบเป็นผู้พิจารณาและตัดสินใจขั้นสุดท้าย";

const NAV = [
  { href: "/", label: "ภาพรวม" },
  { href: "/projects", label: "โครงการ" },
  { href: "/budget-items", label: "สรุปการจัดซื้อ" },
  { href: "/trends", label: "แนวโน้ม" },
];

const ROLE_TH: Record<string, string> = {
  ADMIN: "ผู้ดูแลระบบ",
  SENIOR_AUDITOR: "ผู้ตรวจสอบอาวุโส",
  AUDITOR: "ผู้ตรวจสอบ",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, token, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  if (!ready) return null;
  if (!token) return null;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-3">
              <span
                className="flex size-8 items-center justify-center rounded bg-primary text-sm font-bold text-primary-foreground"
                aria-hidden
              >
                ตส
              </span>
              <span className="leading-tight">
                <span className="block text-[15px] font-semibold text-foreground">
                  ระบบช่วยวิเคราะห์ความเสี่ยงงบประมาณท้องถิ่น
                </span>
                <span className="block text-xs text-muted-foreground">
                  เครื่องมือสนับสนุนการตรวจสอบ — ต้นแบบ
                </span>
              </span>
            </Link>
            <nav className="flex items-center gap-1">
              {NAV.map((item) => {
                const active =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      active
                        ? "rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-foreground"
                        : "rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                    }
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-4">
            {user ? (
              <span className="text-right leading-tight">
                <span className="block text-sm font-medium text-foreground">
                  {user.display_name_th}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {ROLE_TH[user.role] ?? user.role}
                </span>
              </span>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
            >
              ออกจากระบบ
            </Button>
          </div>
        </div>
      </header>

      <div className="border-b border-border bg-secondary">
        <p className="mx-auto w-full max-w-6xl px-6 py-2 text-[13px] text-secondary-foreground">
          {DISCLAIMER_TH}
        </p>
      </div>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>

      <footer className="border-t border-border bg-white">
        <p className="mx-auto w-full max-w-6xl px-6 py-4 text-xs text-muted-foreground">
          ข้อมูลจากเอกสารจัดซื้อจัดจ้างและงบประมาณที่ผ่านการประมวลผลล่วงหน้า —
          ระบบไม่เรียกใช้แบบจำลองภาษาระหว่างการแสดงผล
        </p>
      </footer>
    </div>
  );
}
