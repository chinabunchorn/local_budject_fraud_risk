"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * GET hook: fetches once the token is ready; on 401 clears the session and
 * returns to /login. Refetches keep the previous data on screen (no skeleton
 * flash).
 */
export function useApi<T>(path: string | null) {
  const { token, ready, logout } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!ready || !path) return;
    if (!token) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    api<T>(path, token)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) {
          logout();
          router.replace("/login");
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [path, token, ready, nonce, router, logout]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { data, error, loading: data === null && error === null, reload };
}
