import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Fresh module per test: the dedupe set and the pending report are module state.
async function load() {
  vi.resetModules();
  return import("@/lib/errorReporting");
}

describe("errorReporting", () => {
  const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));

  beforeEach(() => {
    window.localStorage.setItem("jobflow_token", "t");
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("holds the error for the prompt and sends nothing until the user agrees", async () => {
    const r = await load();
    r.captureClientError(new Error("boom"));
    expect(r.getPendingReport()?.message).toBe("boom");
    expect(fetchMock).not.toHaveBeenCalled();

    r.dismissPendingReport();
    expect(r.getPendingReport()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the user's note on top of the error", async () => {
    const r = await load();
    r.captureClientError(new Error("boom"));
    await r.sendPendingReport("  tocaba Guardar ");
    const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
    expect(body.message).toBe("Comentario del usuario: tocaba Guardar\n\nboom");
    expect(r.getPendingReport()).toBeNull();
  });

  it("does not prompt twice for the same error, nor without a session", async () => {
    const r = await load();
    r.captureClientError(new Error("boom"));
    r.dismissPendingReport();
    r.captureClientError(new Error("boom"));
    expect(r.getPendingReport()).toBeNull();

    window.localStorage.clear();
    r.captureClientError(new Error("otro"));
    expect(r.getPendingReport()).toBeNull();
  });
});
