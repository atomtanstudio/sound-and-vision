import { useState } from "react";
import { api, ApiError } from "../lib/api";
import type { Influence } from "../lib/types";
import { Button, Segmented } from "../ui/controls";
import { Machine, machine } from "../lib/machine";

interface Inspected {
  model: string | null;
  rank: number | null;
  trigger: string | null;
  name: string | null;
  loraTensors: number;
}

const MODELS = [
  { value: "yue2", label: "YuE2" },
  { value: "ace15", label: "ACE-Step 1.5" },
  { value: "music3", label: "MiniMax Music 3" },
];
const KINDS = ["Style", "Genre", "Artist"] as const;
const HEADER_BYTES = 16 * 1024 * 1024; // the header sits at the start; that's enough to read it

/** Bring your own LoRA: a .safetensors file, or a Hugging Face link the server downloads. */
export function AddInfluence({ onAdded }: { onAdded: (i: Influence) => void }) {
  const [how, setHow] = useState<"file" | "link">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [seen, setSeen] = useState<Inspected | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<(typeof KINDS)[number]>("Style");
  const [about, setAbout] = useState("");
  const [model, setModel] = useState<string>("yue2");
  const [busy, setBusy] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function pick(f: File | null) {
    setFile(f);
    setSeen(null);
    setError(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".safetensors")) {
      setError("Only .safetensors files can be added (other formats can run code when loaded).");
      return;
    }
    setBusy("inspect");
    try {
      const form = new FormData();
      form.append("file", f.slice(0, HEADER_BYTES), f.name);
      const res = await fetch("/api/influences/inspect", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Couldn't read that file.");
      setSeen(data);
      if (data.model) setModel(data.model);
      setName(data.name || f.name.replace(/\.safetensors$/i, "").replace(/[_-]+/g, " "));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function upload() {
    if (!file) return;
    setBusy("add");
    setError(null);
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("name", name);
    form.append("kind", kind);
    form.append("about", about);
    form.append("model", model);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/influences/upload");
    xhr.upload.onprogress = (e) => e.lengthComputable && setProgress(e.loaded / e.total);
    xhr.onload = () => {
      setBusy(null);
      const data = JSON.parse(xhr.responseText || "{}");
      if (xhr.status >= 300) setError(data.detail || "That didn't work.");
      else onAdded(data);
    };
    xhr.onerror = () => {
      setBusy(null);
      setError(`The upload didn't reach ${machine()}.`);
    };
    xhr.send(form);
  }

  async function fromLink() {
    setBusy("add");
    setError(null);
    try {
      onAdded(await api.post<Influence>("/api/influences/from-url", { url, name, kind, about, model: model || null }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const ready = how === "file" ? !!file && !!seen && !!name.trim() : !!url.trim();
  return (
    <div className="ai">
      <Segmented size="sm" label="Where it comes from" value={how} onChange={(v) => { setHow(v); setError(null); }}
        options={[{ value: "file", label: "A file I have" }, { value: "link", label: "A Hugging Face link" }]} />
      {how === "file" ? (
        <label className="ai-drop">
          <input type="file" accept=".safetensors" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
          <span>{file ? file.name : "Choose a .safetensors file"}</span>
          {file && <em>{(file.size / 1024 / 1024).toFixed(0)} MB</em>}
        </label>
      ) : (
        <input className="in" placeholder="https://huggingface.co/…/resolve/main/….safetensors" value={url} onChange={(e) => setUrl(e.target.value)} />
      )}
      {busy === "inspect" && <p className="ai-note">Reading the file…</p>}
      {seen && (
        <p className="ai-note">
          A LoRA{seen.rank ? ` (rank ${seen.rank})` : ""}
          {seen.model ? <>, made for <strong>{MODELS.find((m) => m.value === seen.model)?.label}</strong></> : ", for a model it doesn't say"}
          {seen.trigger ? <>; trigger word <code>{seen.trigger}</code></> : ""}.
        </p>
      )}
      {(seen || how === "link") && (
        <div className="ai-form">
          <label>
            <span>Name</span>
            <input className="in" value={name} placeholder={how === "link" ? "from the file if empty" : ""} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="ai-row">
            <label>
              <span>It's a…</span>
              <Segmented size="sm" label="Kind" value={kind} onChange={setKind} options={KINDS.map((k) => ({ value: k, label: k }))} />
            </label>
            <label>
              <span>For</span>
              <select className="in" value={model} onChange={(e) => setModel(e.target.value)}>
                {MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
          </div>
          <label>
            <span>What it does (for you, later)</span>
            <input className="in" value={about} placeholder="warm 70s soul horns and tape hiss" onChange={(e) => setAbout(e.target.value)} />
          </label>
        </div>
      )}
      {error && <p className="mk-error">{error}</p>}
      <div className="ai-go">
        {busy === "add" && how === "file" && <span className="ai-note">Uploading {Math.round(progress * 100)}%</span>}
        {busy === "add" && how === "link" && <span className="ai-note">{Machine()} is downloading it…</span>}
        <Button kind="primary" disabled={!ready || !!busy} busy={busy === "add"} onClick={how === "file" ? upload : fromLink}>
          Add to my influences
        </Button>
      </div>
    </div>
  );
}
