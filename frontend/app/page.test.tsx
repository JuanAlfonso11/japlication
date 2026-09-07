import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/context/AuthContext";
import { setToken } from "@/lib/api";
import type { Job } from "@/lib/types";
import HomePage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

// The real SwipeCard only calls onDecide once its framer-motion exit
// animation finishes — irrelevant to what this suite cares about (the
// decide() handler's own logic), and animation completion isn't reliably
// simulated in jsdom. Stand in a plain button that calls onDecide directly,
// so the test exercises the *real* decide() from app/page.tsx.
vi.mock("@/components/SwipeCard", () => ({
  default: ({ job, onDecide, isTop }: { job: Job; onDecide: (d: "left" | "right") => void; isTop: boolean }) =>
    isTop ? (
      <div>
        <span>{job.title}</span>
        <button onClick={() => onDecide("right")}>mock-save</button>
        <button onClick={() => onDecide("left")}>mock-pass</button>
      </div>
    ) : null,
}));

const { me, matches, listApplications, decide } = vi.hoisted(() => ({
  me: vi.fn(),
  matches: vi.fn(),
  listApplications: vi.fn(),
  decide: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authApi: { ...actual.authApi, me },
    jobsApi: { ...actual.jobsApi, matches, decide },
    applicationsApi: { ...actual.applicationsApi, list: listApplications },
  };
});

function job(id: string, title: string): Job {
  return {
    id,
    title,
    company: "Acme",
    location: "Remote",
    skills_required: [],
    requirements: [],
  } as unknown as Job;
}

function renderHome() {
  return render(
    <AuthProvider>
      <HomePage />
    </AuthProvider>
  );
}

describe("Home swipe/decision flow", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setToken("fake-access-token");
    me.mockResolvedValue({ id: "u1", email: "user@example.com", full_name: "Test User", email_verified: true });
    // Same shape the real endpoint returns — Home reads `.items` off this,
    // so a bare array silently left the stats row unrendered.
    listApplications.mockResolvedValue({ items: [], total: 0 });
    decide.mockReset();
  });

  it("removes the current job from the queue after a successful decision", async () => {
    matches.mockResolvedValue({ items: [job("a", "Backend Engineer"), job("b", "Frontend Engineer")], total: 2 });
    decide.mockResolvedValue({ id: "app1", status: "applied" });

    renderHome();

    await waitFor(() => expect(screen.getByText("Backend Engineer")).toBeInTheDocument());
    await userEvent.click(screen.getByText("mock-save"));

    await waitFor(() => expect(screen.getByText("Frontend Engineer")).toBeInTheDocument());
    expect(decide).toHaveBeenCalledWith("a", { decision: "right" });
    // Scoped to the card (the mock above renders the title in a <span>):
    // the decided job is deliberately still named in the "saved to your
    // pipeline" confirmation below the deck, so an unscoped query here
    // matches that banner and fails even though the queue advanced.
    expect(screen.queryByText("Backend Engineer", { selector: "span" })).not.toBeInTheDocument();
  });

  it("keeps the job in the queue and shows an error when the decision fails to save", async () => {
    matches.mockResolvedValue({ items: [job("a", "Backend Engineer")], total: 1 });
    decide.mockRejectedValue(new Error("boom"));

    renderHome();

    await waitFor(() => expect(screen.getByText("mock-pass")).toBeInTheDocument());
    await userEvent.click(screen.getByText("mock-pass"));

    await waitFor(() =>
      expect(
        screen.getByText("No se pudo registrar tu decisión. Intenta de nuevo.")
      ).toBeInTheDocument()
    );
    // The failed decision must NOT remove the job — otherwise a flaky
    // network error would silently drop it from the user's queue.
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
  });

  it("shows the empty state once every job has been decided on", async () => {
    matches.mockResolvedValue({ items: [job("a", "Only Job")], total: 1 });
    decide.mockResolvedValue({ id: "app1", status: "applied" });

    renderHome();
    await waitFor(() => expect(screen.getByText("mock-save")).toBeInTheDocument());
    await userEvent.click(screen.getByText("mock-save"));

    await waitFor(() => expect(screen.getByText(/ya estás al día/i)).toBeInTheDocument());
  });
});
