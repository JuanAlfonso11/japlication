import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_UNAUTHORIZED_EVENT,
  authApi,
  resumeApi,
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

describe("downloadFile()", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  /**
   * This is a regression test for a bug that produced no error anywhere: the
   * button appeared to work, no exception was thrown, the backend logged
   * nothing, and no file arrived. Both halves of it are silent, so both are
   * pinned here.
   */
  it("does not revoke the blob URL in the same tick as the click", async () => {
    vi.useFakeTimers();
    window.localStorage.clear();
    setToken("token");

    // Hand-rolled instead of `new Response(blob)`: jsdom's Blob has no
    // .stream(), which the Response constructor calls.
    const pdfResponse = {
      ok: true,
      status: 200,
      blob: async () => new Blob(["%PDF-1.4"], { type: "application/pdf" }),
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(pdfResponse));

    const revoke = vi.fn();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:fake"),
      revokeObjectURL: revoke,
    });

    const clicked: string[] = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === "a") {
        // click() on a detached anchor is a no-op in jsdom; record instead.
        (el as HTMLAnchorElement).click = () => clicked.push((el as HTMLAnchorElement).download);
      }
      return el;
    });

    await resumeApi.downloadPdf("resume-id", "cv.pdf");

    expect(clicked).toEqual(["cv.pdf"]);
    // The whole bug: revoking here can abort a download that click() has
    // only scheduled, which is why the failure looked intermittent.
    expect(revoke).not.toHaveBeenCalled();

    vi.advanceTimersByTime(60_000);
    expect(revoke).toHaveBeenCalledWith("blob:fake");
  });

  it("throws a real error when the server rejects the request", async () => {
    window.localStorage.clear();
    setToken("token");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));

    await expect(resumeApi.downloadPdf("missing", "cv.pdf")).rejects.toThrow();
  });
});
