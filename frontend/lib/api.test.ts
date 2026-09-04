import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_UNAUTHORIZED_EVENT,
  authApi,
  getRefreshToken,
  getToken,
  setRefreshToken,
  setToken,
} from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("request() transparent access-token refresh", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setToken("old-access-token");
    setRefreshToken("valid-refresh-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("retries the original request once with a refreshed token after a 401", async () => {
    const fetchMock = vi
      .fn()
      // 1) original request — expired access token
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      // 2) POST /auth/refresh — succeeds
      .mockResolvedValueOnce(
        jsonResponse(200, { access_token: "new-access-token", refresh_token: "new-refresh-token" })
      )
      // 3) original request retried — succeeds this time
      .mockResolvedValueOnce(jsonResponse(200, { email: "user@example.com" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await authApi.me();

    expect(result).toEqual({ email: "user@example.com" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    // The retried request must carry the new token, not the stale one.
    const retriedHeaders = fetchMock.mock.calls[2][1].headers as Record<string, string>;
    expect(retriedHeaders.Authorization).toBe("Bearer new-access-token");
    // The refreshed pair is persisted for subsequent requests.
    expect(getToken()).toBe("new-access-token");
    expect(getRefreshToken()).toBe("new-refresh-token");
  });

  it("clears stored tokens and fires AUTH_UNAUTHORIZED_EVENT when the refresh token is also invalid", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "refresh token invalid" }));
    vi.stubGlobal("fetch", fetchMock);

    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);

    await expect(authApi.me()).rejects.toMatchObject({ status: 401 });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(getToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();

    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });

  it("does not attempt a refresh for a network error (no response at all)", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("network down"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(authApi.me()).rejects.toMatchObject({ status: 0 });

    // Only the one failed attempt — no refresh call, and the still-valid
    // saved session is left untouched (this is the exact bug the session-
    // persistence fix was about: a network error must never look like an
    // invalid session).
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getToken()).toBe("old-access-token");
    expect(getRefreshToken()).toBe("valid-refresh-token");
  });

  it("coalesces concurrent 401s into a single refresh call", async () => {
    let refreshCalls = 0;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.includes("/auth/refresh")) {
        refreshCalls += 1;
        return Promise.resolve(
          jsonResponse(200, { access_token: "new-access-token", refresh_token: "new-refresh-token" })
        );
      }
      // Every plain request "expires" on the stale token, succeeds once
      // retried with the refreshed one.
      const headers = init?.headers as Record<string, string> | undefined;
      if (headers?.Authorization === "Bearer old-access-token") {
        return Promise.resolve(jsonResponse(401, { detail: "expired" }));
      }
      return Promise.resolve(jsonResponse(200, { ok: true }));
    });
    vi.stubGlobal("fetch", fetchMock);

    const [a, b] = await Promise.all([authApi.me(), authApi.resendVerification()]);

    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(refreshCalls).toBe(1);
  });
});
