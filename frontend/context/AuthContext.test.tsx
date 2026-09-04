import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import { setRefreshToken, setToken } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Renders the token/user state so tests can assert on it without reaching
 * into AuthProvider internals. */
function Probe() {
  const { token, user, isLoading } = useAuth();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      <div data-testid="token">{token ?? "null"}</div>
      <div data-testid="user">{user?.email ?? "null"}</div>
    </div>
  );
}

describe("AuthProvider — saved-session handling on mount", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps a saved session when /auth/me fails with a network error", async () => {
    setToken("saved-access-token");
    setRefreshToken("saved-refresh-token");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("token")).toBeInTheDocument());

    // This is the exact regression this test guards against: a network
    // hiccup on startup must NOT look like an expired session.
    expect(screen.getByTestId("token")).toHaveTextContent("saved-access-token");
    expect(screen.getByTestId("user")).toHaveTextContent("null");
  });

  it("clears the session when the token is genuinely invalid (401, refresh also fails)", async () => {
    setToken("stale-access-token");
    setRefreshToken("stale-refresh-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" })) // /auth/me
      .mockResolvedValueOnce(jsonResponse(401, { detail: "invalid" })); // /auth/refresh
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("null"));
    expect(screen.getByTestId("user")).toHaveTextContent("null");
  });

  it("picks up the user once /auth/me succeeds", async () => {
    setToken("saved-access-token");
    setRefreshToken("saved-refresh-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(200, { email: "user@example.com" }))
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("user@example.com"));
  });
});
