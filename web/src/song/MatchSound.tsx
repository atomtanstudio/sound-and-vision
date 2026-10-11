import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { SectionKind, SongDoc } from "../lib/types";
import { label, sectionId, useSong } from "../state/song";
import { Button, Chip, Modal, TextArea } from "../ui/controls";

export interface Matched {
  genres: string[];
  moods: string[];
  instruments: string;
  production: string;
  voice: "female" | "male" | "duet" | "none" | null;
  vocalStyle: string;
  tempo: number | null;
  key: string | null;
  theme: string;
  summary: string;
  structure: { kind: SectionKind; start: string }[];
  seconds: number | null;
}

/** What to ask an AI that can listen to a song, so its answer reads straight into the app. */
export const LISTEN_PROMPT = `Listen to this song and describe its sound so another AI music model can make a NEW, original song in the same style. Don't quote any lyrics. Answer in exactly this format:

GENRES: 1–4 genres, the most distinctive first
MOODS: 1–4 single words
TEMPO: the BPM · KEY: e.g. A minor · TIME SIGNATURE: e.g. 4/4
LENGTH: the song's length (m:ss)
VOICE: female / male / duet / no vocals — VOCAL STYLE: how it's sung and processed
INSTRUMENTS: the actual sound sources (e.g. distorted sawtooth bass, 808 kick, Rhodes piano)
PRODUCTION: mix, effects and arrangement tricks (e.g. sidechain pumping, tape stops, glitch stutters)
STRUCTURE: one line per section, in order, with its start time (e.g. Intro 0:00, Verse 0:16, Chorus 0:48…)
ENERGY: how the intensity moves through the song
THEME: what it's about in one sentence (no lyrics)`;

const LENGTH_FROM = (s: number | null): SongDoc["length"] | null => (s ? (s < 150 ? "short" : s < 300 ? "song" : "long") : null);

/** Turn a description of a sound (from Gemini, a review, your notes) into the song's sound settings. */
export function MatchSound({ initial = "", onClose, fromIdea = false }: { initial?: string; onClose: () => void; fromIdea?: boolean }) {
  const s = useSong();
  const [text, setText] = useState(initial);
  const [found, setFound] = useState<Matched | null>(null);
  const [by, setBy] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [useTheme, setUseTheme] = useState(fromIdea || !s.doc.idea.trim());
  const [useForm, setUseForm] = useState(true);

  async function read() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ result: Matched; by: { name: string } }>("/api/write", { task: "match", text });
      setFound(r.result);
      setBy(r.by.name);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function apply() {
    if (!found) return;
    const set = s.set;
    set("genres", found.genres);
    set("moods", found.moods);
    set("instruments", found.instruments);
    set("extra", [found.production, found.vocalStyle].filter(Boolean).join(", "));
    if (found.voice === "none") set("sung", false);
    else {
      set("sung", true);
      set("voice", found.voice === "female" || found.voice === "male" || found.voice === "duet" ? found.voice : null);
    }
    if (found.tempo) set("tempo", found.tempo);
    set("key", found.key);
    const length = LENGTH_FROM(found.seconds);
    if (length) set("length", length);
    set("soundNotes", text);
    if (useTheme && found.theme) set("idea", found.theme);
    if (useForm && found.structure.length > 1 && !s.doc.sections.some((x) => x.text.trim())) {
      set("sections", found.structure.map((x) => ({ id: sectionId(), kind: x.kind, text: "" })));
    }
    onClose();
  }

  return (
    <Modal title="Match a sound" onClose={onClose} wide>
      {!found ? (
        <>
          <p className="ms-lead">
            Paste a description of the sound you're after: from an AI that can listen to a song, a review, or your own notes. The
            writer turns it into this song's sound. The words and melody stay new and yours.
          </p>
          <TextArea value={text} minRows={8} placeholder="Dark electro-pop at about 124 BPM, distorted sawtooth bass, glitchy pitched-down vocal chops…"
            onChange={(e) => setText(e.target.value)} />
          <details className="ms-tip">
            <summary>Asking an AI that can listen? Use this prompt for the best match</summary>
            <p>Give it the song (a link or the file) with this prompt, then paste its whole answer above. Asking for the structure
              lets the app lay out your lyric sheet in the same form.</p>
            <pre className="tc-pre">{LISTEN_PROMPT}</pre>
            <Button size="sm" onClick={() => navigator.clipboard.writeText(LISTEN_PROMPT).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy the prompt"}
            </Button>
          </details>
          {error && <p className="mk-error">{error}</p>}
          <div className="ms-go">
            <Button kind="primary" disabled={text.trim().length < 20} busy={busy} onClick={read}>Read it</Button>
          </div>
        </>
      ) : (
        <>
          <p className="ms-summary">{found.summary}</p>
          <dl className="ms-found">
            <dt>Genres</dt>
            <dd className="ms-chips">{found.genres.map((g) => <Chip key={g} on>{g}</Chip>)}</dd>
            <dt>Mood</dt>
            <dd className="ms-chips">{found.moods.map((m) => <Chip key={m} on tone="var(--c-graphics)">{m}</Chip>)}</dd>
            <dt>Instruments</dt>
            <dd>{found.instruments || "—"}</dd>
            <dt>Production</dt>
            <dd>{found.production || "—"}</dd>
            <dt>Voice</dt>
            <dd>{found.voice === "none" ? "No vocals (instrumental)" : `${found.voice ?? "Either"}${found.vocalStyle ? `: ${found.vocalStyle}` : ""}`}</dd>
            <dt>Tempo · key</dt>
            <dd>{found.tempo ? `${found.tempo} BPM` : "—"} · {found.key ?? "let it choose"}{found.seconds ? ` · about ${Math.floor(found.seconds / 60)}:${String(found.seconds % 60).padStart(2, "0")} long` : ""}</dd>
            {found.structure.length > 1 && (
              <>
                <dt>Form</dt>
                <dd>{found.structure.map((x) => label(x.kind)).join(" → ")}</dd>
              </>
            )}
            <dt>An idea</dt>
            <dd>{found.theme}</dd>
          </dl>
          <div className="ms-opts">
            <label><input type="checkbox" checked={useTheme} onChange={(e) => setUseTheme(e.target.checked)} /> Use the idea for this song</label>
            {found.structure.length > 1 && (
              <label>
                <input type="checkbox" checked={useForm} disabled={s.doc.sections.some((x) => x.text.trim())} onChange={(e) => setUseForm(e.target.checked)} />{" "}
                Lay out the lyric sheet in this form{s.doc.sections.some((x) => x.text.trim()) ? " (your words are kept instead)" : ""}
              </label>
            )}
          </div>
          <p className="ms-by">Read by {by}. You can change anything afterwards.</p>
          <div className="ms-go">
            <Button kind="ghost" onClick={() => setFound(null)}>Back</Button>
            <Button kind="primary" onClick={apply}>Use this sound</Button>
          </div>
        </>
      )}
    </Modal>
  );
}

/** Does this text read like a description of a sound rather than what a song is about? */
export function looksLikeSound(text: string): boolean {
  if (text.length < 160) return false;
  const hits = (text.match(/\b(bpm|tempo|genre|synth|bass|kick|snare|drums?|vocals?|reverb|distort\w*|groove|production|mix|darkwave|electro|techno|house|hip[- ]hop|rock|pop|ebm|glitch\w*|lo-?fi|808|four-on-the-floor)\b/gi) ?? []).length;
  return hits >= 4;
}
