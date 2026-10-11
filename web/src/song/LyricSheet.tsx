import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { LyricSection, SectionKind } from "../lib/types";
import { label, lyricsText, parseLyrics, sectionId, useSong } from "../state/song";
import { Button, Modal, TextArea } from "../ui/controls";
import { SECTION_KINDS, soundSummary } from "./sound";

interface WriteResult<T> {
  result: T;
  by: { provider: string; name: string; model: string | null };
}

/** The song's words as section blocks, written by the user, the writer, or both. */
export function LyricSheet() {
  const { doc, project, set, setTitle } = useSong();
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [paste, setPaste] = useState("");
  const sections = doc.sections;

  const song = () => ({
    title: project?.title && project.title !== "Untitled song" ? project.title : "",
    idea: doc.idea,
    sound: soundSummary(doc),
    length: doc.length,
    language: doc.language,
    sections: sections.map((s) => ({ kind: s.kind, label: label(s.kind), lines: s.text.split("\n").filter((l) => l.trim()) })),
  });

  async function writeAll() {
    setBusy("all");
    setError(null);
    try {
      // the sheet's sections go along even when empty: a laid-out form (yours, or a matched song's) is written into as is
      const r = await api.post<WriteResult<{ title: string; sections: { kind: SectionKind; lines: string[] }[] }>>("/api/write", {
        task: "song",
        song: song(),
      });
      set("sections", r.result.sections.map((s) => ({ id: sectionId(), kind: s.kind, text: s.lines.join("\n") })));
      if (r.result.title && (!project?.title || project.title === "Untitled song")) setTitle(r.result.title);
      setNote(`Written by ${r.by.name}${r.by.model ? ` (${r.by.model})` : ""}. Change anything you like.`);
      if (!doc.genres.length && !doc.moods.length && !doc.instruments.trim()) void suggestSound();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function suggestSound() {
    try {
      const r = await api.post<WriteResult<{ genres: string[]; moods: string[]; instruments: string; voice: string | null; tempo: number | null }>>(
        "/api/write",
        { task: "sound", song: song() },
      );
      const s = useSong.getState().doc;
      if (!s.genres.length) set("genres", r.result.genres.map((g) => g.toLowerCase()));
      if (!s.moods.length) set("moods", r.result.moods.map((m) => m.toLowerCase()));
      if (!s.instruments.trim() && r.result.instruments) set("instruments", r.result.instruments);
      if (!s.voice && r.result.voice) set("voice", r.result.voice as "female" | "male" | "duet");
      if (!s.tempo && r.result.tempo) set("tempo", r.result.tempo);
    } catch {
      /* the sound stays the user's to choose */
    }
  }

  async function rewrite(i: number) {
    const s = sections[i];
    setBusy(s.id);
    setError(null);
    try {
      const r = await api.post<WriteResult<{ lines: string[] }>>("/api/write", {
        task: "section",
        song: song(),
        target: { kind: s.kind, label: label(s.kind), lines: s.text.split("\n").filter((l) => l.trim()) },
      });
      update(i, { text: r.result.lines.join("\n") });
      setNote(`${label(s.kind)} rewritten by ${r.by.name}.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const update = (i: number, patch: Partial<LyricSection>) =>
    set("sections", sections.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const remove = (i: number) => set("sections", sections.filter((_, j) => j !== i));
  const add = (kind: SectionKind, after = sections.length - 1) => {
    const next = [...sections];
    next.splice(after + 1, 0, { id: sectionId(), kind, text: "" });
    set("sections", next);
  };
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= sections.length) return;
    const next = [...sections];
    [next[i], next[j]] = [next[j], next[i]];
    set("sections", next);
  };

  return (
    <div className="ls">
      <div className="ls-actions">
        <Button kind="primary" size="sm" busy={busy === "all"} disabled={!!busy || !doc.idea.trim()} onClick={writeAll}
          title={doc.idea.trim() ? undefined : "Say what it's about first"}>
          {sections.some((s) => s.text.trim()) ? "Make the words better" : "Write the words for me"}
        </Button>
        <Button kind="ghost" size="sm" onClick={() => setPasting(true)}>
          Paste lyrics
        </Button>
        {sections.length > 0 && (
          <Button kind="ghost" size="sm" onClick={() => navigator.clipboard.writeText(lyricsText(sections))}>
            Copy
          </Button>
        )}
      </div>
      {note && <p className="ls-note">{note}</p>}
      {error && <p className="ls-error">{error}</p>}

      {sections.length === 0 ? (
        <div className="ls-empty">
          <p>No words yet. Let the writer draft them from your idea, paste your own, or start a section.</p>
          <div className="ls-starts">
            {(["verse", "chorus"] as const).map((k) => (
              <Button key={k} size="sm" onClick={() => add(k)}>
                + {label(k)}
              </Button>
            ))}
          </div>
        </div>
      ) : (
        <ol className="ls-sections">
          {sections.map((s, i) => (
            <li key={s.id} className={`ls-sec ls-${s.kind}`}>
              <div className="ls-sec-head">
                <select value={s.kind} onChange={(e) => update(i, { kind: e.target.value as SectionKind })} aria-label="Section">
                  {SECTION_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {label(k)}
                    </option>
                  ))}
                </select>
                <span className="ls-sec-tools">
                  <button type="button" className="ls-rewrite" title="Rewrite this section" disabled={!!busy || s.kind === "instrumental"} onClick={() => rewrite(i)}>
                    {busy === s.id ? "Rewriting…" : "Rewrite"}
                  </button>
                  <button type="button" title="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                    ↑
                  </button>
                  <button type="button" title="Move down" disabled={i === sections.length - 1} onClick={() => move(i, 1)}>
                    ↓
                  </button>
                  <button type="button" title="Remove" onClick={() => remove(i)}>
                    ×
                  </button>
                </span>
              </div>
              {s.kind === "instrumental" ? (
                <p className="ls-inst">A break with no singing.</p>
              ) : (
                <TextArea
                  value={s.text}
                  minRows={2}
                  placeholder={s.kind === "chorus" ? "The hook, the lines everyone sings back…" : "Lines to sing, one per line"}
                  onChange={(e) => update(i, { text: e.target.value })}
                />
              )}
            </li>
          ))}
        </ol>
      )}
      {sections.length > 0 && (
        <div className="ls-add">
          {(["verse", "pre-chorus", "chorus", "bridge", "instrumental", "outro"] as const).map((k) => (
            <button key={k} type="button" onClick={() => add(k)}>
              + {label(k)}
            </button>
          ))}
        </div>
      )}

      {pasting && (
        <Modal title="Paste lyrics" onClose={() => setPasting(false)}>
          <p className="ls-hint">
            Section names in square brackets ([Verse], [Chorus]) are kept; plain verses separated by blank lines become verses.
          </p>
          <TextArea value={paste} minRows={10} onChange={(e) => setPaste(e.target.value)} placeholder={"[Verse]\n…\n\n[Chorus]\n…"} />
          <div className="ls-modal-actions">
            <Button kind="primary" disabled={!paste.trim()} onClick={() => {
              set("sections", parseLyrics(paste));
              setPasting(false);
              setPaste("");
            }}>
              Use these words
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
