"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi, getToken, setToken } from "@/lib/api";
import type { LoginPayload, RegisterPayload, User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const existing = getToken();
    if (!existing) {
      setIsLoading(false);
      return;
    }
    setTokenState(existing);
    authApi
      .me()
      .then((u) => setUser(u))
      .catch(() => {
        // Token invalid/expired — clear it and force re-login.
        setToken(null);
        setTokenState(null);
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const res = await authApi.login(payload);
    setToken(res.access_token);
    setTokenState(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await authApi.register(payload);
    setToken(res.access_token);
    setTokenState(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!getToken()) return;
    const u = await authApi.me();
    setUser(u);
  }, []);

  // Refresh user state whenever the app regains focus — e.g. the user
  // taps the email-verification link (which opens in the phone's browser,
  // a separate session from the app's) and then switches back into the
  // app. Without this, the "verify your email" banner would keep showing
  // until the next manual reload even though verification succeeded.
  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === "visible" && getToken()) {
        refreshUser().catch(() => {
          // Non-fatal — the next explicit action that needs fresh user
          // data (or the next resume) will just try again.
        });
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [refreshUser]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, isLoading, login, register, logout, refreshUser }),
    [user, token, isLoading, login, register, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
