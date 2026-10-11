import { create } from "zustand";
import { api } from "../lib/api";
import type { InfluenceRun, Job } from "../lib/types";

/** Influence Engine runs and their jobs, kept live by the window's event line. */
interface RunsState {
  runs: Record<string, InfluenceRun>;
  jobs: Record<string, Job>;
  loaded: boolean;
  load: () => Promise<void>;
  onRun: (r: InfluenceRun) => void;
  onJob: (j: Job) => void;
}

export const useRuns = create<RunsState>((set) => ({
  runs: {},
  jobs: {},
  loaded: false,

  async load() {
    const [runs, jobs] = await Promise.all([api.get<InfluenceRun[]>("/api/influence-runs"), api.get<Job[]>("/api/jobs")]);
    set({
      runs: Object.fromEntries(runs.map((r) => [r.id, r])),
      jobs: Object.fromEntries(jobs.filter((j) => j.kind.startsWith("influence.")).map((j) => [j.id, j])),
      loaded: true,
    });
  },

  onRun(r) {
    set((s) => {
      const runs = { ...s.runs };
      if (r.deleted) delete runs[r.id];
      else runs[r.id] = r;
      return { runs };
    });
  },

  onJob(j) {
    if (j.kind.startsWith("influence.")) set((s) => ({ jobs: { ...s.jobs, [j.id]: j } }));
  },
}));
