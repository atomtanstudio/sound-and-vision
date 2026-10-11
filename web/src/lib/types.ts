/** The shapes the server sends (sv/store.py, sv/music, sv/analysis.py). */

export type SectionKind =
  | "intro"
  | "verse"
  | "pre-chorus"
  | "chorus"
  | "post-chorus"
  | "bridge"
  | "hook"
  | "instrumental"
  | "outro";

export interface LyricSection {
  id: string;
  kind: SectionKind;
  /** The sung lines, one per line of text. */
  text: string;
}

export interface InfluencePick {
  id: string;
  strength: number;
}

export interface SongDoc {
  idea: string;
  sung: boolean;
  sections: LyricSection[];
  voice: "female" | "male" | "duet" | null;
  genres: string[];
  moods: string[];
  instruments: string;
  extra: string;
  length: "short" | "song" | "long";
  influences: InfluencePick[];
  plan: "full" | "melody" | "free";
  creativity: number;
  repetition: number;
  tempo: number | null;
  key: string | null;
  language: string;
  takes: number;
  seed: number | null;
  styleOverride: string | null;
  engine: Record<string, number | null>;
  masterTake?: string | null;
  /** A pasted description of the sound this song matches (kept for reference). */
  soundNotes?: string;
  /** Who sings it: YuE2 (the default), ACE-Step 1.5, MiniMax Music 3, or a song model on an MCP server
   *  ("mcp:<id>:music": ElevenLabs Music). */
  model: SongModel;
  /** That MCP song model's own settings, as the song page offers them (its audio quality, …). */
  mcpOptions?: Record<string, string | number | boolean>;
  /** ACE-Step 1.5's time signature (beats in a bar). */
  timeSignature: "2" | "3" | "4" | "6" | null;
  /** MiniMax Music 3's guidance. */
  music3Guidance: number | null;
  /** YuE2 covering a song (the song's `reference`): what of it to keep. Null: YuE2 writes its own tune. */
  covering: { keep: "melody" | "full" } | null;
}

export type SongModel = "yue2" | "ace15" | "music3" | `mcp:${string}`;

/** A song model on one of the person's MCP servers (GET /api/song-models), with the settings it takes. */
export interface McpSongModel {
  id: `mcp:${string}`;
  name: string; // "ElevenLabs Music"
  via: string; // the server: "Mitte"
  paid: boolean; // asked before each take
  paidOnly?: boolean;
  note: string;
  maxSeconds: number;
  fields: McpField[];
}
export interface McpField {
  key: string;
  label: string;
  help: string;
  type: "choice" | "switch" | "number";
  default: string | number | boolean | null;
  values?: (string | number)[];
  labels?: Record<string, string>; // the values in plain words
  min?: number;
  max?: number;
  integer?: boolean;
}

/** The song's sleeve: the picture made for it and the finished cover set from it (title, artist, logos). */
export interface CoverPick {
  n: number;
  art: string;
  prompt?: string;
  made?: { engine: string; model: string; moving?: boolean };
  by?: { provider: string; concept?: string };
  at?: number;
}

export interface Cover {
  n: number;
  rev: number;
  art: string;
  file: string;
  small: string;
  title: string;
  artist: string;
  prompt: string;
  by?: { provider: string; model?: string | null; concept?: string };
  /** engine: "openai", "local", "upload", an MCP server ("mcp:<id>"), or the owner's own where it's on */
  made: { engine: string; model: string; cost?: number; moving?: boolean };
  at: number;
}

/** Living Album Cover: 1-4 subtle loops of the cover that take turns through the song, under a fixed title. */
export interface LivingLoop {
  id: string;
  motion: string;
  status: "new" | "queued" | "making" | "ready";
  video?: string;
  rev?: number;
  cover?: number;
  seconds?: number;
  verdict?: "calm" | "lively" | "too much" | "cuts";
  changed?: number;
  held?: boolean;
  tries?: { seed: number; piece: number; motion: string; changed: number; cuts: number; held: number | null }[];
  madeWith?: string;
  madeFeel?: string;
  madeSeconds?: number;
  madeHold?: boolean;
  /** "forward": made forward-only and closed by blending (unset: the old way, pinned at both ends). */
  way?: "forward";
  /** False: H3 cut away to a different shot in every try, so the loop is left out of the video (unusable says why). */
  usable?: boolean;
  unusable?: string | null;
  error?: string | null;
  edited?: boolean;
  jobId?: string;
}

export interface LivingRender {
  id: string;
  file: string;
  shape: "square" | "story" | "wide";
  seconds: number;
  bytes: number;
  stretches: number;
  transition?: string;
  cover?: number;
  made?: Record<string, number>;
  /** Made by Claude's finish in code (its id); kept beside the plain video of the same shape. */
  finish?: string;
  poster?: string | null;
  at: number;
}

export type Feel = "still" | "subtle" | "gentle";
export type Transition = "seamless" | "dissolve" | "slow" | "dark";

/** "Let Claude make it": what Claude decided and how far the making has got. */
export interface LivingAuto {
  status: "deciding" | "painting" | "writing" | "animating" | "finishing" | "done" | "failed" | "stopped";
  jobId?: string;
  coverJob?: string;
  note?: string;
  idea?: string;
  why?: string;
  picture?: "keep" | "new";
  brief?: string;
  /** The picture's prompt, written by Claude as art director. */
  prompt?: string;
  /** What Claude's finish in code should add (empty: none). */
  finish?: string;
  finishJob?: string;
  finished?: { id: string; about: string; seconds: number; leftOut?: Record<string, string> } | null;
  finishError?: string | null;
  choices?: { count: number; feel: Feel; seconds: number; transition: Transition };
  render?: string;
  /** You kept the video Claude made. */
  kept?: boolean;
  error?: string | null;
  /** The step that stopped, to carry on from: the picture, the motion, or deciding. */
  failedAt?: "paint" | "motion" | "decide" | null;
  at: number;
}

export interface Living {
  settings: { count: number; seconds: number; feel: Feel; keepPeople: boolean; transition: Transition; shape: LivingRender["shape"] };
  loops: LivingLoop[];
  renders: LivingRender[];
  /** The cover (its number) chosen as the picture to animate. */
  picture?: number;
  steer?: string;
  plan?: { risk: string; at: number } | null;
  /** Claude makes it, or you direct each step. */
  mode?: "auto" | "direct";
  auto?: LivingAuto | null;
}

export interface Project extends Partial<SongDoc> {
  id: string;
  title: string;
  /** The song's own artist, when one was set (blank: none). Without it: its file's, else your artist name (Brand). */
  artist?: string;
  rev: number;
  createdAt: number;
  updatedAt: number;
  cover?: Cover | null;
  covers?: CoverPick[];
  living?: Living | null;
  /** The song this one covers (YuE2): uploaded, or one of your songs. */
  reference?: Reference | null;
  /** Where the song came from, when it wasn't made here (your own uploaded song). */
  source?: { kind: "upload"; file: string; artist?: string; tags?: Record<string, string> } | null;
  /** Its words were heard by Whisper (a draft to check), not typed in. */
  lyricsHeard?: boolean;
  /** Motion Graphics: the film Claude is making (one conversation) and the versions it has finished. */
  kinetic?: { film: KineticFilm | null; videos: KineticVideo[] } | null;
  /** This song's own look for its cover (the title, the artist, the logos), over the house look (Brand). */
  layout?: Partial<import("../look/look").Look> | null;
  /** Your own thumbnails for its videos, by "kind:id". */
  thumbs?: Record<string, { file: string; frame: number; at: number }>;
  /** Music Video: the same kind of record (Claude's conversation and its versions), with pictures and H3 motion. */
  music?: { film: KineticFilm | null; videos: KineticVideo[] } | null;
}

export interface KineticFilm {
  id: string;
  status: "queued" | "preparing" | "running" | "waiting" | "done" | "failed" | "stopped" | "stopping";
  request: string;
  feel: string;
  shape: "wide" | "story" | "square";
  ideaFirst: boolean;
  /** The lyrics on screen (the default request asks for them). */
  lyrics?: boolean;
  /** Music Video: which kind ("surreal" first), and whether Claude stops after the first 30 seconds. */
  kind?: "performance" | "hybrid" | "surreal";
  opening?: boolean;
  model: string;
  effort: string | null;
  session: string | null;
  runs: number;
  jobId?: string;
  message?: string;
  error?: string | null;
  reply?: string;
  concept?: string | null;
  stills?: string[];
  lines?: { text: string; at: number }[];
  notes?: { text: string; go: boolean; at: number }[];
  video?: string;
  /** When the current run (the first, or the one a note started) began. */
  runAt?: number;
  at: number;
}

export interface KineticVideo {
  id: string;
  film: string;
  version: number;
  file: string;
  share: string | null;
  poster: string | null;
  shape: "wide" | "story" | "square";
  seconds: number;
  bytes: number;
  about: string;
  model?: string;
  effort?: string | null;
  /** Only the start of the song (a music video's opening, to see the direction). */
  opening?: boolean;
  /** A chosen part of the song, made on its own (for a trailer or a clip): where in the song it runs. */
  part?: { start: number; end: number; label?: string } | null;
  at: number;
}

export interface Reference {
  id: string;
  file: string;
  name: string;
  seconds: number;
  from: "upload" | "song";
  projectId?: string;
  hasWords?: boolean;
}

export type TakeStatus = "queued" | "sketching" | "singing" | "finishing" | "ready" | "failed" | "stopped";

export interface TimedWord {
  text: string;
  start: number;
  end: number;
  score?: number;
}

export interface TimedLine {
  id: string;
  text: string;
  start: number;
  end: number;
  section: string;
  score?: number;
  words: TimedWord[];
}

export interface Analysis {
  tempo: number | null;
  beats: number[];
  downbeat: number | null;
  sections: { label: string; start: number; end: number }[];
  lines: TimedLine[];
}

export interface Take {
  id: string;
  projectId: string;
  n: number;
  model: string;
  status: TakeStatus;
  seed: number;
  jobId?: string;
  label?: string;
  liked?: boolean;
  duration?: number;
  truncated?: boolean;
  error?: string | null;
  sketch?: string;
  files?: { flac: string; audio: string; peaks: string; sketch?: string };
  sent: {
    style: string;
    lyrics: string;
    plan: string;
    sung: boolean;
    influences: { id: string; name: string; strength: number }[];
    sing?: Record<string, unknown>;
    sketch: Record<string, unknown> | null;
    /** ACE-Step 1.5 and Music 3: the settings sent in their one stage. */
    params?: Record<string, unknown>;
  };
  request: Partial<SongDoc> & Record<string, unknown>;
  analysis?: {
    status: "queued" | "running" | "ready" | "failed" | "cancelled";
    file?: string;
    stems?: Record<string, string>;
    vocalsPeaks?: string | null;
    tempo?: number | null;
    lines?: number;
    error?: string;
  };
  createdAt: number;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  stage?: string;
  message?: string;
  progress?: number;
  projectId?: string;
  takeId?: string;
  createdAt?: number;
}

export interface Influence {
  id: string;
  name: string;
  kind: "Artist" | "Genre" | "Style";
  about: string;
  recommended: number;
  max: number;
  models: string[];
}

export interface ProviderStatus {
  id: string;
  name: string;
  installed: boolean;
  connected: boolean;
  error?: string | null;
  note?: string;
  login?: { url: string; code: string; expiresAt: number } | null;
  /** its models, each with the reasoning levels it takes (when it takes any) */
  models?: { id: string; name: string; default: boolean; efforts?: string[]; defaultEffort?: string | null }[];
  /** signed in from Settings (a device code), and signed out there */
  canSignIn?: boolean;
  account?: string | null;
  plan?: string | null;
}

/** Something that can make pictures (Settings → Pictures): see lib/pictures.ts. */
export type { PictureChoice as ImageProvider } from "./pictures";

/** The Influence Engine: one training run, from research to a kept influence. */
export type RunStatus = "researching" | "planned" | "gathering" | "listening" | "training" | "choosing" | "kept" | "failed" | "stopped";

export interface RunSong {
  id: string;
  artist: string;
  title: string;
  album?: string;
  seconds?: number;
  /** library: found in your music; yours: audio you added to the run; finder: the run's song finder (an add-on)
   *  will get it; needed: no audio yet ("download" and "missing" are from older runs, and mean the same as needed) */
  source: "library" | "yours" | "finder" | "needed" | "download" | "missing";
  use: boolean;
  state: "waiting" | "needed" | "downloading" | "copying" | "ready" | "failed";
  /** the name of the file you added */
  file?: string;
  /** the song it's instead of: one that couldn't be had, swapped for another by the same artist */
  instead?: string;
  note?: string | null;
  asked?: boolean;
  instrumental?: boolean;
}

export interface RunArtist {
  name: string;
  why: string;
  inLibrary: boolean;
}

export interface Checkpoint {
  step: number;
  preview: string;
  seconds: number;
}

export interface InfluenceRun {
  id: string;
  status: RunStatus;
  createdAt: number;
  updatedAt: number;
  message?: string;
  jobId?: string;
  ask: { text: string; heard?: string; projectId?: string | null; takeId?: string | null };
  name?: string;
  kind?: "Genre" | "Style" | "Artist";
  trigger?: string;
  about?: string;
  howMany?: string;
  style?: string;
  artists: RunArtist[];
  songs: RunSong[];
  /** your music (SV_MUSIC) couldn't be read when the songs were chosen: why */
  musicNote?: string | null;
  /** the add-on that gets songs that aren't in your music (its name), and why it couldn't be asked, if it couldn't */
  finder?: string | null;
  finderNote?: string | null;
  train?: {
    step: number;
    steps: number;
    loss?: number | null;
    status?: string;
    eta?: number | null;
    minutes?: number;
    checkpoints: Checkpoint[];
    baseline?: Checkpoint | null;
  };
  kept?: { step: number; influenceId: string };
  deleted?: boolean;
}
