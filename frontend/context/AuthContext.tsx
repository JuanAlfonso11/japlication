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
import {
  AUTH_UNAUTHORIZED_EVENT,
  authApi,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken,
} from "@/lib/api";
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
        // A network error (backend/Tailscale briefly unreachable) leaves
        // the saved session alone — RouteGuard only checks token
        // presence, so the app stays usable and retries later (e.g. on
        // the next visibilitychange below). A genuine expired/invalid
        // token is handled by request()'s own refresh-then-give-up logic
        // in lib/api.ts, which already cleared storage and fired
        // AUTH_UNAUTHORIZED_EVENT before this rejection even reaches
        // here — see the listener below.
      })
      .finally(() => setIsLoading(false));
  }, []);

  // request()/uploadFile() (lib/api.ts) clear the saved token pair and
  // dispatch this the moment a 401 survives a silent refresh attempt —
  // i.e. the session is genuinely over, not just a momentary hiccup.
  // Reacting to it here (rather than every call site checking its own
  // error) is what makes that redirect to /login instant everywhere.
  useEffect(() => {
    function handleUnauthorized() {
      setTokenState(null);
      setUser(null);
    }
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const res = await authApi.login(payload);
    setToken(res.access_token);
    setRefreshToken(res.refresh_token);
    setTokenState(res.access_token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await authApi.register(payload);
    setToken(res.access_token);
    setRefreshToken(res.refresh_token);
    setTokenState(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    const refreshToken = getRefreshToken();
    setToken(null);
    setRefreshToken(null);
    setTokenState(null);
    setUser(null);
    if (refreshToken) {
      // Best-effort server-side revocation — local state is already
      // cleared either way, so a failed request here isn't worth
      // surfacing to the user.
      authApi.logout(refreshToken).catch(() => {});
    }
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
