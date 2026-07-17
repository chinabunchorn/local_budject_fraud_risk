"use client";

/**
 * Simple JWT auth for the prototype: token in localStorage, user hydrated from
 * /auth/me. A 401 anywhere routes back to /login (see useApi).
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, type TokenResponse, type UserOut } from "@/lib/api";

const TOKEN_KEY = "m3.token";

interface AuthState {
  token: string | null;
  user: UserOut | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Deferred so state updates happen asynchronously (post-hydration)
    Promise.resolve().then(async () => {
      if (cancelled) return;
      const stored = window.localStorage.getItem(TOKEN_KEY);
      if (!stored) {
        setReady(true);
        return;
      }
      setToken(stored);
      try {
        const me = await api<UserOut>("/auth/me", stored);
        if (!cancelled) setUser(me);
      } catch {
        window.localStorage.removeItem(TOKEN_KEY);
        if (!cancelled) setToken(null);
      } finally {
        if (!cancelled) setReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api<TokenResponse>("/auth/login", null, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    window.localStorage.setItem(TOKEN_KEY, res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
