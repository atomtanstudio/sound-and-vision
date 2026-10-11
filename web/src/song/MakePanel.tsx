import { useEffect, useRef, useState } from "react";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Influence, Project } from "../lib/types";
import type { Listed } from "../shell/RecentList";
import "../shell/bring.css";
import { lyricsText, useSong } from "../state/song";
import { Button, Chip, Disclosure, Modal, Segmented, Slider, TextArea } from "../ui/controls";
import { AddInfluence } from "./AddInfluence";
import { LyricSheet } from "./LyricSheet";
import { looksLikeSound, MatchSound } from "./MatchSound";
import { FIRST_GENRES, GENRES, KEYS, LANGUAGES, MOODS } from "./sound";
import { machine } from "../lib/machine";

/** YuE2's own defaults, shown in the Engine room so a change is always visible against them. */
const ENGINE = [
  { stage: "Sketch (the melody and chords)", fields: [
    { key: "plan_temperature", label: "Temperature", def: 0.7, min: 0.1, max: 1.5, step: 0.05 },
    { key: "plan_top_p", label: "Top-p", def: 0.9, min: 0.1, max: 1, step: 0.01 },
    { key: "plan_top_k", label: "Top-k", def: 30, min: 1, max: 200, step: 1 },
    { key: "plan_repetition_penalty", label: "Repetition penalty", def: 1.005, min: 1, max: 1.5, step: 0.005 },
    { key: "plan_penalty_window", label: "Penalty window (tokens)", def: 100, min: 10, max: 1000, step: 10 },
    { key: "plan_max_tokens", label: "Longest sketch (tokens)", def: 8192, min: 1024, max: 20000, step: 256 },
  ] },
  { stage: "Singing", fields: [
    { key: "top_p", label: "Top-p", def: 0.95, min: 0.1, max: 1, step: 0.01 },
    { key: "top_k", label: "Top-k", def: 100, min: 1, max: 1000, step: 1 },
    { key: "guidance", label: "Text guidance (CFG)", def: 1.0, min: 0, max: 3, step: 0.01 },
    { key: "steps", label: "Synthesis steps", def: 32, min: 8, max: 96, step: 1 },
    { key: "seconds", label: "Longest song (seconds)", def: 0, min: 0, max: 600, step: 10 },
  ] },
] as const;

const LENGTH_LABEL = { short: "Short", song: "Song", long: "Long" } as const;
/** Who sings it, and roughly how long a take of a 3-4 minute song takes on the server. */
const MODELS = {
  yue2: { name: "YuE2", hint: "The best sound; sketches the melody first", perTake: 75 },
  ace15: { name: "ACE-Step 1.5", hint: "Fast and flexible; real tempo and key", perTake: 20 },
  music3: { name: "MiniMax Music 3", hint: "Rich arrangements; slow; picks its own length", perTake: 200 },
} as const;
const LENGTH_HINT = { short: "about 1½–2½ min", song: "about 3–4 min", long: "up to 6 min" } as const;

export function MakePanel() {
  const s = useSong();
  const d = s.doc;
  const [moreGenres, setMoreGenres] = useState(false);
  const [custom, setCustom] = useState("");
  const [picking, setPicking] = useState(false);
  const [matching, setMatching] = useState<null | { text: string; fromIdea: boolean }>(null);
  const [making, setMaking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (key: "genres" | "moods", v: string) =>
    s.set(key, d[key].includes(v) ? d[key].filter((x) => x !== v) : [...d[key], v]);
  const words = d.sections.reduce((n, x) => n + (x.kind === "instrumental" ? 0 : x.text.split(/\s+/).filter(Boolean).length), 0);
  const hasSound = d.genres.length + d.moods.length > 0 || !!d.instruments.trim() || !!d.extra.trim() || !!d.styleOverride?.trim();
  const covering = (d.model ?? "yue2") === "yue2" && !!d.covering;
  const why = !hasSound ? "Choose how it should sound first" : d.sung && words < 4 ? "A sung song needs words" :
    covering && !s.project?.reference ? "Choose the song to cover" : null;
  const lib = Object.fromEntries(s.library.map((i) => [i.id, i]));
  const model = d.model ?? "yue2";
  const scale = { short: 0.6, song: 1, long: 1.6 }[d.length] ?? 1;
  const minutes = Math.max(1, Math.round((d.takes * MODELS[model].perTake * scale) / 60));
  const yue = model === "yue2";

  async function make() {
    if (!s.project) return;
    setMaking(true);
    setError(null);
    await s.saveNow();
    try {
      const engine = yue ? Object.fromEntries(Object.entries(d.engine).filter(([, v]) => v !== null && v !== undefined))
        : model === "music3" && d.music3Guidance ? { guidance: d.music3Guidance } : {};
      await api.post(`/api/projects/${s.project.id}/takes`, {
        model, time_signature: model === "ace15" ? d.timeSignature : null, sung: d.sung, voice: d.voice, language: d.language, genres: d.genres, moods: d.moods,
        instruments: d.instruments, extra: d.extra, tempo: d.tempo, key: d.key, style_override: d.styleOverride,
        lyrics: lyricsText(d.sections), length: d.length, influences: d.influences, takes: d.takes, plan: d.plan,
        creativity: d.creativity, repetition: d.repetition, seed: d.seed, engine,
        cover: covering ? { keep: d.covering!.keep } : null,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setMaking(false);
    }
  }

  return (
    <div className="mk">
      <section className="mk-step">
        <h3><span className="mk-n">1</span>What's it about?</h3>
        <TextArea
          value={d.idea}
          minRows={2}
          placeholder="A late drive home after the last shift, the city half asleep, still thinking about someone…"
          onChange={(e) => s.set("idea", e.target.value)}
        />
        {looksLikeSound(d.idea) && (
          <div className="mk-hint">
            <span>This reads like a description of a <em>sound</em>. Want the app to match it?</span>
            <Button size="sm" kind="primary" onClick={() => setMatching({ text: d.idea, fromIdea: true })}>Match this sound</Button>
          </div>
        )}
      </section>

      <section className="mk-step">
        <div className="mk-step-head">
          <h3><span className="mk-n">2</span>The words</h3>
          <Segmented size="sm" label="Sung or instrumental" value={d.sung ? "sung" : "inst"} onChange={(v) => s.set("sung", v === "sung")}
            options={[{ value: "sung", label: "Sung" }, { value: "inst", label: "Instrumental" }]} />
        </div>
        {d.sung ? (
          <LyricSheet />
        ) : (
          <p className="mk-quiet">No words needed. YuE2 plays the whole song in the form the length sets, guided by the
            instrumental influence <a href="https://huggingface.co/Mothersuperior/YuE2-instrumental-cot-full-loras" target="_blank"
            rel="noreferrer">“YuE2-instrumental-cot-full-loras” by Mothersuperior</a> (CC BY-NC 4.0: non-commercial use).</p>
        )}
      </section>

      <section className="mk-step">
        <div className="mk-step-head">
          <h3><span className="mk-n">3</span>The sound</h3>
          <Button size="sm" kind="ghost" onClick={() => setMatching({ text: d.soundNotes ?? "", fromIdea: false })}
            title="Paste a description of a sound (from an AI that can listen, a review, your notes) and the app fills this in">
            Match a sound
          </Button>
        </div>
        {d.sung && (
          <div className="mk-row">
            <span className="mk-label">Voice</span>
            <Segmented size="sm" label="Voice" value={d.voice ?? "any"} onChange={(v) => s.set("voice", v === "any" ? null : (v as "female"))}
              options={[{ value: "female", label: "Female" }, { value: "male", label: "Male" }, { value: "duet", label: "Duet" },
                { value: "any", label: "Let it choose" }]} />
          </div>
        )}
        <div className="mk-field">
          <span className="mk-label">Genre</span>
          <div className="mk-chips">
            {[...new Set([...(moreGenres ? GENRES : GENRES.slice(0, FIRST_GENRES)), ...d.genres])].map((g) => (
              <Chip key={g} on={d.genres.includes(g)} onClick={() => toggle("genres", g)}>{g}</Chip>
            ))}
            <button type="button" className="mk-more" onClick={() => setMoreGenres(!moreGenres)}>{moreGenres ? "Fewer" : "More…"}</button>
            <input className="mk-custom" value={custom} placeholder="+ your own" onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && custom.trim()) {
                  if (!d.genres.includes(custom.trim().toLowerCase())) s.set("genres", [...d.genres, custom.trim().toLowerCase()]);
                  setCustom("");
                }
              }} />
          </div>
        </div>
        <div className="mk-field">
          <span className="mk-label">Mood</span>
          <div className="mk-chips">
            {[...new Set([...MOODS, ...d.moods])].map((m) => (
              <Chip key={m} tone="var(--c-graphics)" on={d.moods.includes(m)} onClick={() => toggle("moods", m)}>{m}</Chip>
            ))}
          </div>
        </div>
        <div className="mk-field">
          <label className="mk-label" htmlFor="mk-inst">Instruments</label>
          <input id="mk-inst" className="in" value={d.instruments} placeholder="shimmering guitars, warm synth pads, brushed drums"
            onChange={(e) => s.set("instruments", e.target.value)} />
        </div>
        <div className="mk-field">
          <span className="mk-label">Influences</span>
          <div className="mk-chips">
            {d.influences.map((pick) => {
              const inf = lib[pick.id];
              return (
                <InfluenceChip key={pick.id} name={inf?.name ?? pick.id} kind={inf?.kind ?? "Style"} strength={pick.strength}
                  max={inf?.max ?? 1} recommended={inf?.recommended ?? 0.5}
                  onChange={(v) => s.set("influences", d.influences.map((x) => (x.id === pick.id ? { ...x, strength: v } : x)))}
                  onRemove={() => s.set("influences", d.influences.filter((x) => x.id !== pick.id))} />
              );
            })}
            <button type="button" className="mk-add-inf" onClick={() => setPicking(true)}>+ Add an influence</button>
          </div>
        </div>
        <div className="mk-row">
          <span className="mk-label">Length</span>
          <Segmented size="sm" label="Length" value={d.length} onChange={(v) => s.set("length", v)}
            options={(["short", "song", "long"] as const).map((k) => ({ value: k, label: LENGTH_LABEL[k], hint: LENGTH_HINT[k] }))} />
        </div>
      </section>

      <section className="mk-step">
        <div className="mk-step-head">
          <h3><span className="mk-n">4</span>Who sings it</h3>
        </div>
        <Segmented size="sm" label="Song model" value={model} onChange={(v) => s.set("model", v)}
          options={(Object.keys(MODELS) as (keyof typeof MODELS)[]).map((k) => ({ value: k, label: MODELS[k].name, hint: MODELS[k].hint }))} />
        <p className="mk-help">
          {model === "yue2" && "YuE2 sounds the cleanest and follows your words closely; it sketches the melody first, and takes your influences."}
          {model === "ace15" && "ACE-Step 1.5 is the fastest and has real controls for tempo, key and time signature. YuE2 influences don't apply to it."}
          {model === "music3" && "MiniMax Music 3 builds rich, varied arrangements and decides its own length (up to the one you choose). It's the slowest. YuE2 influences don't apply."}
        </p>
        {model === "yue2" && (
          <div className="mk-field">
            <span className="mk-label">Start from</span>
            <Segmented size="sm" label="Start from" value={covering ? "cover" : "own"}
              onChange={(v) => s.set("covering", v === "cover" ? { keep: d.covering?.keep ?? "melody" } : null)}
              options={[
                { value: "own", label: "Its own tune", hint: "YuE2 writes the melody for your words" },
                { value: "cover", label: "A song to cover", hint: "Your words and style, sung to another song's melody" },
              ]} />
            {covering && <CoverSource />}
          </div>
        )}
      </section>

      <Disclosure id="shape" title="Shape it" hint={yue ? "melody, creativity, tempo, key" : "creativity, tempo, key"}>
        {yue && !covering && (<div className="mk-field">
          <span className="mk-label">How YuE2 composes</span>
          <Segmented size="sm" label="Composition" value={d.plan} onChange={(v) => s.set("plan", v)}
            options={[
              { value: "full", label: "Melody and chords", hint: "It sketches a melody and chords first, then sings them" },
              { value: "melody", label: "Melody only", hint: "It sketches only the melody; the band plays more freely" },
              { value: "free", label: "Improvise", hint: "No sketch: looser, less predictable", disabled: d.influences.length > 0 || !d.sung },
            ]} />
          <p className="mk-help">
            {d.plan === "full" && "YuE2 writes the melody and chords as a sketch first, then sings to it. The most reliable songs, with endings that land."}
            {d.plan === "melody" && "YuE2 sketches only the tune; the band finds its own chords. Good for looser, more surprising arrangements."}
            {d.plan === "free" && "No sketch at all: YuE2 sings straight from the words. Looser and less predictable (influences need a sketch)."}
          </p>
        </div>)}
        {model === "ace15" && (
          <div className="mk-row">
            <span className="mk-label">Time signature</span>
            <Segmented size="sm" label="Time signature" value={d.timeSignature ?? "4"} onChange={(v) => s.set("timeSignature", v)}
              options={(["4", "3", "6", "2"] as const).map((v) => ({ value: v, label: `${v}/4`.replace("6/4", "6/8") }))} />
          </div>
        )}
        {model === "music3" && (
          <Slider label="Guidance" value={d.music3Guidance ?? 1.7} min={1.0} max={4.0} step={0.1} defaultValue={1.7}
            left="Freer" right="Follows the caption" format={(v) => v.toFixed(1)} onChange={(v) => s.set("music3Guidance", v)} />
        )}
        <Slider label="Creativity" value={d.creativity} min={0.6} max={1.4} step={0.05} defaultValue={1.0}
          left="Steady" right="Adventurous" format={(v) => v.toFixed(2)} onChange={(v) => s.set("creativity", v)} />
        {yue && <Slider label="Variety" value={d.repetition} min={1.0} max={1.4} step={0.01} defaultValue={1.2}
          left="Repeats itself more" right="Repeats less" format={(v) => v.toFixed(2)} onChange={(v) => s.set("repetition", v)} />}
        <div className="mk-pair">
          <div className="mk-field">
            <label className="mk-label" htmlFor="mk-tempo">Tempo hint</label>
            <div className="mk-inline">
              <input id="mk-tempo" className="in mk-num" type="number" min={40} max={240} placeholder="—" value={d.tempo ?? ""}
                onChange={(e) => s.set("tempo", e.target.value ? Math.max(40, Math.min(240, Number(e.target.value))) : null)} />
              <span className="mk-unit">BPM</span>
            </div>
          </div>
          <div className="mk-field">
            <label className="mk-label" htmlFor="mk-key">Key hint</label>
            <select id="mk-key" className="in" value={d.key ?? ""} onChange={(e) => s.set("key", e.target.value || null)}>
              <option value="">Let it choose</option>
              {KEYS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          {d.sung && (
            <div className="mk-field">
              <label className="mk-label" htmlFor="mk-lang">Language</label>
              <select id="mk-lang" className="in" value={d.language} onChange={(e) => s.set("language", e.target.value)}>
                {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </div>
          )}
        </div>
        <p className="mk-help">{model === "ace15" ? "ACE-Step takes tempo and key as real controls (120 BPM and C major when left to choose)." :
          "Tempo and key are written into the style as hints; the model usually follows them, and the analysis tells you what it actually did."}</p>
        <div className="mk-row">
          <span className="mk-label">Takes at a time</span>
          <Segmented size="sm" label="Takes" value={d.takes} onChange={(v) => s.set("takes", v)}
            options={[1, 2, 3, 4].map((n) => ({ value: n, label: String(n) }))} />
        </div>
      </Disclosure>

      {yue && (
        <Disclosure id="engine" title="Engine room" hint="exact YuE2 settings">
          <EngineRoom />
        </Disclosure>
      )}

      <div className="mk-go">
        {error && <p className="mk-error">{error}</p>}
        <Button kind="primary" size="lg" busy={making} disabled={!!why || making} onClick={make} title={why ?? undefined}>
          {why ?? `Make ${d.takes === 1 ? "a take" : `${d.takes} takes`}`}
        </Button>
        <span className="mk-go-hint">{MODELS[model].name} · about {minutes} min{yue && d.influences.length ? ` · ${d.influences.length} influence${d.influences.length > 1 ? "s" : ""}` : ""}</span>
      </div>

      {matching && <MatchSound initial={matching.text} fromIdea={matching.fromIdea} onClose={() => setMatching(null)} />}
      {picking && (
        <InfluencePicker library={s.library} picked={d.influences.map((x) => x.id)} onClose={() => setPicking(false)}
          onPick={(inf) => {
            s.set("influences", [...d.influences, { id: inf.id, strength: inf.recommended }]);
            if (d.plan === "free") s.set("plan", "full");
            setPicking(false);
          }} />
      )}
    </div>
  );
}

/** Cover a song: which song (uploaded, or one of yours), and what of it to keep. SheetSage2 writes its melody down
 *  (and its chords, with "Melody and chords"); YuE2 sings your words, in your style, to that. */
function CoverSource() {
  const s = useSong();
  const p = s.project!;
  const ref = p.reference;
  const keep = s.doc.covering?.keep ?? "melody";
  const [songs, setSongs] = useState<Listed[]>([]);
  const [choosing, setChoosing] = useState(!ref);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pick = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api.get<Listed[]>("/api/projects").then((xs) => setSongs(xs.filter((x) => x.id !== p.id && x.master?.status === "ready")))
      .catch(() => setSongs([]));
  }, [p.id]);
  useEffect(() => setChoosing(!ref), [ref?.id]);

  const run = async (what: string, fn: () => Promise<Project>) => {
    setBusy(what);
    setError(null);
    try {
      await s.saveNow();
      s.onProject(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  const upload = (file: File) => run("upload", async () => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`/api/projects/${p.id}/reference`, { method: "POST", body: form });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new ApiError(body.detail ?? "The song didn't upload.", r.status);
    return body as Project;
  });
  const fmt = (t: number) => `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`;

  return (
    <div className="cv-src">
      {ref && !choosing ? (
        <>
          <div className="cv-ref">
            <strong>{ref.name}</strong>
            <span>{fmt(ref.seconds)} · {ref.from === "song" ? "one of your songs" : "uploaded"}</span>
            <Button size="sm" kind="ghost" onClick={() => setChoosing(true)}>Change</Button>
            <audio src={fileUrl(p.id, ref.file)} controls preload="none" />
          </div>
          {ref.from === "song" && ref.hasWords && (
            <div className="cv-pick">
              <Button size="sm" busy={busy === "words"} disabled={!!busy}
                onClick={() => void run("words", () => api.post<Project>(`/api/projects/${p.id}/reference/words`))}>
                Use its words
              </Button>
              <span className="mk-help">Puts that song's lyrics on this song's lyric sheet, to sing in a new style.</span>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="cv-pick">
            <Button size="sm" busy={busy === "upload"} disabled={!!busy} onClick={() => pick.current?.click()}>Upload a song…</Button>
            <input ref={pick} type="file" accept=".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,audio/*" hidden
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
            {songs.length > 0 && (
              <select className="in" value="" disabled={!!busy} aria-label="One of your songs"
                onChange={(e) => e.target.value && void run("song", () => api.post<Project>(`/api/projects/${p.id}/reference/song`, { projectId: e.target.value }))}>
                <option value="">…or one of your songs</option>
                {songs.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
              </select>
            )}
            {ref && <Button size="sm" kind="ghost" onClick={() => setChoosing(false)}>Keep {ref.name}</Button>}
          </div>
          {busy === "upload" && <span className="mk-help">Uploading and reading it…</span>}
        </>
      )}
      <div className="mk-row">
        <span className="mk-label">Keep from it</span>
        <Segmented size="sm" label="Keep from it" value={keep} onChange={(v) => s.set("covering", { keep: v })}
          options={[
            { value: "melody", label: "The melody", hint: "Its tune; the band plays it your way (best for covers)" },
            { value: "full", label: "Melody and chords", hint: "Its tune and its harmony, closer to the original" },
          ]} />
      </div>
      <p className="mk-help">
        {keep === "melody" ? "SheetSage2 writes down its tune; YuE2 sings your words to it, in the style you chose, and finds its own chords." :
          "SheetSage2 writes down its tune and chords; YuE2 sings your words over that harmony, in the style you chose."}
        {" "}Your lyrics should follow its shape (verse, chorus…) to fit the melody well.
      </p>
      {error && <p className="mk-error">{error}</p>}
    </div>
  );
}

function InfluenceChip(props: { name: string; kind: string; strength: number; max: number; recommended: number; onChange: (v: number) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="inf-chip">
      <Chip on tone="var(--c-video)" onClick={() => setOpen(!open)} onRemove={props.onRemove}>
        <span className="inf-kind">{props.kind}</span> {props.name} <span className="inf-amt">{Math.round(props.strength * 100)}%</span>
      </Chip>
      {open && (
        <div className="inf-pop">
          <Slider label="Strength" value={props.strength} min={0.05} max={props.max} step={0.05} defaultValue={props.recommended}
            left="A hint" right="Strong" format={(v) => `${Math.round(v * 100)}%`} onChange={props.onChange} />
        </div>
      )}
    </span>
  );
}

function InfluencePicker({ library, picked, onPick, onClose }: { library: Influence[]; picked: string[]; onPick: (i: Influence) => void; onClose: () => void }) {
  const [q, setQ] = useState("");
  const shown = library.filter((i) => !picked.includes(i.id) && `${i.name} ${i.kind} ${i.about}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Modal title="Add an influence" onClose={onClose}>
      <p className="ip-lead">Influences are trained styles, genres or artists that YuE2 leans toward. Add one, then set how strongly it pulls.</p>
      <input className="in" autoFocus placeholder="Search influences" value={q} onChange={(e) => setQ(e.target.value)} />
      <ul className="ip-list">
        {shown.map((i) => (
          <li key={i.id}>
            <button type="button" className="ip-item" onClick={() => onPick(i)}>
              <span className="ip-kind">{i.kind}</span>
              <span className="ip-name">{i.name}</span>
              <span className="ip-about">{i.about}</span>
              <span className="ip-rec">starts at {Math.round(i.recommended * 100)}%</span>
            </button>
          </li>
        ))}
        {shown.length === 0 && <li className="ip-none">{library.length ? "Nothing matches." : "No influences in the library yet."}</li>}
      </ul>
      <details className="ip-own">
        <summary>
          <strong>Add your own</strong>
          <span>A LoRA you trained, or one from Hugging Face</span>
        </summary>
        <AddInfluence onAdded={async (i) => {
          const lib = await useSong.getState().refreshLibrary();
          const fresh = lib.find((x) => x.id === i.id);
          if (fresh && fresh.models.includes("yue2")) onPick(fresh);
          else onClose();
        }} />
      </details>
    </Modal>
  );
}

function EngineRoom() {
  const s = useSong();
  const d = s.doc;
  const composed = [
    d.sung ? d.language : "", d.sung && d.voice ? `${d.voice === "duet" ? "male and female duet vocals" : `${d.voice} vocal`}` : "",
    ...d.genres, d.instruments.trim(), ...d.moods, d.extra.trim(), d.sung ? "" : "instrumental, no vocals",
    d.tempo ? `${d.tempo} BPM` : "", d.key ?? "",
  ].filter(Boolean).join(", ");
  const setEngine = (k: string, v: number | null) => s.set("engine", { ...d.engine, [k]: v });
  return (
    <>
      <div className="mk-field">
        <span className="mk-label">The style YuE2 reads</span>
        <TextArea value={d.styleOverride ?? composed} minRows={2} onChange={(e) => s.set("styleOverride", e.target.value === composed ? null : e.target.value)} />
        <p className="mk-help">
          {d.styleOverride ? <>Your own wording is used. <button type="button" className="mk-link" onClick={() => s.set("styleOverride", null)}>Go back to the composed style</button></> :
            "Built from your choices above, in YuE2's order. Type here to use your own wording instead."}
        </p>
      </div>
      <div className="mk-field">
        <span className="mk-label">Extra style words</span>
        <input className="in" value={d.extra} placeholder="e.g. tape saturation, wide stereo, live room" onChange={(e) => s.set("extra", e.target.value)} />
      </div>
      <div className="mk-field">
        <label className="mk-label" htmlFor="mk-seed">Seed</label>
        <div className="mk-inline">
          <input id="mk-seed" className="in mk-num mk-seed" type="number" min={0} placeholder="new each take" value={d.seed ?? ""}
            onChange={(e) => s.set("seed", e.target.value ? Math.max(0, Math.floor(Number(e.target.value))) : null)} />
          {d.seed !== null && <button type="button" className="mk-link" onClick={() => s.set("seed", null)}>clear</button>}
        </div>
        <p className="mk-help">Empty gives every take a fresh seed. A seed with the same settings repeats a take on this machine; with several takes, they use it and the seeds after it.</p>
      </div>
      {ENGINE.map((group) => (
        <div key={group.stage} className="er-group">
          <h4>{group.stage}</h4>
          <div className="er-grid">
            {group.fields.map((f) => {
              const v = d.engine[f.key];
              return (
                <label key={f.key} className={"er-f" + (v !== null && v !== undefined ? " er-set" : "")}>
                  <span>{f.label}</span>
                  <input className="in" type="number" min={f.min} max={f.max} step={f.step}
                    placeholder={f.key === "seconds" ? "by length" : String(f.def)} value={v ?? ""}
                    onChange={(e) => setEngine(f.key, e.target.value === "" ? null : Number(e.target.value))} />
                </label>
              );
            })}
          </div>
        </div>
      ))}
      <p className="mk-help">Empty fields use YuE2's defaults (shown faintly). Creativity and Variety above are the singing stage's temperature and repetition penalty.</p>
    </>
  );
}
