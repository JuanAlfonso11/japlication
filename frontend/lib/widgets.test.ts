import { describe, expect, it } from "vitest";
import type { Job } from "./types";
import {
  buildWidgetPayload,
  countPipeline,
  describePlace,
  parseSwipeIntent,
  toWidgetJob,
} from "./widgets";

const JOB = {
  id: "5c347b19-9944-4dcd-aadb-7a85910a1536",
  title: "  Backend   Engineer ",
  company: "Enveritas",
  location: "Santiago",
  remote_type: "hybrid",
  description: "",
  requirements: [],
  skills_required: [],
  match: {
    overall_score: 81.6,
    technical_score: null,
    experience_score: null,
    semantic_score: null,
    matched_skills: [],
    missing_skills: [],
    concerns: [],
  },
} as Job;

describe("describePlace", () => {
  it("pone la modalidad delante de la ciudad", () => {
    expect(describePlace({ location: "Santiago", remote_type: "hybrid" })).toBe("Híbrido · Santiago");
  });
  it("no repite 'remoto' cuando la ubicación ya lo dice", () => {
    expect(describePlace({ location: "Remote - Worldwide", remote_type: "remote" })).toBe("Remoto");
    expect(describePlace({ location: "Canada", remote_type: "remote" })).toBe("Remoto · Canada");
  });
  it("sin modalidad usa la ubicación tal cual", () => {
    expect(describePlace({ location: "Madrid", remote_type: null })).toBe("Madrid");
  });
});

describe("toWidgetJob", () => {
  it("limpia el texto y redondea el match", () => {
    expect(toWidgetJob(JOB)).toEqual({
      id: JOB.id,
      title: "Backend Engineer",
      company: "Enveritas",
      place: "Híbrido · Santiago",
      score: 82,
    });
  });
  it("sin match calculado el score es null, no 0", () => {
    expect(toWidgetJob({ ...JOB, match: null }).score).toBeNull();
  });
  it("recorta títulos enormes", () => {
    expect(toWidgetJob({ ...JOB, title: "x".repeat(500) }).title.length).toBe(140);
  });
});

describe("countPipeline", () => {
  it("cuenta solo aplicadas, entrevistas y ofertas", () => {
    const apps = ["applied", "applied", "interviewing", "offer", "saved", "passed"].map((status) => ({ status }));
    expect(countPipeline(apps as never)).toEqual({ applied: 2, interviewing: 1, offer: 1 });
  });
});

describe("buildWidgetPayload", () => {
  it("arma la foto completa", () => {
    const payload = buildWidgetPayload({
      queueCount: 12.7,
      next: JOB,
      pipeline: { applied: 5, interviewing: 2, offer: 0 },
      now: 1_700_000_000_000,
    });
    expect(payload).toMatchObject({ v: 1, updatedAt: 1_700_000_000_000, queueCount: 12 });
    expect(payload.next?.id).toBe(JOB.id);
    expect(payload.upcoming).toEqual([]);
  });
  it("lleva hasta cinco tarjetas de reserva para avanzar sin red", () => {
    const more = Array.from({ length: 8 }, (_, i) => ({ ...JOB, id: `job-${i}`, title: `Job ${i}` }));
    const payload = buildWidgetPayload({
      queueCount: 9,
      next: JOB,
      upcoming: more,
      pipeline: { applied: 0, interviewing: 0, offer: 0 },
    });
    expect(payload.upcoming.map((j) => j.id)).toEqual(["job-0", "job-1", "job-2", "job-3", "job-4"]);
  });
  it("cola vacía: sin próxima vacante ni reserva", () => {
    const payload = buildWidgetPayload({
      queueCount: 0,
      next: null,
      upcoming: [JOB],
      pipeline: { applied: 0, interviewing: 0, offer: 0 },
    });
    expect(payload.next).toBeNull();
    expect(payload.upcoming).toEqual([]);
  });
});

describe("parseSwipeIntent", () => {
  it("lee el swipe que pide el widget", () => {
    expect(parseSwipeIntent(`?swipe=right&job=${JOB.id}`)).toEqual({ decision: "right", jobId: JOB.id });
    expect(parseSwipeIntent(`?swipe=left&job=${JOB.id}`)).toEqual({ decision: "left", jobId: JOB.id });
  });
  it("ignora cualquier otra cosa", () => {
    expect(parseSwipeIntent("")).toBeNull();
    expect(parseSwipeIntent(`?swipe=up&job=${JOB.id}`)).toBeNull();
    expect(parseSwipeIntent("?swipe=right")).toBeNull();
    expect(parseSwipeIntent("?swipe=right&job=<script>")).toBeNull();
  });
});
