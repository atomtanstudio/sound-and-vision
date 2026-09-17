import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { AudioLines, Mic2, RefreshCw, FolderOpen } from "lucide-react";
import { request } from "./api";
import type { SongForm } from "./model";
import "./trained-styles.css";

export type LoraSelection = { id: string; sha256: string; strength: number };
export type SavedLora = LoraSelection & {
  name: string;
  kind: "style" | "artist";
  step: number | null;
  trigger: string;
};
type Checkpoint = {
  id: string;
  sha256: string;
  label: string;
  step: number | null;
};
type Group = {
  id: string;
  name: string;
  kind: "style" | "artist";
  trigger: string;
  preferredStep: number | null;
  checkpoints: Checkpoint[];
  generation: {
    cot?: SongForm["cot"];
    cfg_scale?: number;
    ode_steps?: number;
  };
};
type Catalog = {
  folder: string;
  groups: Group[];
  issues: { filename: string; message: string }[];
};

export function LoraBadge({ lora }: { lora: SavedLora }) {
  const Icon = lora.kind === "artist" ? Mic2 : AudioLines;
  return (
    <span
      className={`lora-badge lora-${lora.kind}`}
      title={`${lora.kind === "artist" ? "Artist" : "Style"} · Strength ${lora.strength}`}
    >
      <Icon size={12} aria-hidden="true" />
      {lora.name}
      {lora.step !== null ? ` · ${lora.step}` : ""}
    </span>
  );
}

export function TrainedStyles({
  form,
  change,
  connected,
}: {
  form: SongForm;
  change: Dispatch<SetStateAction<SongForm>>;
  connected: boolean;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void request<Catalog>("/loras")
      .then((data) => {
        if (!disposed) {
          setCatalog(data);
          setError("");
        }
      })
      .catch(() => {
        if (!disposed)
          setError("Connect to the music server to scan trained styles.");
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [connected, refresh]);

  const group = catalog?.groups.find((g) =>
    g.checkpoints.some((c) => c.id === form.lora?.id),
  );
  const checkpoint = group?.checkpoints.find((c) => c.id === form.lora?.id);
  const unavailable =
    !!form.lora && (!checkpoint || checkpoint.sha256 !== form.lora.sha256);
  const Icon = group?.kind === "artist" ? Mic2 : AudioLines;
  function selectGroup(id: string) {
    const next = catalog?.groups.find((g) => g.id === id);
    if (!next) {
      change((f) => ({ ...f, lora: null }));
      return;
    }
    const selected =
      next.checkpoints.find((c) => c.step === next.preferredStep) ??
      next.checkpoints.at(-1)!;
    const defaults = next.generation;
    change((f) => ({
      ...f,
      lora: { id: selected.id, sha256: selected.sha256, strength: 1 },
      cot: defaults.cot ?? f.cot,
      cfg_scale:
        defaults.cfg_scale === undefined
          ? f.cfg_scale
          : String(defaults.cfg_scale),
      ode_steps: defaults.ode_steps ?? f.ode_steps,
      planFirst: defaults.cot === "off" ? false : f.planFirst,
    }));
  }
  return (
    <section
      className="trained-styles"
      aria-label="Trained styles and artists"
      aria-busy={loading}
    >
      <div className="trained-heading">
        <label htmlFor="trained-style">Trained styles &amp; artists</label>
        <button
          type="button"
          className="icon-button"
          aria-label="Refresh trained styles"
          title="Scan the LoRA folder"
          disabled={loading}
          onClick={() => setRefresh((n) => n + 1)}
        >
          <RefreshCw size={12} />
        </button>
      </div>
      <div className={`trained-select lora-${group?.kind || "none"}`}>
        <Icon size={16} aria-hidden="true" />
        <select
          id="trained-style"
          value={group?.id || (form.lora ? "unavailable" : "")}
          onChange={(e) => selectGroup(e.target.value)}
          disabled={loading && !catalog}
        >
          <option value="">Original model · no LoRA</option>
          {form.lora && !group && (
            <option value="unavailable" disabled>
              Selected LoRA unavailable
            </option>
          )}
          {(["style", "artist"] as const).map((kind) => {
            const groups = catalog?.groups.filter((g) => g.kind === kind) || [];
            return groups.length ? (
              <optgroup
                key={kind}
                label={kind === "style" ? "Styles" : "Artists"}
              >
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </optgroup>
            ) : null;
          })}
        </select>
        {group && (
          <span className="trained-kind">
            {group.kind === "artist" ? "Artist" : "Style"}
          </span>
        )}
      </div>
      {group && form.lora && (
        <>
          <div className="trained-controls">
            <label>
              Checkpoint
              <select
                aria-label="LoRA checkpoint"
                value={form.lora.id}
                onChange={(e) => {
                  const next = group.checkpoints.find(
                    (c) => c.id === e.target.value,
                  )!;
                  change((f) => ({
                    ...f,
                    lora: {
                      id: next.id,
                      sha256: next.sha256,
                      strength: f.lora?.strength ?? 1,
                    },
                  }));
                }}
              >
                {group.checkpoints.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Strength
              <input
                aria-label="LoRA strength"
                type="number"
                min="0.1"
                max="2"
                step="0.1"
                value={
                  Number.isNaN(form.lora.strength) ? "" : form.lora.strength
                }
                onChange={(e) => {
                  const strength = e.target.valueAsNumber;
                  change((f) => ({
                    ...f,
                    lora: f.lora ? { ...f.lora, strength } : null,
                  }));
                }}
              />
            </label>
          </div>
          <p className="trained-note">
            {group.trigger ? (
              <>
                Trigger <code>{group.trigger}</code> added automatically.
              </>
            ) : (
              "No trigger supplied. Add one to this folder’s lora.json if needed."
            )}
          </p>
          {group.generation.cot && (
            <p className="trained-note">
              {form.cot === "off"
                ? "No score plan"
                : form.cot === "full"
                  ? "Melody & chords"
                  : "Melody only"}{" "}
              · Guidance {form.cfg_scale || "default"}. Adjust in Advanced.
            </p>
          )}
        </>
      )}
      {!loading && unavailable && (
        <p className="trained-error" role="alert">
          This checkpoint is missing or changed. Refresh and select it again, or
          choose the original model.
        </p>
      )}
      {error && (
        <p className="trained-note" role="status">
          {error}
        </p>
      )}
      {catalog && (
        <details className="trained-folder">
          <summary>
            <FolderOpen size={12} />{" "}
            {catalog.groups.length ? "LoRA folder" : "Add your trained LoRAs"}
            {catalog.issues.length ? ` · ${catalog.issues.length} skipped` : ""}
          </summary>
          <p>
            Place compatible YuE2 <code>.safetensors</code> files here, then
            refresh this page or use the scan button.
          </p>
          <code className="trained-path">{catalog.folder}</code>
          <p>
            Use one folder per style under <code>styles/</code> or per artist
            under <code>artists/</code>. An optional <code>lora.json</code>{" "}
            supplies its name and trigger.
          </p>
          {catalog.issues.map((issue) => (
            <p key={issue.filename} className="trained-error">
              {issue.filename}: {issue.message}
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
