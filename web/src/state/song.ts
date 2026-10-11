import { create } from "zustand";
import { api, ApiError } from "../lib/api";
import type { Influence, Job, LyricSection, Project, SongDoc, Take } from "../lib/types";

export const NEW_SONG: SongDoc = {
  idea: "",
  sung: true,
  sections: [],
  voice: null,
  genres: [],
  moods: [],
  instruments: "",
  extra: "",
  length: "song",
  influences: [],
  plan: "full",
  creativity: 1.0,
  repetition: 1.2,
  tempo: null,
  key: null,
  language: "English",
  takes: 2,
  seed: null,
  styleOverride: null,
  engine: {},
  soundNotes: "",
  model: "yue2",
  timeSignature: null,
  music3Guidance: null,
  covering: null,
  mcpOptions: {},
};

let uid = 0;
export const sectionId = () => `s${Date.now().toString(36)}${(uid++).toString(36)}`;

/** The lyric sheet as YuE2 reads it: "[Verse]\nline\n…", a blank line between sections. */
export function lyricsText(sections: LyricSection[]): string {
  return sections
    .map((s) => `[${label(s.kind)}]\n${s.text.split("\n").map((l) => l.trim()).filter(Boolean).join("\n")}`)
    .join("\n\n");
}

export function label(kind: string): string {
  return kind === "pre-chorus" ? "Pre-Chorus" : kind === "post-chorus" ? "Post-Chorus" : kind[0].toUpperCase() + kind.slice(1);
}

/** Parse pasted lyrics ("[Chorus]" tags, or plain stanzas) into sections. */
export function parseLyrics(text: string): LyricSection[] {
  const out: LyricSection[] = [];
  const kinds: Record<string, LyricSection["kind"]> = {
    intro: "intro", verse: "verse", "pre-chorus": "pre-chorus", prechorus: "pre-chorus", chorus: "chorus", refrain: "chorus",
    "post-chorus": "post-chorus", bridge: "bridge", hook: "hook", instrumental: "instrumental", interlude: "instrumental",
    outro: "outro",
  };
  let cur: LyricSection | null = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const tag = line.match(/^\[([^\]]+)\]$/) ?? line.match(/^(verse|chorus|bridge|intro|outro|pre-?chorus|hook)\s*\d*:?$/i);
    if (tag) {
      const k = tag[1].toLowerCase().replace(/\s*\d+\s*$/, "").replace(/\s+/g, "-");
      cur = { id: sectionId(), kind: kinds[k] ?? "verse", text: "" };
      out.push(cur);
    } else if (line) {
      if (!cur) {
        cur = { id: sectionId(), kind: "verse", text: "" };
        out.push(cur);
      }
      cur.text += (cur.text ? "\n" : "") + line;
    } else if (cur && cur.text) {
      cur = null; // a blank line ends an untagged stanza
    }
  }
  return out;
}

type DocKey = keyof SongDoc;

interface SongState {
  project: Project | null;
  doc: SongDoc;
  takes: Take[];
  jobs: Record<string, Job>;
  library: Influence[];
  saving: "idle" | "pending" | "saving" | "error";
  error: string | null;
  load: (id: string) => Promise<void>;
  refreshLibrary: () => Promise<Influence[]>;
  resync: () => Promise<void>;
  set: <K extends DocKey>(key: K, value: SongDoc[K]) => void;
  setTitle: (title: string) => void;
  saveNow: () => Promise<void>;
  onTake: (t: Take & { trashed?: boolean }) => void;
  onJob: (j: Job) => void;
  onProject: (p: Project) => void;
}

let timer: number | undefined;
const pending = new Set<string>();

function docOf(p: Project): SongDoc {
  const d: Record<string, unknown> = { ...NEW_SONG };
  const src = p as unknown as Record<string, unknown>;
  for (const k of Object.keys(NEW_SONG)) if (src[k] !== undefined) d[k] = src[k];
  d.masterTake = p.masterTake ?? null;
  return d as unknown as SongDoc;
}

export const useSong = create<SongState>((set, get) => ({
  project: null,
  doc: NEW_SONG,
  takes: [],
  jobs: {},
  library: [],
  saving: "idle",
  error: null,

  async load(id) {
    if (pending.size) await get().saveNow();  // an edit made just before leaving the song still lands
    set({ project: null, takes: [], error: null });
    try {
      const [p, takes, jobs, library] = await Promise.all([
        api.get<Project>(`/api/projects/${id}`),
        api.get<Take[]>(`/api/projects/${id}/takes`),
        api.get<Job[]>(`/api/jobs?project=${id}`),
        api.get<Influence[]>(`/api/influences?model=yue2`),
      ]);
      pending.clear();
      set({ project: p, doc: docOf(p), takes, jobs: Object.fromEntries(jobs.map((j) => [j.id, j])), library, saving: "idle" });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  async resync() {
    // after the live line was down: re-read the open song's takes and jobs (and the project, unless this window has unsaved edits)
    const p = get().project;
    if (!p) return;
    try {
      const [takes, jobs, fresh] = await Promise.all([
        api.get<Take[]>(`/api/projects/${p.id}/takes`),
        api.get<Job[]>(`/api/jobs?project=${p.id}`),
        api.get<Project>(`/api/projects/${p.id}`),
      ]);
      set((s) => ({ takes, jobs: { ...s.jobs, ...Object.fromEntries(jobs.map((j) => [j.id, j])) } }));
      get().onProject(fresh);
      if (pending.size) void get().saveNow();
    } catch {
      /* still down; the next reconnect tries again */
    }
  },

  async refreshLibrary() {
    const library = await api.get<Influence[]>(`/api/influences?model=yue2`);
    set({ library });
    return library;
  },

  set(key, value) {
    set((s) => ({ doc: { ...s.doc, [key]: value }, saving: "pending" }));
    pending.add(key);
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void get().saveNow(), 700);
  },

  setTitle(title) {
    const p = get().project;
    if (!p) return;
    set({ project: { ...p, title }, saving: "pending" });
    pending.add("title");
    window.clearTimeout(timer);
    timer = window.setTimeout(() => void get().saveNow(), 700);
  },

  async saveNow() {
    window.clearTimeout(timer);
    const { project, doc } = get();
    if (!project || pending.size === 0) return;
    set({ saving: "saving" });
    const sent = new Set(pending);
    pending.clear();
    try {
      const saved = await api.put<Project>(`/api/projects/${project.id}`, { title: project.title, doc, rev: project.rev });
      set((s) => ({ project: { ...saved, title: s.project?.title ?? saved.title }, saving: pending.size ? "pending" : "idle" }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Someone (another window, or the server choosing the master take) saved first: keep their
        // version and lay this window's own changes on top, then save again.
        const theirs = (e.body as { project: Project }).project;
        const merged = { ...docOf(theirs) } as Record<string, unknown>;
        for (const k of sent) if (k !== "title") merged[k] = (doc as unknown as Record<string, unknown>)[k];
        sent.forEach((k) => pending.add(k));
        set({ project: { ...theirs, title: sent.has("title") ? project.title : theirs.title }, doc: merged as unknown as SongDoc });
        await get().saveNow();
        return;
      }
      sent.forEach((k) => pending.add(k));
      set({ saving: "error", error: e instanceof Error ? e.message : String(e) });
    }
  },

  onTake(t) {
    const p = get().project;
    if (!p || t.projectId !== p.id) return;
    set((s) => {
      if (t.trashed) return { takes: s.takes.filter((x) => x.id !== t.id) };
      const has = s.takes.some((x) => x.id === t.id);
      const takes = has ? s.takes.map((x) => (x.id === t.id ? t : x)) : [t, ...s.takes];
      return { takes: takes.sort((a, b) => b.n - a.n) };
    });
  },

  onJob(j) {
    set((s) => ({ jobs: { ...s.jobs, [j.id]: j } }));
  },

  onProject(p) {
    const cur = get().project;
    if (!cur || p.id !== cur.id || pending.size) return;
    if (p.rev > cur.rev) set({ project: p, doc: docOf(p) });
  },
}));
