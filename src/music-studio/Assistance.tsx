import { ProviderSettingsPanel } from "./ProviderSettings";
import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  ChevronDown,
  WandSparkles,
  Upload,
  FileMusic,
  X,
  LoaderCircle,
  Undo2,
} from "lucide-react";
import { request } from "./api";
import { readLocal, writeLocal, type SongForm } from "./model";
import {
  applyDescription,
  descriptionMatches,
  type DescriptionSource,
} from "./description";

export type AccountStatus = {
  provider?: "openai" | "local";
  imageProvider?: string;
  imageError?: string | null;
  available: boolean;
  connected: boolean;
  email?: string;
  plan?: string;
  images: boolean;
  models: { id: string; name: string; default: boolean }[];
  login?: {
    verificationUrl: string;
    userCode: string;
    expiresAt: number;
  } | null;
  error?: string | null;
};
type Proposal = {
  title: string;
  lyrics: string;
  style: string;
  abc: string;
  summary: string;
  ideas: { title: string; style: string; description: string }[];
};
type Job = {
  id: string;
  kind: string;
  state: string;
  error?: string;
  result?: {
    proposal?: Proposal;
    model?: string;
    input?: Record<string, unknown>;
    abc?: string;
    duration?: number;
    warnings?: string[];
  };
};
export const accountStatus = () => request<AccountStatus>("/openai/account");

export function AccountPanel({
  account,
  refresh,
}: {
  account: AccountStatus | null;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function action(path: string) {
    setBusy(true);
    setError("");
    try {
      await request(path, {});
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-body">
      <ProviderSettingsPanel refresh={refresh}>
      <p>
        Use your ChatGPT account for song ideas, lyrics, score edits, and
        available image generation.
      </p>
      <div className="connection-state">
        <span className="tiny-dot" />
        {account?.connected && account.provider !== "local" ? account.email || "Connected" : "Not connected"}
      </div>
      {account?.connected && account.provider !== "local" ? (
        <>
          <p className="field-note">
            {account.plan} · {account.models.length} available models · Cover
            art {account.images ? "available" : "unavailable"}
          </p>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void action("/openai/logout")}
          >
            Disconnect OpenAI
          </button>
        </>
      ) : account?.login ? (
        <>
          <p>Enter this code on OpenAI’s sign-in page:</p>
          <p>
            <strong className="device-code">{account.login.userCode}</strong>
          </p>
          <a
            className="secondary-button"
            href={account.login.verificationUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open OpenAI sign-in ↗
          </a>
          <p className="field-note">
            Waiting for sign-in. This page will update automatically.
          </p>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => void action("/openai/login/cancel")}
          >
            Cancel sign-in
          </button>
        </>
      ) : (
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void action("/openai/login")}
        >
          {busy ? "Starting sign-in…" : "Connect OpenAI"}
        </button>
      )}
      {(error || account?.error) && (
        <p role="alert">{error || account?.error}</p>
      )}
      <p className="field-note">
        Sign-in is saved privately on the backend for this Sound/Vision installation.
        Requests use your account’s limits.
      </p>
      </ProviderSettingsPanel>
    </div>
  );
}

function useJob(storageKey: string) {
  const [id, setId] = useState<string | null>(() =>
    readLocal(storageKey, null),
  );
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const selectedId = useRef(id);
  useEffect(() => {
    if (!id) return;
    let stopped = false,
      timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await request<Job>(`/assistance/${id}`);
        if (stopped || selectedId.current !== id) return;
        setJob(value);
        setError("");
        if (!["succeeded", "failed", "cancelled"].includes(value.state))
          timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!stopped && selectedId.current === id) {
          setError((e as Error).message);
          timer = setTimeout(poll, 5000);
        }
      }
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id]);
  function select(value: string | null) {
    selectedId.current = value;
    writeLocal(storageKey, value);
    setId(value);
    setJob(null);
    setError("");
  }
  const busy =
    !!id && (!job || !["succeeded", "failed", "cancelled"].includes(job.state));
  async function cancel() {
    if (!id) return;
    const result = await request<Job>(`/assistance/${id}/cancel`, {});
    if (selectedId.current === id) setJob(result);
  }
  return { job, id, busy, error, select, cancel };
}

export function SongDescription({
  form,
  change,
  account,
  connect,
}: {
  form: SongForm;
  change: Dispatch<SetStateAction<SongForm>>;
  account: AccountStatus | null;
  connect: () => void;
}) {
  const work = useJob("sv-description-request");
  const [starting, setStarting] = useState(false),
    [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState(""),
    [notice, setNotice] = useState("");
  const [undo, setUndo] = useState<{
    source: DescriptionSource;
    generated: string;
  } | null>(() => readLocal("sv-description-undo", null));
  const handled = useRef(""),
    submitting = useRef(false),
    latest = useRef(form);
  latest.current = form;
  function remember(source: DescriptionSource, generated: string) {
    const value = { source, generated };
    setUndo(value);
    writeLocal("sv-description-undo", value);
  }
  useEffect(() => {
    const job = work.job;
    if (
      !job ||
      handled.current === job.id ||
      !["succeeded", "failed", "cancelled"].includes(job.state)
    )
      return;
    handled.current = job.id;
    if (job.state === "succeeded") {
      const generated = job.result?.proposal?.style?.trim();
      const saved = readLocal<{ id: string; source: DescriptionSource } | null>(
        "sv-description-source",
        null,
      );
      if (!generated) setError("No description was returned. Try again.");
      else if (
        saved?.id === job.id &&
        descriptionMatches(latest.current, saved.source)
      ) {
        remember(saved.source, generated);
        change((current) => applyDescription(current, saved.source, generated));
        setNotice("Description updated.");
      } else {
        setSuggestion(generated);
        setNotice("Description ready. Your newer edits have been kept.");
      }
    } else if (job.state === "failed")
      setError(job.error || "Could not write a description. Try again.");
    else setNotice("Cancelled.");
    work.select(null);
  }, [work.job, change]);
  async function generate() {
    if (!account?.connected) {
      connect();
      return;
    }
    if (submitting.current || work.busy) return;
    submitting.current = true;
    setStarting(true);
    setError("");
    setNotice("");
    setSuggestion("");
    const source = { description: form.description, style: form.style };
    const signature = JSON.stringify(source);
    const pending = readLocal<{ id: string; signature: string } | null>(
      "sv-description-submission",
      null,
    );
    const id =
      pending?.signature === signature ? pending.id : crypto.randomUUID();
    writeLocal("sv-description-submission", { id, signature });
    writeLocal("sv-description-source", { id, source });
    try {
      const job = await request<Job>("/assistance", {
        requestId: id,
        task: "Describe song",
        prompt: source.description,
      });
      work.select(job.id);
      writeLocal("sv-description-submission", null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      submitting.current = false;
      setStarting(false);
    }
  }
  const busy = starting || work.busy;
  const canUndo =
    undo && form.description === undo.generated && form.style === "";
  return (
    <>
      <div className="field-heading">
        <label className="field-label" htmlFor="song-description">
          Describe your song
        </label>
        <button
          type="button"
          className="writer-wand"
          aria-label="Generate song description"
          title={
            form.description.trim()
              ? "Expand your song idea"
              : "Create a fresh song idea"
          }
          disabled={busy}
          onClick={() => void generate()}
        >
          {busy ? (
            <LoaderCircle size={16} className="description-spinner" />
          ) : (
            <WandSparkles size={16} />
          )}
        </button>
      </div>
      <textarea
        id="song-description"
        className="description-input"
        value={form.description}
        onChange={(e) => {
          const description = e.target.value;
          change((current) => ({ ...current, description, style: "" }));
          setNotice("");
        }}
        placeholder="A late-night drive. Warm synths, a steady beat, and a soft, soulful vocal…"
      />
      {(busy || notice || canUndo) && (
        <div className="description-status" role="status">
          <span>
            {busy
              ? work.job?.state === "queued"
                ? "Queued…"
                : "Writing your description…"
              : notice}
          </span>
          {work.busy && (
            <button
              type="button"
              className="text-button"
              onClick={() =>
                void work.cancel().catch((e) => setError(e.message))
              }
            >
              Cancel
            </button>
          )}
          {!busy && canUndo && (
            <button
              type="button"
              className="text-button"
              onClick={() => {
                change((current) =>
                  current.description === undo.generated && current.style === ""
                    ? { ...current, ...undo.source }
                    : current,
                );
                setUndo(null);
                writeLocal("sv-description-undo", null);
                setNotice("Previous description restored.");
              }}
            >
              <Undo2 size={12} /> Undo
            </button>
          )}
        </div>
      )}
      {suggestion && (
        <div className="description-suggestion">
          <p>{suggestion}</p>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              const source = {
                description: form.description,
                style: form.style,
              };
              remember(source, suggestion);
              change((current) =>
                applyDescription(current, source, suggestion),
              );
              setSuggestion("");
              setNotice("Description updated.");
            }}
          >
            Use this description
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setSuggestion("")}
          >
            Dismiss
          </button>
        </div>
      )}
      {(error || work.error) && (
        <p className="form-error" role="alert">
          {error || work.error}
        </p>
      )}
    </>
  );
}

export function CoverButton({
  id,
  connected,
  hasCover,
  connect,
}: {
  id: string;
  connected: boolean;
  hasCover: boolean;
  connect: () => void;
}) {
  const work = useJob(`sv-cover-${id}`),
    [error, setError] = useState(""),
    [starting, setStarting] = useState(false);
  async function create() {
    if (!connected) {
      connect();
      return;
    }
    setStarting(true);
    setError("");
    try {
      const job = await request<Job>(`/takes/${id}/cover`, {});
      work.select(job.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="details-body">
      <button
        className="secondary-button"
        disabled={work.busy || starting}
        onClick={() => void create()}
      >
        {work.busy || starting
          ? "Creating cover…"
          : hasCover
            ? "Create another cover"
            : "Create cover art"}
      </button>
      {work.busy && (
        <button
          className="text-button"
          onClick={() => void work.cancel().catch((e) => setError(e.message))}
        >
          Cancel cover
        </button>
      )}
      {(error || work.error || work.job?.error) && (
        <p role="alert">{error || work.error || work.job?.error}</p>
      )}
    </div>
  );
}

export function WritingAssistant({
  form,
  change,
  account,
  connect,
  simple = false,
  openRequest = 0,
}: {
  form: SongForm;
  change: (form: SongForm) => void;
  account: AccountStatus | null;
  connect: () => void;
  simple?: boolean;
  openRequest?: number;
}) {
  const work = useJob("sv-writing-request"),
    [error, setError] = useState(""),
    [starting, setStarting] = useState(false);
  const [model, setModel] = useState(""),
    [preserveMelody, setPreserveMelody] = useState(true);
  const [review, setReview] = useState(false),
    [undo, setUndo] = useState<SongForm | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const panel = useRef<HTMLDetailsElement>(null);
  const instructions = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!openRequest || !panel.current) return;
    panel.current.open = true;
    panel.current.scrollIntoView({ block: "nearest" });
    instructions.current?.focus({ preventScroll: true });
  }, [openRequest]);
  useEffect(() => {
    if (review) dialog.current?.showModal();
  }, [review]);
  async function generate(task = form.writingTask) {
    if (!account?.connected) {
      connect();
      return;
    }
    setError("");
    setStarting(true);
    const signature = JSON.stringify({ task, form, preserveMelody, model });
    const pending = readLocal<{ signature: string; id: string } | null>(
      "sv-writing-submission",
      null,
    );
    const id =
      pending?.signature === signature ? pending.id : crypto.randomUUID();
    writeLocal("sv-writing-submission", { signature, id });
    try {
      const job = await request<Job>("/assistance", {
        requestId: id,
        task,
        prompt: form.writingPrompt,
        title: form.title,
        lyrics: form.lyrics,
        style: form.style || form.description,
        abc: form.abc,
        preserveMelody,
        model: model || null,
      });
      work.select(job.id);
      writeLocal("sv-writing-submission", null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  const proposal = work.job?.result?.proposal;
  function apply(idea?: Proposal["ideas"][number]) {
    if (!proposal) return;
    const input = work.job?.result?.input;
    if (
      input &&
      (input.lyrics !== form.lyrics ||
        input.abc !== form.abc ||
        input.style !== (form.style || form.description) ||
        input.title !== form.title)
    ) {
      setError(
        "The song changed after this proposal was requested. Generate a new proposal to keep your edits.",
      );
      setReview(false);
      return;
    }
    setUndo({ ...form });
    if (idea)
      change({
        ...form,
        title: idea.title,
        style: idea.style,
        description: idea.description,
      });
    else
      change({
        ...form,
        title: proposal.title,
        lyrics: proposal.lyrics,
        style: proposal.style,
        abc: proposal.abc,
      });
    setReview(false);
    work.select(null);
  }
  return (
    <details ref={panel} className="setting-group">
      <summary>
        <WandSparkles size={15} aria-hidden="true" />
        <span>Writing assistant</span>
        <ChevronDown size={15} />
      </summary>
      <div className="details-body">
        <label>
          Task
          <select
            aria-label="Writing task"
            value={form.writingTask}
            onChange={(e) => change({ ...form, writingTask: e.target.value })}
          >
            {[
              "Song ideas",
              "Draft lyrics",
              "Rewrite a section",
              "Refine the style",
              "Translate lyrics",
              ...(!simple ? ["Edit score"] : []),
            ].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          Instructions
          <textarea
            ref={instructions}
            rows={3}
            value={form.writingPrompt}
            onChange={(e) => change({ ...form, writingPrompt: e.target.value })}
            placeholder="A song about coming home after a long time away…"
          />
        </label>
        {!simple && account?.connected && (
          <label>
            Model
            <select
              aria-label="Writing model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">Provider default</option>
              {account.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {form.writingTask === "Edit score" && (
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={preserveMelody}
              onChange={(e) => setPreserveMelody(e.target.checked)}
            />
            Keep melody and timing
          </label>
        )}
        <button
          className="secondary-button"
          disabled={starting || work.busy}
          onClick={() => void generate()}
        >
          <WandSparkles size={15} aria-hidden="true" />
          {starting || work.busy
            ? "Working…"
            : account?.connected
              ? "Generate proposal"
              : "Choose an AI provider"}
        </button>
        {work.busy && (
          <button
            className="text-button"
            onClick={() => void work.cancel().catch((e) => setError(e.message))}
          >
            Cancel request
          </button>
        )}
        {proposal && (
          <button className="secondary-button" onClick={() => setReview(true)}>
            Review proposal
          </button>
        )}
        {undo && (
          <button
            className="text-button"
            onClick={() => {
              change(undo);
              setUndo(null);
            }}
          >
            Undo applied proposal
          </button>
        )}
        {(error || work.error || work.job?.error) && (
          <p role="alert">{error || work.error || work.job?.error}</p>
        )}
        <p className="field-note">
          Review changes before applying. Score edits render as a new recording.
        </p>
      </div>
      {review && proposal && (
        <dialog
          ref={dialog}
          className="modal"
          aria-label="Review music proposal"
          onCancel={() => setReview(false)}
        >
          <div className="modal-head">
            <h2>Review proposal</h2>
            <button className="text-button" onClick={() => setReview(false)}>
              Close
            </button>
          </div>
          <div className="modal-body">
            <p>{proposal.summary}</p>
            {proposal.ideas.length ? (
              proposal.ideas.map((idea, i) => (
                <section key={i}>
                  <h3>{idea.title}</h3>
                  <p>{idea.description}</p>
                  <p className="field-note">{idea.style}</p>
                  <button
                    className="secondary-button"
                    onClick={() => apply(idea)}
                  >
                    Use this idea
                  </button>
                </section>
              ))
            ) : (
              <>
                {(["title", "style", "lyrics", "abc"] as const)
                  .filter(
                    (key) => proposal[key] !== work.job?.result?.input?.[key],
                  )
                  .map((key) => (
                    <label key={key}>
                      {key === "abc" ? "Score" : key}
                      <textarea
                        readOnly
                        rows={key === "lyrics" || key === "abc" ? 12 : 3}
                        value={proposal[key]}
                      />
                    </label>
                  ))}
                <button className="secondary-button" onClick={() => apply()}>
                  Apply proposal
                </button>
              </>
            )}
          </div>
        </dialog>
      )}
    </details>
  );
}

export function ReferenceSong({
  form,
  change,
}: {
  form: SongForm;
  change: (form: SongForm) => void;
}) {
  const work = useJob("sv-reference-request");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<"melody" | "full">("melody");
  const input = useRef<HTMLInputElement>(null);
  // A newer selection owns the panel immediately, including during an upload.
  const revision = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const busy = uploading || work.busy;
  const preview = work.job?.state === "succeeded" ? work.job.result : null;
  const hasScore = !!(form.abc.trim() || preview?.abc);

  function clearScore() {
    const current = ++revision.current;
    if (work.id && work.busy) {
      void work.cancel().catch((e) => {
        if (revision.current === current)
          setError(
            `Previous transcription could not be cancelled: ${e.message}`,
          );
      });
    }
    work.select(null);
    setUploading(false);
    setError("");
    change({
      ...form,
      abc: "",
      referenceId: undefined,
      sourceTakeId: undefined,
    });
  }

  function chooseFile(next?: File) {
    if (!next) return;
    if (
      !/\.(wav|flac|mp3|m4a|ogg)$/i.test(next.name) ||
      next.size === 0 ||
      next.size > 50 * 1024 * 1024
    ) {
      setError("Choose a WAV, FLAC, MP3, M4A or OGG file smaller than 50 MB.");
      if (input.current) input.current.value = "";
      return;
    }
    clearScore();
    setFile(next);
    // The same file can be selected again after clearing or replacing it.
    if (input.current) input.current.value = "";
  }

  async function generateScore() {
    if (!file || busy) return;
    clearScore();
    const current = revision.current;
    setUploading(true);
    try {
      const response = await fetch(`/api/references?mode=${mode}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
        signal: AbortSignal.timeout(120000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed.");
      if (current !== revision.current || !mounted.current) {
        // Keep the response long enough to cancel its owned server job. Never
        // let an upload that finished late replace the newly selected song.
        await request(`/assistance/${data.id}/cancel`, {});
        return;
      }
      work.select(data.id);
    } catch (e) {
      if (mounted.current && current === revision.current)
        setError((e as Error).message);
    } finally {
      if (mounted.current && current === revision.current) setUploading(false);
    }
  }

  return (
    <details className="setting-group reference-song">
      <summary>
        <Upload size={15} />
        <span>Reference song</span>
        <ChevronDown size={15} />
      </summary>
      <div className="details-body">
        <input
          ref={input}
          className="reference-file-input"
          type="file"
          aria-label="Audio file"
          accept=".wav,.flac,.mp3,.m4a,.ogg"
          onChange={(e) => chooseFile(e.target.files?.[0])}
        />
        {file && (
          <div className="reference-file">
            <FileMusic size={18} aria-hidden="true" />
            <span>
              <strong>{file.name}</strong>
              <small>{(file.size / (1024 * 1024)).toFixed(1)} MB</small>
            </span>
            <button
              type="button"
              className="writer-wand"
              aria-label="Remove reference song"
              title="Remove reference song"
              onClick={() => {
                clearScore();
                setFile(null);
                if (input.current) input.current.value = "";
              }}
            >
              <X size={15} />
            </button>
          </div>
        )}
        <button
          type="button"
          className="secondary-button"
          onClick={() => input.current?.click()}
        >
          <Upload size={15} aria-hidden="true" />
          {file ? "Choose another song" : "Choose reference song"}
        </button>
        <p className="field-note">
          WAV, FLAC, MP3, M4A or OGG · up to 5 minutes / 50 MB.
        </p>
        <label>
          Keep
          <select
            aria-label="Reference transcription mode"
            value={mode}
            disabled={busy}
            onChange={(e) => {
              clearScore();
              setMode(e.target.value as typeof mode);
            }}
          >
            <option value="melody">Melody — new arrangement</option>
            <option value="full">Melody and chords</option>
          </select>
        </label>
        <div className="reference-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={!file || busy}
            onClick={() => void generateScore()}
          >
            <FileMusic size={15} aria-hidden="true" />
            {busy ? "Generating score…" : "Generate score"}
          </button>
          {(hasScore || work.id || uploading) && (
            <button
              type="button"
              className="secondary-button"
              onClick={clearScore}
            >
              {busy ? "Cancel & clear" : "Clear score"}
            </button>
          )}
        </div>
        {!file && !work.id && !form.abc && (
          <p className="field-note">Choose a song, then generate its score.</p>
        )}
        {busy && (
          <p className="field-note" role="status">
            {uploading
              ? "Uploading…"
              : work.job?.state === "waiting-for-resource"
                ? "Waiting for GPU…"
                : "Transcribing reference…"}
          </p>
        )}
        {preview?.abc && (
          <>
            <label>
              New score
              <textarea
                aria-label="Transcribed score"
                rows={6}
                readOnly
                value={preview.abc}
              />
            </label>
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                change({
                  ...form,
                  abc: preview.abc!,
                  cot: preview.input?.mode === "full" ? "full" : "melody",
                  referenceId: work.id || undefined,
                  sourceTakeId: undefined,
                });
                work.select(null);
              }}
            >
              Use this score
            </button>
            {preview.warnings?.map((w, i) => (
              <p className="field-note" key={i}>
                {w}
              </p>
            ))}
          </>
        )}
        {form.abc && (
          <p className="field-note" role="status">
            {form.referenceId
              ? "Reference score applied."
              : "A score is added to this song."}
          </p>
        )}
        {(error || work.error || work.job?.error) && (
          <p role="alert">{error || work.error || work.job?.error}</p>
        )}
      </div>
    </details>
  );
}
