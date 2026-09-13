export type Page = "home" | "music" | "video";
export type Sampling = {
  temperature: number;
  top_p: number;
  top_k: number;
  repetition_penalty: number;
  penalty_window: number;
  min_tokens: number;
  max_tokens: number;
};
export type SongForm = {
  description: string;
  title: string;
  lyrics: string;
  style: string;
  count: 1 | 2;
  project: string;
  cot: "full" | "melody" | "off";
  abc: string;
  seed: string;
  cfg_scale: string;
  planFirst: boolean;
  ode_steps: number;
  semantic: Sampling;
  score: Sampling;
  genre?: string;
  referenceId?: string;
  sourceTakeId?: string;
  writingTask: string;
  writingPrompt: string;
};
export type Track = {
  id: string;
  title: string;
  subtitle: string;
  project: string;
  cover?: string;
  audio?: 1 | 2;
  audioUrl?: string | null;
  source?: "yue2" | "imported";
  duration?: number;
  status?:
    | "queued"
    | "waiting-for-resource"
    | "running"
    | "needs-review"
    | "succeeded"
    | "failed"
    | "cancelled";
  stage?: string;
  elapsed?: number;
  attempt?: number;
  error?: string | null;
  warnings?: string[];
  sampleRate?: number | null;
  delivery?: Record<string, unknown> | null;
  favorite: boolean;
  created: number;
  deletedAt?: number | null;
  form?: SongForm;
  requestId?: string;
  take?: number;
  coverStatus?: "reference" | "requested" | "unavailable" | "ready";
};
export const initialForm: SongForm = {
  description: "",
  title: "",
  lyrics: "",
  style: "",
  count: 2,
  project: "Loose tracks",
  cot: "full",
  abc: "",
  seed: "",
  cfg_scale: "",
  planFirst: false,
  ode_steps: 32,
  semantic: {
    temperature: 1,
    top_p: 0.95,
    top_k: 100,
    repetition_penalty: 1.2,
    penalty_window: 50,
    min_tokens: 200,
    max_tokens: 9000,
  },
  score: {
    temperature: 0.7,
    top_p: 0.9,
    top_k: 30,
    repetition_penalty: 1.005,
    penalty_window: 100,
    min_tokens: 32,
    max_tokens: 4096,
  },
  writingTask: "Draft lyrics",
  writingPrompt: "",
};
export const initialTracks: Track[] = [
  {
    id: "amber",
    title: "Desert Afterglow",
    subtitle: "Amber take · Indie electronic",
    project: "Desert Afterglow",
    cover: "/covers/amber.png",
    audio: 1,
    favorite: true,
    created: 4,
  },
  {
    id: "dusk",
    title: "Desert Afterglow",
    subtitle: "Dusk take · Ambient electronic",
    project: "Desert Afterglow",
    cover: "/covers/dusk.png",
    audio: 2,
    favorite: false,
    created: 3,
  },
  {
    id: "soft-focus",
    title: "Soft Focus",
    subtitle: "Alternative folk · Warm & intimate",
    project: "Quiet hours",
    cover: "/covers/soft-focus.png",
    favorite: false,
    created: 2,
    coverStatus: "reference",
    form: {
      ...initialForm,
      title: "Soft Focus",
      description:
        "An intimate folk song with felt piano, fingerpicked guitar and a close, soft vocal.",
      project: "Quiet hours",
    },
  },
  {
    id: "low-tide",
    title: "Low Tide",
    subtitle: "Dream pop · Slow & spacious",
    project: "Quiet hours",
    cover: "/covers/low-tide.png",
    favorite: false,
    created: 1,
    coverStatus: "reference",
    form: {
      ...initialForm,
      title: "Low Tide",
      description:
        "Slow dream pop, sea-glass guitars, a low warm bass and a distant vocal. A quiet morning by the sea.",
      project: "Quiet hours",
    },
  },
];
export const projects = ["Loose tracks", "Desert Afterglow", "Quiet hours"];
export function readLocal<T>(key: string, fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}
export function writeLocal(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export function validate(form: SongForm): string | null {
  if (!form.description.trim() && !form.style.trim())
    return "Add a song description or style first.";
  if (form.seed && (!/^\d+$/.test(form.seed) || BigInt(form.seed) >= 2n ** 63n))
    return "Use a seed between 0 and 9223372036854775807.";
  if (
    form.cfg_scale !== "" &&
    (!Number.isFinite(Number(form.cfg_scale)) ||
      +form.cfg_scale < 0 ||
      +form.cfg_scale > 20)
  )
    return "Guidance must be between 0 and 20.";
  if (!Number.isInteger(form.ode_steps) || form.ode_steps < 1)
    return "Synthesis steps must be a positive integer.";
  for (const sampling of [form.semantic, form.score]) {
    if (Object.values(sampling).some((v) => !Number.isFinite(v)))
      return "Complete the sampling values.";
    if (
      sampling.temperature < 0 ||
      sampling.temperature > 5 ||
      sampling.top_p <= 0 ||
      sampling.top_p > 1 ||
      sampling.repetition_penalty <= 0
    )
      return "Check temperature, top-p and repetition penalty.";
    if (
      !Number.isInteger(sampling.top_k) ||
      sampling.top_k < 1 ||
      !Number.isInteger(sampling.penalty_window) ||
      sampling.penalty_window < 1 ||
      sampling.penalty_window > 100
    )
      return "Top-k must be a positive integer; penalty window must be 1–100.";
    if (
      !Number.isInteger(sampling.min_tokens) ||
      !Number.isInteger(sampling.max_tokens) ||
      sampling.min_tokens < 0 ||
      sampling.max_tokens < 1 ||
      sampling.min_tokens > sampling.max_tokens
    )
      return "Token limits must be whole numbers, with minimum no greater than maximum.";
  }
  return null;
}
// UI contract only. The server must validate again and resolve account capability.
export function generationRequest(form: SongForm, requestId: string) {
  return {
    id: requestId,
    project: form.project,
    genre: form.genre || null,
    referenceId: form.referenceId || null,
    sourceTakeId: form.sourceTakeId || null,
    title: form.title,
    status: "draft",
    description: form.description,
    preparation: {
      lyrics: form.lyrics.trim() ? "provided" : "needs-writing",
      writingTask: form.writingTask,
      writingPrompt: form.writingPrompt,
      planFirst: form.cot !== "off" && form.planFirst,
    },
    takes: Array.from({ length: form.count }, (_, i) => ({
      index: i + 1,
      song: {
        id: `${requestId}-${i + 1}`,
        style: form.style.trim() || form.description.trim(),
        lyrics: form.lyrics,
        cot: form.cot,
        ...(form.cot !== "off" && form.abc.trim() ? { abc: form.abc } : {}),
        // Strings preserve the full 63-bit seed in JSON; the YuE adapter must parse to integer.
        seed: form.seed
          ? String((BigInt(form.seed) + BigInt(i)) % 2n ** 63n)
          : null,
        cfg_scale: form.cfg_scale === "" ? null : Number(form.cfg_scale),
      },
      generation: {
        abc: form.score,
        semantic: form.semantic,
        ode_steps: form.ode_steps,
      },
      cover: {
        provider: "configured",
        model: "selected-in-ai-setup",
        status: "requested",
        count: 1,
        prompt: `${form.title || "Untitled"}. ${form.description || form.style}. Lyrics context: ${form.lyrics.slice(0, 600)}. Distinct cover for take ${i + 1}. No text.`,
      },
    })),
  };
}
