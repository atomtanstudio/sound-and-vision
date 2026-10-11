import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { go } from "../lib/router";
import type { Project } from "../lib/types";
import { Button, Segmented } from "../ui/controls";
import "./promptbox.css";

const EXAMPLES = [
  "A slow-burning soul ballad about the last bus home, warm Rhodes, a tired but hopeful female voice",
  "Upbeat 80s synthwave about driving to the coast at dawn with your best friend, big gated drums",
  "Dark industrial electro, 124 BPM, distorted bass, a chanting male voice, something about temptation",
  "A sea shanty for a lighthouse keeper who talks to passing ships",
  "Paste lyrics, a mood, a scene, or a description of a sound…",
];

/** Suno-style: type (or paste) anything, press Create, and two songs start at once. */
export function PromptBox() {
  const [text, setText] = useState("");
  const [takes, setTakes] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [example, setExample] = useState(0);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (text) return;
    const id = window.setInterval(() => setExample((i) => (i + 1) % EXAMPLES.length), 4500);
    return () => window.clearInterval(id);
  }, [text]);

  async function create() {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ project: Project }>("/api/quick", { prompt: text, takes });
      go(`/music/${r.project.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className={"pbx" + (text ? " pbx-on" : "")}>
      <textarea
        ref={ref}
        className="pbx-text"
        value={text}
        rows={3}
        placeholder={EXAMPLES[example]}
        aria-label="Describe a song"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void create();
        }}
      />
      <div className="pbx-bar">
        <span className="pbx-hint">An idea, a vibe, lyrics, or a description of a sound. We write it, then YuE2 sings it.</span>
        <Segmented size="sm" label="How many songs" value={takes} onChange={setTakes}
          options={[1, 2, 4].map((n) => ({ value: n, label: n === 1 ? "1 song" : `${n} songs` }))} />
        <Button kind="primary" size="md" disabled={!text.trim()} busy={busy} onClick={create} title="⌘↵">
          Create
        </Button>
      </div>
      {error && <p className="pbx-error">{error}</p>}
    </div>
  );
}
