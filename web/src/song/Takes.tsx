import { useEffect, useMemo, useRef, useState } from "react";
import { go } from "../lib/router";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Analysis, Take } from "../lib/types";
import { clock, usePlayer, type Source } from "../state/player";
import { useSong } from "../state/song";
import { Button, Modal, Segmented } from "../ui/controls";
import { Waveform } from "../ui/Waveform";

const fmt = (s?: number) => (s === undefined || !isFinite(s) ? "–:––" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const STEMS: { value: Source; label: string }[] = [
  { value: "mix", label: "Full mix" },
  { value: "vocals", label: "Vocals" },
  { value: "drums", label: "Drums" },
  { value: "bass", label: "Bass" },
  { value: "guitar", label: "Guitar" },
  { value: "piano", label: "Keys" },
  { value: "other", label: "Other" },
  { value: "instrumental", label: "No vocals" },
];

export function TakesColumn() {
  const { takes, doc, project } = useSong();
  const master = takes.find((t) => t.id === doc.masterTake);
  const others = takes.filter((t) => t.id !== doc.masterTake);
  return (
    <div className="tk">
      {master && <TheSong take={master} title={project?.title ?? ""} />}
      <div className="tk-head">
        <h2>{master ? "Other takes" : "Takes"}</h2>
        <span>{takes.length ? `${takes.length} made` : ""}</span>
      </div>
      {takes.length === 0 ? (
        <div className="tk-empty">
          <div className="tk-empty-art" aria-hidden="true">
            {Array.from({ length: 28 }, (_, i) => (
              <span key={i} style={{ ["--h" as string]: (0.2 + 0.8 * Math.abs(Math.sin(i * 0.7))).toFixed(2), ["--d" as string]: `${i * 0.05}s` }} />
            ))}
          </div>
          <p>Your takes will appear here.</p>
          <p className="tk-empty-sub">Each take is a different performance of the same song. Make a few, keep the one you love.</p>
        </div>
      ) : (
        <ul className="tk-list">
          {others.map((t) => (
            <li key={t.id}>
              <TakeCard take={t} title={project?.title ?? ""} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function useJob(take: Take) {
  const jobs = useSong((s) => s.jobs);
  return take.jobId ? jobs[take.jobId] : undefined;
}

const MODEL_NAME: Record<string, string> = { yue2: "YuE2", ace15: "ACE-Step", music3: "Music 3", upload: "Your song" };

function TakeCard({ take, title }: { take: Take; title: string }) {
  const job = useJob(take);
  const player = usePlayer();
  const active = player.take?.id === take.id;
  const [show, setShow] = useState<"sketch" | "sent" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sure, setSure] = useState(false);
  const working = ["queued", "sketching", "singing", "finishing"].includes(take.status);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }
  const again = (seed: number | null) =>
    act(seed === null ? "more" : "again", () =>
      api.post(`/api/projects/${take.projectId}/takes`, { ...take.request, model: take.model, takes: 1, seed }));

  return (
    <article className={`tc tc-${take.status}` + (active ? " tc-active" : "")}>
      <div className="tc-top">
        <button type="button" className="tc-play" disabled={take.status !== "ready"} aria-label={active && player.playing ? "Pause" : "Play"}
          onClick={() => (active ? player.toggle() : player.play(take, title))}>
          {active && player.playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <div className="tc-name">
          <strong>Take {take.n}</strong>
          <span>
            {take.status === "ready" ? fmt(take.duration) : working ? job?.message ?? "Waiting its turn" : take.status === "failed" ? "Didn't work" : "Stopped"}
            {take.truncated && <em title="It reached the length limit before it ended"> · no ending</em>}
          </span>
        </div>
        <div className="tc-tags">
          {take.sent.influences.filter((i) => i.id !== "instrumental").map((i) => (
            <span key={i.id} className="tc-tag">{i.name} {Math.round(i.strength * 100)}%</span>
          ))}
          {take.model !== "yue2" && <span className="tc-tag">{MODEL_NAME[take.model] ?? take.model}</span>}
          <span className="tc-tag tc-seed" title="Seed">#{String(take.seed).slice(-5)}</span>
        </div>
        <button type="button" className={"tc-like" + (take.liked ? " on" : "")} aria-pressed={!!take.liked} title="Keep an eye on this one"
          onClick={() => void act("like", () => api.patch(`/api/takes/${take.id}`, { liked: !take.liked }))}>
          ♥
        </button>
      </div>

      {take.status === "ready" && take.files ? (
        <Waveform url={fileUrl(take.projectId, take.files.peaks)} duration={take.duration ?? 0} active={active}
          onSeek={(t) => (active ? player.seek(t) : player.play(take, title, t))} />
      ) : working ? (
        <div className="tc-progress">
          <div className="tc-bar"><span style={{ width: `${Math.round((job?.progress ?? 0) * 100)}%` }} /></div>
          <span className="tc-stage">{stageLabel(take.status)}</span>
        </div>
      ) : (
        <p className="tc-error">{take.error ?? "It stopped before it finished."}</p>
      )}

      <div className="tc-actions">
        {take.status === "ready" && (
          <Button kind="primary" size="sm" busy={busy === "use"} onClick={() => act("use", () => api.post(`/api/takes/${take.id}/use`))}>
            Use this one
          </Button>
        )}
        {take.model !== "upload" && (take.status === "ready" || take.status === "failed" || take.status === "stopped") && (
          <>
            <Button size="sm" kind="ghost" busy={busy === "more"} onClick={() => again(null)} title="Same song and settings, a new performance">
              More like this
            </Button>
            <Button size="sm" kind="ghost" busy={busy === "again"} onClick={() => again(take.seed)} title="Exactly this take's seed and settings">
              Again, same seed
            </Button>
          </>
        )}
        {take.status === "ready" && take.model !== "upload" && (
          <Button size="sm" kind="ghost" title="The sound isn't coming through? Train an influence for it"
            onClick={() => go(`/influences?project=${take.projectId}&take=${take.id}`)}>
            Needs more influence
          </Button>
        )}
        {take.sketch && <Button size="sm" kind="ghost" onClick={() => setShow("sketch")}>Sketch</Button>}
        {take.model !== "upload" && <Button size="sm" kind="ghost" onClick={() => setShow("sent")}>What {MODEL_NAME[take.model] ?? "the model"} got</Button>}
        {working && take.jobId && (
          <Button size="sm" kind="ghost" busy={busy === "stop"} onClick={() => void act("stop", () => api.post(`/api/jobs/${take.jobId}/cancel`))}>Stop</Button>
        )}
        <span className="tc-spacer" />
        {sure ? (
          <span className="tc-sure">
            Delete this take?
            <Button size="sm" kind="ghost" busy={busy === "del"} onClick={() => void act("del", () => api.del(`/api/takes/${take.id}`))}>Delete</Button>
            <Button size="sm" kind="ghost" onClick={() => setSure(false)}>Keep it</Button>
          </span>
        ) : (
          <Button size="sm" kind="ghost" onClick={() => setSure(true)} title="Delete this take">Delete</Button>
        )}
      </div>
      {error && <p className="tc-error">{error}</p>}

      {show === "sketch" && (
        <Modal title={`Take ${take.n}: the sketch`} onClose={() => setShow(null)} wide>
          <p className="tc-modal-lead">
            Before singing, YuE2 wrote the song as a score in ABC notation ({take.sent.plan === "full" ? "melody and chords" : "melody"}). This is
            what it then sang.
          </p>
          <pre className="tc-pre">{take.sketch}</pre>
        </Modal>
      )}
      {show === "sent" && (
        <Modal title={`Take ${take.n}: what ${MODEL_NAME[take.model] ?? "the model"} got`} onClose={() => setShow(null)} wide>
          <dl className="tc-dl">
            <dt>{take.model === "music3" ? "Caption" : "Style"}</dt><dd>{take.sent.style}</dd>
            {take.model === "yue2" && <><dt>Composition</dt><dd>{take.sent.plan === "free" ? "No sketch (improvised)" : take.sent.plan === "full" ? "Melody and chords" : "Melody only"}</dd></>}
            <dt>Influences</dt><dd>{take.sent.influences.length ? take.sent.influences.map((i) => `${i.name} ${Math.round(i.strength * 100)}%`).join(", ") : "None"}</dd>
            <dt>Seed</dt><dd className="tc-mono">{take.seed}</dd>
            <dt>{take.model === "yue2" ? "Singing" : "Settings"}</dt><dd className="tc-mono">{Object.entries(take.sent.sing ?? take.sent.params ?? {}).filter(([k]) => !["style", "lyrics"].includes(k)).map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
            {take.sent.sketch && <><dt>Sketch</dt><dd className="tc-mono">{Object.entries(take.sent.sketch).filter(([k]) => !["style", "lyrics"].includes(k)).map(([k, v]) => `${k} ${v}`).join(" · ") || "defaults"}</dd></>}
          </dl>
          <h4 className="tc-h4">Lyrics as sent</h4>
          <pre className="tc-pre">{take.sent.lyrics}</pre>
        </Modal>
      )}
    </article>
  );
}

function stageLabel(s: string) {
  return { queued: "Waiting its turn", sketching: "Writing the melody", singing: "Singing", finishing: "Finishing" }[s] ?? s;
}

/** The chosen take: the song everything else follows. Stems to listen through, words lighting up as they're sung. */
function TheSong({ take, title }: { take: Take; title: string }) {
  const player = usePlayer();
  const active = player.take?.id === take.id;
  const a = take.analysis;
  const job = useSong((s) => Object.values(s.jobs).find((j) => j.takeId === take.id && j.kind === "analysis" && (j.status === "running" || j.status === "queued")));
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

  useEffect(() => {
    if (a?.status === "ready" && a.file) {
      // (a missing or unreadable file leaves the song without its map rather than the page blank)
      fetch(fileUrl(take.projectId, a.file)).then((r) => (r.ok ? r.json() : null))
        .then((x) => setAnalysis(x && Array.isArray(x.lines) ? x : null)).catch(() => setAnalysis(null));
    }
  }, [a?.status, a?.file, take.projectId]);

  return (
    <section className="ts">
      <div className="ts-top">
        <button type="button" className="ts-play" aria-label={active && player.playing ? "Pause" : "Play"}
          onClick={() => (active ? player.toggle() : player.play(take, title))}>
          {active && player.playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <div className="ts-name">
          <span className="ts-badge">The song</span>
          <strong>{title || "Untitled song"}</strong>
          <span>Take {take.n} · {fmt(take.duration)}{analysis?.tempo ? ` · ${Math.round(analysis.tempo)} BPM` : ""}</span>
        </div>
      </div>
      {take.files && (
        <Waveform url={fileUrl(take.projectId, take.files.peaks)} duration={take.duration ?? 0} active={active} height={72}
          onSeek={(t) => (active ? player.seek(t) : player.play(take, title, t))} />
      )}
      {a?.status === "ready" ? (
        <>
          {a.stems && Object.keys(a.stems).length > 0 && (
            <div className="ts-stems">
              <span className="ts-label">Listen to</span>
              <Segmented size="sm" label="Listen to" value={active ? player.source : "mix"}
                onChange={(v) => {
                  if (!active) player.play(take, title);
                  usePlayer.getState().listenTo(v, take);
                }}
                options={STEMS.filter((s) => s.value === "mix" || a.stems?.[s.value])} />
            </div>
          )}
          {analysis && analysis.lines.length > 0 && <Karaoke analysis={analysis} take={take} title={title} />}
          {analysis && analysis.lines.length === 0 && <p className="ts-quiet">An instrumental: the beat and sections are mapped for the video.</p>}
        </>
      ) : a?.status === "failed" ? (
        <p className="tc-error">Listening didn't finish: {a.error}{" "}
          <button type="button" className="mk-link" onClick={() => void api.post(`/api/takes/${take.id}/listen`).catch(() => undefined)}>Try again</button></p>
      ) : (
        <div className="ts-listening">
          <div className="tc-bar"><span style={{ width: `${Math.round((job?.progress ?? 0.02) * 100)}%` }} /></div>
          <span>{job?.message ?? "Waiting to listen"}: separating the stems and timing every word.</span>
        </div>
      )}
    </section>
  );
}

function Karaoke({ analysis, take, title }: { analysis: Analysis; take: Take; title: string }) {
  const player = usePlayer();
  const active = player.take?.id === take.id;
  const [at, setAt] = useState<{ line: number; word: number }>({ line: -1, word: -1 });
  const box = useRef<HTMLDivElement>(null);
  const lines = analysis.lines;
  const starts = useMemo(() => lines.map((l) => l.start), [lines]);

  useEffect(() => {
    if (!active) return setAt({ line: -1, word: -1 });
    return clock.onFrame((t) => {
      let li = -1;
      for (let i = 0; i < starts.length; i++) if (starts[i] <= t + 0.05) li = i;
      const words = li >= 0 ? lines[li].words : [];
      let wi = -1;
      for (let i = 0; i < words.length; i++) if (words[i].start <= t + 0.02) wi = i;
      setAt((p) => (p.line === li && p.word === wi ? p : { line: li, word: wi }));
    });
  }, [active, starts, lines]);

  useEffect(() => {
    // keep the sung line in the middle of the lyrics box (only the box scrolls, never the page)
    const kk = box.current;
    const el = kk?.querySelector<HTMLElement>(`[data-line="${at.line}"]`);
    if (kk && el) kk.scrollTo({ top: el.offsetTop - kk.clientHeight / 2 + el.clientHeight / 2, behavior: "smooth" });
  }, [at.line]);

  let lastSection = "";
  return (
    <div className="kk" ref={box}>
      {lines.map((l, i) => {
        const head = l.section !== lastSection ? l.section : "";
        lastSection = l.section;
        const state = i < at.line ? "past" : i === at.line ? "now" : "next";
        return (
          <div key={l.id}>
            {head && <div className="kk-sec">{head}</div>}
            <button type="button" data-line={i} className={`kk-line kk-${state}` + ((l.score ?? 1) < 0.45 ? " kk-unsure" : "")}
              title={(l.score ?? 1) < 0.45 ? "This line may not be sung as written" : `${fmt(l.start)}`}
              onClick={() => (active ? player.seek(Math.max(0, l.start - 0.25)) : player.play(take, title, Math.max(0, l.start - 0.25)))}>
              {l.words.length
                ? l.words.map((w, j) => (
                    <span key={j} className={i < at.line || (i === at.line && j <= at.word) ? "kk-w kk-lit" : "kk-w"}>{w.text} </span>
                  ))
                : l.text}
            </button>
          </div>
        );
      })}
    </div>
  );
}

export function PlayIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" /></svg>;
}
export function PauseIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="5" width="4" height="14" rx="1.2" /><rect x="13.5" y="5" width="4" height="14" rx="1.2" /></svg>;
}
