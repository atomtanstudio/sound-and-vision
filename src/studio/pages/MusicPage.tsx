import { useEffect, useRef, useState } from "react";
import {
  FileMusic,
  ListChecks,
  Loader2,
  Play,
  RefreshCcw,
  Scissors,
  Sparkles,
  Video,
  WandSparkles,
  XCircle,
} from "lucide-react";
import { createRequestId, musicApi, request } from "../../music-studio/api";
import { SongDescription, accountStatus, type AccountStatus } from "../../music-studio/Assistance";
import {
  initialForm,
  projects,
  readLocal,
  validate,
  writeLocal,
  type SongForm,
  type Track,
} from "../../music-studio/model";
import { playable, timeLabel, useStudio } from "../context";
import { CoverArt } from "../components/CoverArt";
import { TrackDetail } from "../components/TrackDetail";
import {
  Btn,
  CheckRow,
  ErrorNote,
  Field,
  Kicker,
  Segmented,
  Select,
  Slider,
  TextArea,
  TextInput,
  Toggle,
  cn,
} from "../ui";

type Proposal = {
  title?: string;
  lyrics?: string;
  style?: string;
  abc?: string;
  summary?: string;
  ideas?: { title: string; style: string; description: string }[];
};
type Job = {
  id: string;
  kind: string;
  state: string;
  error: string | null;
  result: { proposal?: Proposal; abc?: string; concept?: unknown } | null;
};
const terminal = (job: Job | null) =>
  !!job && ["succeeded", "failed", "cancelled"].includes(job.state);

type AssistTask =
  | "Song ideas"
  | "Draft lyrics"
  | "Rewrite a section"
  | "Refine the style"
  | "Translate lyrics"
  | "Edit score";

function requestAssist(task: AssistTask) {
  window.dispatchEvent(new CustomEvent<AssistTask>("sv-assist-task", { detail: task }));
}

export function MusicPage() {
  const { tracks, upsertLocal, pushToast, online, refresh, playTrack, makeVideo, settingsOpen, setSettingsOpen } =
    useStudio();
  const [form, setForm] = useState<SongForm>(() => ({
    ...initialForm,
    ...readLocal<Partial<SongForm>>("sv-form-v2", {}),
  }));
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [detail, setDetail] = useState<Track | null>(null);
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const pendingId = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => {
    writeLocal("sv-form-v2", form);
  }, [form]);
  useEffect(() => {
    if (!online) {
      setAccount(null);
      return;
    }
    let cancelled = false;
    accountStatus()
      .then((value) => { if (!cancelled) setAccount(value); })
      .catch(() => { if (!cancelled) setAccount(null); });
    return () => { cancelled = true; };
  }, [online, settingsOpen]);
  const update = (part: Partial<SongForm>) =>
    setForm((old) => ({ ...old, ...part }));

  async function generate() {
    const problem = validate(form);
    setError(problem || "");
    if (problem) return;
    setSubmitting(true);
    const signature = JSON.stringify(form);
    if (pendingId.current?.signature !== signature)
      pendingId.current = { signature, id: createRequestId() };
    try {
      const result = await musicApi.generate(pendingId.current.id, form);
      upsertLocal(result.tracks);
      pendingId.current = null;
      pushToast(
        result.reused ? "Request reused — the bench already has these takes" : (form.count === 2 ? "Two takes queued for the bench" : "One take queued for the bench"),
      );
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const live = tracks.filter(
    (t) => t.status && !["succeeded", "failed", "cancelled"].includes(t.status),
  );
  const done = tracks.filter((t) => t.status === "succeeded" && !t.deletedAt).slice(0, 4);
  const failed = tracks.filter((t) => t.status === "failed").slice(0, 2);

  return (
    <div className="music">
      <header className="page-head">
        <div>
          <Kicker>The console</Kicker>
          <h1>New song</h1>
        </div>
        <p className="page-head-note">
          {online ? "YuE2 synthesis is connected." : "Engine offline — you can still write; requests will retry when it returns."}
        </p>
      </header>

      <div className="music-grid">
        <section className="panel composer">
          <div className="field song-description-field">
            <SongDescription
              form={form}
              change={setForm}
              account={account}
              connect={() => setSettingsOpen(true)}
              label="Describe the song"
              inputClassName="input textarea composer-description"
            />
            <span className="field-hint">A feeling, a scene, a sound — plain language works best.</span>
          </div>
          <div className="composer-row">
            <Field label="Title">
              <TextInput placeholder="Untitled" value={form.title} onChange={(e) => update({ title: e.target.value })} />
            </Field>
            <Field label="Project">
              <Select value={form.project} onChange={(e) => update({ project: e.target.value })}>
                {[...new Set([form.project, ...projects, ...readLocal<string[]>("sv-projects-v2", []), ...tracks.map((track) => track.project)])].map((project) => (
                  <option key={project} value={project}>{project}</option>
                ))}
              </Select>
            </Field>
            <Field label="Takes">
              <Segmented
                ariaLabel="Number of takes"
                size="sm"
                options={[{ value: "1", label: "1" }, { value: "2", label: "2" }]}
                value={String(form.count)}
                onChange={(v) => update({ count: Number(v) as 1 | 2 })}
              />
            </Field>
          </div>
          <div className="field">
            <div className="field-heading">
              <span className="field-label">Style tags</span>
              <button
                type="button"
                className="writer-wand"
                aria-label="Refine style"
                title="Refine style"
                onClick={() => requestAssist("Refine the style")}
              >
                <WandSparkles size={16} />
              </button>
            </div>
            <TextInput placeholder="Style" value={form.style} onChange={(e) => update({ style: e.target.value })} />
            <span className="field-hint">Optional — e.g. dream pop · female vocal · 92 bpm</span>
          </div>
          <div className="field">
            <div className="field-heading">
              <span className="field-label">Lyrics</span>
              <button
                type="button"
                className="writer-wand"
                aria-label="Generate lyrics"
                title="Generate lyrics"
                onClick={() => requestAssist("Draft lyrics")}
              >
                <WandSparkles size={16} />
              </button>
            </div>
            <TextArea rows={6} placeholder={"[Verse]\n…"} value={form.lyrics} onChange={(e) => update({ lyrics: e.target.value })} />
            <span className="field-hint">Leave empty and the model will write them, or ask the assistant.</span>
          </div>

          <button className="disclosure" onClick={() => setAdvanced((v) => !v)} aria-expanded={advanced}>
            {advanced ? <Scissors size={14} /> : <ListChecks size={14} />}
            {advanced ? "Hide synthesis controls" : "Synthesis controls"}
            <small>seed · guidance · score planning · sampling</small>
          </button>
          {advanced ? <AdvancedPanel form={form} update={update} /> : null}

          <div className="generate-bar">
            <Btn variant="primary" size="lg" loading={submitting} onClick={() => void generate()}>
              <WandSparkles size={17} /> Generate {form.count === 2 ? "two takes" : "a take"}
            </Btn>
            <span>{error || (form.count === 2 ? "Both takes get their own seed, cover and delivery." : "This take gets its own seed, cover and delivery.")}</span>
          </div>
        </section>

        <aside className="music-rail">
          <AssistPanel form={form} update={update} />
          <ReferencePanel update={update} pushToast={pushToast} />
        </aside>
      </div>

      {(live.length || failed.length || done.length) > 0 ? (
        <section className="bench">
          <header className="section-head">
            <h2>On the bench</h2>
            <Kicker>live synthesis</Kicker>
          </header>
          <div className="bench-grid">
            {[...live, ...failed, ...done].map((track) => (
              <BenchCard
                key={track.id}
                track={track}
                onOpen={() => setDetail(track)}
                onPlay={() => playTrack(track)}
                onVideo={() => makeVideo(track)}
                playing={false}
              />
            ))}
          </div>
        </section>
      ) : null}
      {detail ? <TrackDetail track={detail} onClose={() => setDetail(null)} /> : null}
    </div>
  );
}

/* ---------------------------------------------------------------- bench */
function BenchCard({
  track,
  onOpen,
  onPlay,
  onVideo,
}: {
  track: Track;
  onOpen: () => void;
  onPlay: () => void;
  onVideo: () => void;
  playing: boolean;
}) {
  const { refresh, pushToast } = useStudio();
  const [error, setError] = useState("");
  const live = !!track.status && !["succeeded", "failed", "cancelled"].includes(track.status);
  return (
    <article className={cn("bench-card", live && "live")}>
      <CoverArt track={track} ring={live} />
      <div className="bench-meta">
        <button className="bench-title" onClick={onOpen}>
          {track.title || "Untitled"}
        </button>
        <span className={cn("bench-status", `tone-${track.status || "done"}`)}>
          {live ? track.stage || track.status : track.status}
          {track.status === "running" && track.elapsed ? ` · ${timeLabel(track.elapsed)}` : ""}
          {track.attempt && track.attempt > 1 ? ` · attempt ${track.attempt}` : ""}
        </span>
        <div className="bench-actions">
          {playable(track) ? (
            <button className="icon-btn icon-btn-sm" aria-label="Play" onClick={onPlay}>
              <Play size={13} fill="currentColor" />
            </button>
          ) : null}
          {track.status === "succeeded" ? (
            <button className="icon-btn icon-btn-sm" aria-label="Make video" onClick={onVideo}>
              <Video size={13} />
            </button>
          ) : null}
          {track.status === "needs-review" && track.source ? (
            <button className="icon-btn icon-btn-sm" aria-label="Review plan" onClick={onOpen}>
              <FileMusic size={13} />
            </button>
          ) : null}
          {track.status === "failed" && track.source ? (
            <button
              className="icon-btn icon-btn-sm"
              aria-label="Retry"
              onClick={() => musicApi.retry(track.id).then(refresh).catch((e) => setError((e as Error).message))}
            >
              <RefreshCcw size={13} />
            </button>
          ) : null}
          {live && track.source ? (
            <button
              className="icon-btn icon-btn-sm"
              aria-label="Cancel"
              onClick={() => musicApi.cancel(track.id).then(refresh).catch((e) => setError((e as Error).message))}
            >
              <XCircle size={13} />
            </button>
          ) : null}
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        {live ? <span className="bench-live-line" aria-hidden="true" /> : null}
      </div>
    </article>
  );
}

/* ------------------------------------------------------------ advanced */
function AdvancedPanel({ form, update }: { form: SongForm; update: (p: Partial<SongForm>) => void }) {
  const { pushToast } = useStudio();
  const setSampling = (which: "semantic" | "score", part: Partial<SongForm["semantic"]>) =>
    update({ [which]: { ...form[which], ...part } } as Partial<SongForm>);
  return (
    <div className="advanced">
      <div className="advanced-grid">
        <Field label="Seed" hint="Blank = fresh seed per take">
          <TextInput inputMode="numeric" placeholder="auto" value={form.seed} onChange={(e) => update({ seed: e.target.value.replace(/\D/g, "") })} />
        </Field>
        <Field label="Guidance (CFG)">
          <TextInput inputMode="decimal" placeholder="default" value={form.cfg_scale} onChange={(e) => update({ cfg_scale: e.target.value })} />
        </Field>
        <Field label="Score planning">
          <Select value={form.cot} onChange={(e) => update({ cot: e.target.value as SongForm["cot"] })}>
            <option value="full">Melody & chords</option>
            <option value="melody">Melody only</option>
            <option value="off">No score plan</option>
          </Select>
        </Field>
        <Field label="Synthesis steps">
          <TextInput inputMode="numeric" value={String(form.ode_steps)} onChange={(e) => update({ ode_steps: Number(e.target.value) || 32 })} />
        </Field>
      </div>
      <CheckRow checked={form.planFirst} onChange={(planFirst) => update({ planFirst })}>
        Review the score plan before synthesis
      </CheckRow>
      <LoraPicker form={form} update={update} />
      <div className="sampling-grid">
        {(["score", "semantic"] as const).map((which) => (
          <details key={which} className="sampling-block">
            <summary>
              <Kicker>{which} sampling</Kicker>
              <span>temp {form[which].temperature} · top-p {form[which].top_p}</span>
            </summary>
            {(
              [
                ["temperature", 0, 5, 0.05],
                ["top_p", 0.01, 1, 0.01],
                ["top_k", 1, 200, 1],
                ["repetition_penalty", 0.1, 3, 0.005],
                ["penalty_window", 1, 100, 1],
                ["min_tokens", 0, 9000, 1],
                ["max_tokens", 1, 12000, 1],
              ] as const
            ).map(([key, min, max, step]) => (
              <Slider
                key={key}
                label={key}
                min={min}
                max={max}
                step={step}
                value={form[which][key]}
                onChange={(v) => setSampling(which, { [key]: v })}
              />
            ))}
          </details>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- lora picker */
type LoraGroup = {
  id: string;
  name: string;
  kind: "style" | "artist";
  trigger: string;
  preferredStep: number;
  checkpoints: { id: string; sha256: string; label: string; step: number }[];
  generation?: { cot?: string; cfg_scale?: number; ode_steps?: number };
};
export function LoraPicker({ form, update }: { form: SongForm; update: (p: Partial<SongForm>) => void }) {
  const { online } = useStudio();
  const [groups, setGroups] = useState<LoraGroup[] | null>(null);
  useEffect(() => {
    if (!online) return;
    request<{ groups: LoraGroup[] }>("/loras")
      .then((r) => setGroups(r.groups))
      .catch(() => setGroups([]));
  }, [online]);
  if (!groups?.length) return null;
  const selected = form.lora?.id;
  return (
    <div className="lora-picker">
      <Kicker>Trained styles</Kicker>
      <div className="lora-chips">
        <button
          className={cn("lora-chip", !selected && "on")}
          onClick={() => update({ lora: null })}
        >
          Base model
        </button>
        {groups.map((group) => (
          <button
            key={group.id}
            className={cn("lora-chip", selected === group.id && "on", `lora-${group.kind}`)}
            title={`${group.trigger} · preferred step ${group.preferredStep}`}
            onClick={() => {
              if (selected === group.id) update({ lora: null });
              else
                update({
                  lora: {
                    id: group.id,
                    sha256: group.checkpoints[0]?.sha256 || "",
                    strength: 1,
                  },
                  ...(group.generation?.cfg_scale ? { cfg_scale: String(group.generation.cfg_scale) } : {}),
                  ...(group.generation?.ode_steps ? { ode_steps: group.generation.ode_steps } : {}),
                  ...(group.generation?.cot ? { cot: group.generation.cot as SongForm["cot"] } : {}),
                });
            }}
          >
            <em>{group.kind}</em>
            {group.name}
          </button>
        ))}
      </div>
      {form.lora ? (
        <Slider
          label="LoRA strength"
          min={0.1}
          max={2}
          step={0.05}
          value={form.lora.strength}
          display={form.lora.strength.toFixed(2)}
          onChange={(strength) => update({ lora: { ...form.lora!, strength } })}
        />
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- assist */
const tasks: AssistTask[] = [
  "Song ideas",
  "Draft lyrics",
  "Rewrite a section",
  "Refine the style",
  "Translate lyrics",
  "Edit score",
];
function AssistPanel({ form, update }: { form: SongForm; update: (p: Partial<SongForm>) => void }) {
  const { online } = useStudio();
  const [task, setTask] = useState<AssistTask>("Draft lyrics");
  const [prompt, setPrompt] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };
  useEffect(stop, []);

  useEffect(() => {
    const onAssistTask = (event: Event) => {
      const requested = (event as CustomEvent<AssistTask>).detail;
      if (!tasks.includes(requested)) return;
      setTask(requested);
      window.requestAnimationFrame(() => {
        document.getElementById("writing-assistant")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    };
    window.addEventListener("sv-assist-task", onAssistTask);
    return () => window.removeEventListener("sv-assist-task", onAssistTask);
  }, []);

  async function run() {
    setError("");
    stop();
    try {
      const started = await request<Job>("/assistance", {
        requestId: createRequestId(),
        task,
        prompt: prompt || form.description || form.title,
        title: form.title,
        lyrics: form.lyrics,
        style: form.style,
        abc: form.abc,
      });
      setJob(started);
      timer.current = setInterval(async () => {
        try {
          const fresh = await request<Job>(`/assistance/${started.id}`);
          setJob(fresh);
          if (terminal(fresh)) stop();
        } catch {
          /* keep polling */
        }
      }, 1500);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const result = job?.state === "succeeded" ? job.result?.proposal : null;
  const apply = (part: Partial<SongForm>) => {
    update(part);
  };
  return (
    <section id="writing-assistant" className="panel assist">
      <header className="panel-head">
        <h2>
          <Sparkles size={15} /> Writing assistant
        </h2>
      </header>
      <div className="assist-tasks">
        {tasks.map((t) => (
          <button key={t} className={cn("chip", task === t && "on")} onClick={() => setTask(t)}>
            {t}
          </button>
        ))}
      </div>
      <TextArea
        rows={2}
        placeholder="Anything the assistant should know — a topic, a phrase, the section to fix…"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
      />
      <div className="assist-run">
        <Btn variant="primary" disabled={!online || (!!job && !terminal(job))} loading={!!job && !terminal(job)} onClick={() => void run()}>
          {job && !terminal(job) ? "Thinking…" : `Run · ${task}`}
        </Btn>
        {job && !terminal(job) ? (
          <Btn variant="quiet" onClick={() => request(`/assistance/${job.id}/cancel`, {}).then((j) => { stop(); setJob(j as Job); }).catch(() => {})}>
            <Loader2 size={14} className="spin" /> Cancel
          </Btn>
        ) : null}
      </div>
      <ErrorNote>{error || (job?.state === "failed" ? job.error : "")}</ErrorNote>
      {result ? (
        <div className="assist-result">
          {result.summary ? <p className="assist-summary">{result.summary}</p> : null}
          {result.lyrics ? (
            <div className="assist-piece">
              <Kicker>Lyrics</Kicker>
              <pre>{result.lyrics}</pre>
              <Btn size="sm" onClick={() => apply({ lyrics: result.lyrics! })}>Use these lyrics</Btn>
            </div>
          ) : null}
          {result.abc ? (
            <div className="assist-piece">
              <Kicker>Score</Kicker>
              <pre>{result.abc}</pre>
              <Btn size="sm" onClick={() => apply({ abc: result.abc! })}>Use this score</Btn>
            </div>
          ) : null}
          {result.style || result.title ? (
            <div className="assist-piece">
              {result.title ? <p><strong>{result.title}</strong></p> : null}
              {result.style ? (
                <>
                  <Kicker>Style</Kicker>
                  <p className="muted">{result.style}</p>
                </>
              ) : null}
              <div className="assist-actions">
                {result.title ? <Btn size="sm" onClick={() => apply({ title: result.title! })}>Use title</Btn> : null}
                {result.style ? (
                  <Btn
                    size="sm"
                    onClick={() => apply({ style: result.style! })}
                  >
                    Use style
                  </Btn>
                ) : null}
              </div>
            </div>
          ) : null}
          {result.ideas?.length ? (
            <div className="assist-piece">
              <Kicker>Ideas</Kicker>
              {result.ideas.map((idea, i) => (
                <button key={i} className="idea-row" onClick={() => apply({ title: idea.title, description: idea.description, style: idea.style })}>
                  <strong>{idea.title}</strong>
                  <span>{idea.style}</span>
                  <p>{idea.description}</p>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------ reference */
function ReferencePanel({
  update,
  pushToast,
}: {
  update: (p: Partial<SongForm>) => void;
  pushToast: (m: string, tone?: "ok" | "err") => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearInterval(timer.current);
    },
    [],
  );
  async function upload(file: File) {
    setError("");
    try {
      const response = await fetch("/api/references?mode=melody", {
        method: "POST",
        headers: { "X-Filename": file.name, "Content-Type": file.type || "application/octet-stream" },
        body: file,
        signal: AbortSignal.timeout(65000),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || "Reference upload failed.");
      setJob(data as Job);
      timer.current = setInterval(async () => {
        try {
          const fresh = await request<Job>(`/assistance/${(data as Job).id}`);
          setJob(fresh);
          if (terminal(fresh)) {
            clearInterval(timer.current!);
            if (fresh.state === "succeeded" && fresh.result?.abc) {
              update({ abc: fresh.result.abc, cot: "melody" });
              pushToast("Melody reference applied — score planning set to melody");
            }
          }
        } catch {
          /* keep polling */
        }
      }, 1500);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel reference">
      <header className="panel-head">
        <h2>
          <FileMusic size={15} /> Melody reference
        </h2>
      </header>
      <p className="muted small">
        Hum or upload any audio you own; we transcribe the melody to ABC and steer the composition with it.
      </p>
      <label className="file-drop">
        <input
          type="file"
          accept="audio/*"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
        />
        <span>{job && !terminal(job) ? "Transcribing…" : "Choose an audio file"}</span>
      </label>
      <ErrorNote>{error}</ErrorNote>
    </section>
  );
}
