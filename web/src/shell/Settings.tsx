import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { ImageProvider, ProviderStatus } from "../lib/types";
import { Button, Modal } from "../ui/controls";
import "./settings.css";
import { Machine, machine } from "../lib/machine";

type Step = { provider: string; model: string | null; effort?: string | null; options?: Record<string, string> };

interface Connections {
  providers: ProviderStatus[];
  who: Record<string, Step[]>;
  roles: Record<string, string>;
  efforts?: string[];
  filmModels?: Record<string, string>;
  imageRoles?: Record<string, string>;
  imageProviders?: ImageProvider[];
  motionRoles?: Record<string, string>;
  motionProviders?: ImageProvider[];
  mcp?: McpServer[];
  providerModels?: Record<string, Partial<Record<"image" | "video", CatalogModel[]>>>; // Grok's Imagine models
}

/** One of your MCP servers (its key never comes back from the server). */
interface McpServer {
  id: string;
  name: string;
  url: string;
  header: string | null;
  paid: boolean;
  ok?: boolean;
  error?: string | null;
  tools?: { name: string; description: string }[];
  director?: boolean; // the director may use it while it makes a video (on unless turned off)
  signIn?: boolean; // signs in in the browser (MCP's OAuth) rather than with a key
  signedIn?: boolean;
  needsSignIn?: boolean;
  catalog?: Catalog; // the models it runs, once they've been read
}

/** A server's models, read by Claude from its own tools (sv/catalog.py): picture models and clip (video) models, each
 *  with the settings that change what it makes and what it costs. */
interface Catalog {
  state: "none" | "reading" | "ready" | "error";
  error?: string;
  image?: CatalogModel[];
  video?: CatalogModel[];
}
interface CatalogModel {
  id: string;
  name: string;
  note: string;
  options: { key: string; label: string; values: string[]; default: string }[];
}

/** Sign in to a server in a new tab; it comes back to the app by itself, or its address is pasted here. */
async function startSignIn(id: string): Promise<void> {
  const tab = window.open("about:blank", "_blank");
  try {
    const { url } = await api.post<{ url: string }>(`/api/mcp/${id}/signin`, { origin: location.origin });
    if (!/^https?:\/\//i.test(url)) throw new Error("The server's sign-in address isn't a web address, so it wasn't opened.");
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (e) {
    tab?.close();
    throw e;
  }
}

/** Reasoning levels in plain words (Claude Code's --effort, and the ones ChatGPT's models list). */
export const EFFORT_NAME: Record<string, string> = { none: "None", minimal: "Minimal", low: "Low", medium: "Medium", high: "High",
  xhigh: "Extra high", max: "Max" };
/** The providers whose steps can carry a reasoning level. */
const REASONS = new Set(["claude", "openai"]);

const PREFIX: Record<string, string> = {
  claude: "Claude", grok: "Grok", openai: "ChatGPT",
  get local() { return `${Machine()} ·`; },
};

interface Option { key: string; label: string; p: string; m: string | null; ok: boolean; dflt?: boolean }

/** The option a step picks: a step with no model runs its provider's default one. */
function keyOf(options: Option[], s: { provider: string; model: string | null }): string {
  const d = s.model == null && (options.find((o) => o.p === s.provider && o.dflt) ?? options.find((o) => o.p === s.provider));
  return d ? d.key : `${s.provider}:${s.model ?? ""}`;
}

/** Every model each provider offers (as it reports them), the role's current choice even if typed in by hand, and
 *  "Another model id…" for anything else the provider can run. */
function optionsFor(c: Connections, first?: { provider: string; model: string | null }): Option[] {
  const out: Option[] = c.providers.flatMap((p) => {
    const models = p.models?.length ? p.models : [{ id: "", name: p.name, default: true }];
    return models.map((m) => ({
      key: `${p.id}:${m.id}`, p: p.id, m: m.id || null, ok: p.connected, dflt: !!m.default,
      label: p.models?.length ? `${PREFIX[p.id] ?? p.name} ${m.name}` : p.name,
    }));
  });
  if (first && !out.some((o) => o.key === keyOf(out, first))) {
    const p = c.providers.find((x) => x.id === first.provider);
    out.unshift({ key: `${first.provider}:${first.model ?? ""}`, p: first.provider, m: first.model, ok: !!p?.connected,
      label: `${PREFIX[first.provider] ?? first.provider} ${first.model ?? ""} (typed in)` });
  }
  return out;
}

/** Settings: who the app talks to, and who does which work. */
export function Settings({ onClose }: { onClose: () => void }) {
  const [c, setC] = useState<Connections | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api.get<Connections>("/api/connections").then(setC).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    void load();
  }, []);

  // A server's sign-in tab came back: show it signed in.
  useEffect(() => {
    const back = (e: MessageEvent) => { if (e.data === "sv-mcp") void load(); };
    window.addEventListener("message", back);
    return () => window.removeEventListener("message", back);
  }, []);

  // While a sign-in code is showing, or a server's models are being read, look every few seconds.
  const waiting = c?.providers.some((p) => p.login) || c?.mcp?.some((m) => m.catalog?.state === "reading");
  useEffect(() => {
    if (!waiting) return;
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, [waiting]);

  async function signIn(id: string) {
    setBusy(id);
    setError(null);
    try {
      await api.post(`/api/connections/${id}/signin`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function signOut(id: string) {
    setBusy(id);
    setError(null);
    try {
      await api.post(`/api/connections/${id}/signout`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function setFirst(role: string, provider: string, model: string | null, effort?: string | null) {
    if (!c) return;
    const rest = c.who[role].filter((s) => !(s.provider === provider && (s.model ?? null) === model));
    // a reasoning level carries over to the new model only if that model takes it
    const asked = effort === undefined ? c.who[role][0]?.effort ?? null : effort;
    const keep = asked && effortsOf(c, provider, model).includes(asked) ? asked : null;
    const who = await api.put<Connections["who"]>(`/api/connections/who/${role}`,
      [{ provider, model, ...(REASONS.has(provider) && keep ? { effort: keep } : {}) }, ...rest]);
    setC({ ...c, who });
  }

  async function setPictures(role: string, step: { provider: string; model?: string | null; options?: Record<string, string> }) {
    if (!c) return;
    const who = await api.put<Connections["who"]>(`/api/connections/who/${role}`, [step]);
    setC({ ...c, who });
  }

  async function readModels(id: string) {
    setError(null);
    try {
      await api.post(`/api/mcp/${id}/catalog`);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <Modal title="Settings" onClose={onClose} wide>
      <h3 className="st-h">Connections</h3>
      <p className="st-lead">The models Sound / Vision can ask. Each signs in its own way; the app never sees a password.</p>
      {!c && !error && <p className="st-lead">Asking {machine()}…</p>}
      {error && <p className="mk-error">{error}</p>}
      <div className="st-cards">
        {c?.providers.map((p) => (
          <div key={p.id} className={"st-card" + (p.connected ? " st-on" : "")}>
            <div className="st-card-head">
              <span className="st-dot" />
              <strong>{p.name}</strong>
              <span className="st-state">{p.connected ? "Connected" : p.installed ? "Not connected" : "Not set up"}</span>
            </div>
            {p.note && <p className="st-note">{p.note}</p>}
            {p.login ? (
              <div className="st-login">
                <p>
                  Open <a href={p.login.url} target="_blank" rel="noreferrer">{new URL(p.login.url).host}</a> and enter this code:
                </p>
                <code className="st-code">{p.login.code}</code>
                <p className="st-note">Waiting for you to approve it… (this updates by itself)</p>
                <Button size="sm" kind="ghost" onClick={() => api.post(`/api/connections/${p.id}/signin/cancel`).then(load)}>Cancel</Button>
              </div>
            ) : p.canSignIn && p.installed && !p.connected ? (
              <>
                {p.error && <p className="st-note">{p.error}</p>}
                <Button size="sm" kind="primary" busy={busy === p.id} onClick={() => signIn(p.id)}>
                  {p.id === "openai" ? "Sign in with ChatGPT" : `Sign in to ${p.name}`}
                </Button>
              </>
            ) : p.error && !p.connected ? (
              <p className="st-note st-how">{p.error}</p>
            ) : null}
            {p.connected && p.account && (
              <p className="st-note">Signed in as {p.account}{p.plan ? ` · ${p.plan}` : ""}</p>
            )}
            {p.connected && p.models && p.models.length > 0 && p.id !== "claude" && (
              <p className="st-note">Models: {p.models.map((m) => m.name).join(", ")}</p>
            )}
            {p.connected && p.canSignIn && (
              <button type="button" className="st-out" disabled={busy === p.id} onClick={() => void signOut(p.id)}>Sign out</button>
            )}
          </div>
        ))}
      </div>

      {c && (
        <>
          <h3 className="st-h">MCP servers</h3>
          <p className="st-lead">Tools from other services: pictures, video, anything they offer. The model that directs your videos can use them while it
            directs a video, and any of them can make your pictures (under Pictures, below).</p>
          {(c.mcp ?? []).length > 0 && (
            <div className="st-mcps">
              {c.mcp!.map((m) => <McpRow key={m.id} server={m} onChange={load} />)}
            </div>
          )}
          <AddMcp onAdded={load} />

          <h3 className="st-h">Who does what</h3>
          <p className="st-lead">Each kind of work goes to its first choice; if that one isn't connected, the next one in line does it.</p>
          <div className="st-roles">
            {Object.entries(c.roles).map(([role, label]) => (
              <RoleRow key={role} label={label} chain={c.who[role] ?? []}
                options={role === "film" ? filmOptions(c) : optionsFor(c, c.who[role]?.[0])}
                efforts={c.who[role]?.[0] ? effortsOf(c, c.who[role][0].provider, c.who[role][0].model) : []}
                providers={c.providers} onPick={(p, m) => void setFirst(role, p, m)}
                onEffort={(e) => { const f = c.who[role]?.[0]; if (f) void setFirst(role, f.provider, f.model, e); }} />
            ))}
          </div>
          <p className="st-lead st-after">Reasoning: how long the model thinks before it answers. Higher is slower and uses
            more of your plan; for videos made in code, Extra high is the default.</p>
          {c.imageRoles && c.imageProviders && (
            <>
              <h3 className="st-h">Pictures and video</h3>
              <div className="st-roles">
                {[...Object.entries(c.imageRoles).map(([role, label]) => [role, label, c.imageProviders!] as const),
                  ...Object.entries(c.motionRoles ?? {}).map(([role, label]) => [role, label, c.motionProviders ?? []] as const)]
                  .map(([role, label, choices]) => {
                    const step = c.who[role]?.[0] ?? { provider: "local", model: null };
                    const server = step.provider.startsWith("mcp:") ? c.mcp?.find((m) => `mcp:${m.id}` === step.provider) : undefined;
                    return (
                      <MediaRow key={role} label={label} choices={choices} step={step} server={server}
                        own={c.providerModels?.[step.provider]?.[role in (c.motionRoles ?? {}) ? "video" : "image"]}
                        kind={role in (c.motionRoles ?? {}) ? "video" : "image"}
                        onSet={(next) => void setPictures(role, next)} onRead={(id) => void readModels(id)} />
                    );
                  })}
              </div>
            </>
          )}
        </>
      )}
    </Modal>
  );
}

/** The reasoning levels this model takes (as its provider lists them); Claude's otherwise, for a typed-in Claude id. */
function effortsOf(c: Connections, provider: string, model: string | null): string[] {
  if (!REASONS.has(provider)) return [];
  const p = c.providers.find((x) => x.id === provider);
  const m = p?.models?.find((x) => x.id === model) ?? p?.models?.find((x) => x.default);
  return m?.efforts ?? (provider === "claude" ? c.efforts ?? [] : []);
}

/** Videos made in code run in Claude Code on the server: only Claude's models. */
function filmOptions(c: Connections): Option[] {
  const claude = c.providers.find((p) => p.id === "claude");
  return Object.entries(c.filmModels ?? {}).map(([id, name]) => ({ key: `claude:${id}`, p: "claude", m: id, ok: !!claude?.connected,
    label: `Claude ${name}` }));
}

/** One picture or clip job in Settings: who makes it and, on an MCP server, which of its models and with what settings
 *  (from the server's catalog; read it first if it hasn't been). */
function MediaRow({ label, choices, step, server, own, kind, onSet, onRead }: {
  label: string;
  choices: ImageProvider[];
  step: Step;
  server?: McpServer;
  own?: CatalogModel[]; // a provider's own models (Grok Imagine's), when it has a choice of them
  kind: "image" | "video";
  onSet: (step: { provider: string; model?: string | null; options?: Record<string, string> }) => void;
  onRead: (id: string) => void;
}) {
  const chosen = choices.find((x) => x.id === step.provider);
  const cat = server?.catalog;
  const models = cat?.[kind] ?? [];
  const model = models.find((x) => x.id === step.model);
  const options = step.options ?? {};
  const what = kind === "video" ? "clip" : "picture";
  let middle = null;
  let note = chosen?.note;
  if (!server && own?.length) {  // Grok: its picture models (the first is its default), or the one it makes clips with
    const pick = own.find((x) => x.id === step.model) ?? own[0];
    middle = own.length === 1 ? <span className="st-wait">{pick.name}</span> : (
      <select className="in" value={pick.id} aria-label={`${label}: model`}
        onChange={(e) => onSet({ provider: step.provider, model: e.target.value })}>
        {own.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
    );
    note = pick.note || note;
  } else if (server && (!cat || cat.state === "none" || (cat.state === "error" && !models.length))) {
    middle = <Button size="sm" kind="ghost" onClick={() => onRead(server.id)}>Read its models</Button>;
    note = cat?.state === "error" ? cat.error : `Lists the ${what} models ${server.name} runs, with their settings, so you can choose one. Nothing is made.`;
  } else if (server && cat?.state === "reading") {
    middle = <span className="st-wait">Reading its models…</span>;
  } else if (server && !models.length) {
    middle = <span className="st-wait">It lists no {what} models</span>;
  } else if (server) {
    middle = (
      <select className="in" value={step.model ?? ""} aria-label={`${label}: model`}
        onChange={(e) => onSet({ provider: step.provider, model: e.target.value || null })}>
        <option value="">Its default model</option>
        {models.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        {step.model && !model && <option value={step.model}>{step.model} (no longer listed)</option>}
      </select>
    );
    note = model?.note || note;
  }
  return (
    <>
      <div className="st-role">
        <span>{label}</span>
        <select className="in" value={step.provider} onChange={(e) => onSet({ provider: e.target.value })}>
          {choices.filter((x) => x.connected !== false || x.id === step.provider).map((x) => (
            <option key={x.id} value={x.id}>{x.name}{x.connected === false ? " (not connected)" : ""}</option>
          ))}
        </select>
        {middle ?? <span />}
        <em>{note}</em>
      </div>
      {model && model.options.length > 0 && (
        <div className="st-media-opts">
          {model.options.map((o) => (
            <label key={o.key} className="st-field">
              {o.label}
              <select className="in" value={options[o.key] ?? ""}
                onChange={(e) => {
                  const next = { ...options };
                  if (e.target.value) next[o.key] = e.target.value;
                  else delete next[o.key];
                  onSet({ provider: step.provider, model: model.id, options: next });
                }}>
                <option value="">{o.default ? `Its default (${o.default})` : "Its default"}</option>
                {o.values.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
          ))}
        </div>
      )}
    </>
  );
}

/** On a server's card: what its catalog holds, and reading it (again). */
function CatalogLine({ m, onRead }: { m: McpServer; onRead: () => void }) {
  const cat = m.catalog;
  if (cat?.state === "reading") return <p className="st-note">Reading its models…</p>;
  const n = (k: "image" | "video") => cat?.[k]?.length ?? 0;
  const have = cat?.state === "ready" || n("image") + n("video") > 0;
  return (
    <p className="st-note">
      {have ? `${n("image")} picture model${n("image") === 1 ? "" : "s"}, ${n("video")} video model${n("video") === 1 ? "" : "s"}. ` : ""}
      {cat?.state === "error" && <span className="st-bad">{cat.error} </span>}
      <button type="button" className="st-out" onClick={onRead}>{have ? "Read them again" : "Read its models"}</button>
    </p>
  );
}

function RoleRow({ label, chain, options, efforts, providers, onPick, onEffort }: {
  label: string;
  chain: Step[];
  options: Option[];
  efforts: string[];
  providers: ProviderStatus[];
  onPick: (provider: string, model: string | null) => void;
  onEffort: (effort: string | null) => void;
}) {
  const first = chain[0];
  const [other, setOther] = useState(false);
  const [prov, setProv] = useState(first?.provider ?? "claude");
  const [id, setId] = useState("");
  const value = first ? keyOf(options, first) : "";
  const name = (s: { provider: string; model: string | null }) =>
    options.find((o) => o.key === `${s.provider}:${s.model ?? ""}`)?.label ??
    (s.model ? `${PREFIX[s.provider] ?? s.provider} ${s.model}` : providers.find((p) => p.id === s.provider)?.name ?? s.provider);
  return (
    <div className="st-role">
      <span>{label}</span>
      <select className="in" value={other ? "__other" : value} onChange={(e) => {
        if (e.target.value === "__other") return setOther(true);
        setOther(false);
        const o = options.find((x) => x.key === e.target.value);
        if (o) onPick(o.p, o.m);
      }}>
        {options.map((o) => (
          <option key={o.key} value={o.key}>{o.label}{o.ok ? "" : " (not connected)"}</option>
        ))}
        <option value="__other">Another model id…</option>
      </select>
      {first && efforts.length > 0 && (
        <select className="in st-effort" value={first.effort ?? ""} aria-label={`Reasoning for ${label}`}
          onChange={(e) => onEffort(e.target.value || null)}>
          <option value="">Reasoning: {PREFIX[first.provider] ?? first.provider}'s default</option>
          {efforts.map((x) => <option key={x} value={x}>Reasoning: {EFFORT_NAME[x] ?? x}</option>)}
        </select>
      )}
      {other ? (
        <div className="st-other">
          <select className="in" value={prov} onChange={(e) => setProv(e.target.value)} aria-label="Provider">
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input className="in" value={id} placeholder={prov === "claude" ? "e.g. claude-opus-5-5" : "the model's id"}
            onChange={(e) => setId(e.target.value)} aria-label="Model id" />
          <Button size="sm" disabled={!id.trim()} onClick={() => { onPick(prov, id.trim()); setOther(false); setId(""); }}>Use</Button>
        </div>
      ) : (
        <em>then {chain.slice(1).map(name).join(", then ") || "nothing"}</em>
      )}
    </div>
  );
}

function McpRow({ server: m, onChange }: { server: McpServer; onChange: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const act = async (what: string, call: () => Promise<unknown>) => {
    setBusy(what);
    setError(null);
    try {
      await call();
      onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  let host = m.url;
  try { host = new URL(m.url).host; } catch { /* as typed */ }
  const [signing, setSigning] = useState(false);
  const [pasted, setPasted] = useState("");
  // while a sign-in is open in another tab: look for it to finish (the tab also says so when it comes back)
  useEffect(() => {
    if (!signing) return;
    const done = (e: MessageEvent) => { if (e.data === "sv-mcp") { setSigning(false); onChange(); } };
    window.addEventListener("message", done);
    const id = window.setInterval(onChange, 4000);
    return () => { window.removeEventListener("message", done); window.clearInterval(id); };
  }, [signing]);
  useEffect(() => { if (m.signedIn) setSigning(false); }, [m.signedIn]);
  return (
    <div className={"st-card st-mcp" + (m.ok ? " st-on" : "")}>
      <div className="st-card-head">
        <span className="st-dot" />
        <strong>{m.name}</strong>
        <span className="st-state">{m.ok ? `${m.tools?.length ?? 0} tools` : m.signIn && !m.signedIn ? "Not signed in" : "Not answering"}</span>
      </div>
      <p className="st-note">{host}{m.header ? ` · key sent as ${m.header}` : m.signIn ? " · signs in in the browser" : ""}</p>
      {!m.ok && m.error && !(m.signIn && !m.signedIn) && <p className="st-note st-bad">{m.error}</p>}
      {m.signIn && !m.signedIn && (
        signing ? (
          <div className="st-login">
            <p className="st-note">Sign in in the new tab. If the page it ends on doesn't load, paste that page's address here:</p>
            <input className="in" value={pasted} placeholder="The address you ended on" onChange={(e) => setPasted(e.target.value)} />
            <div className="st-mcp-actions">
              <Button size="sm" disabled={!pasted.trim()} busy={busy === "paste"}
                onClick={() => void act("paste", () => api.post("/api/mcp/signin/finish", { address: pasted }).then(() => { setSigning(false); setPasted(""); }))}>
                Finish signing in
              </Button>
              <Button size="sm" kind="ghost" onClick={() => setSigning(false)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <Button size="sm" kind="primary" busy={busy === "signin"}
            onClick={() => void act("signin", () => startSignIn(m.id).then(() => setSigning(true)))}>
            Sign in to {m.name}
          </Button>
        )
      )}
      {m.ok && <CatalogLine m={m} onRead={() => void act("catalog", () => api.post(`/api/mcp/${m.id}/catalog`))} />}
      {m.ok && (m.tools?.length ?? 0) > 0 && (
        <button type="button" className="st-out" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide its tools" : "Show its tools"}
        </button>
      )}
      {open && (
        <ul className="st-tools">
          {m.tools!.map((t) => <li key={t.name}><code>{t.name}</code>{t.description ? ` — ${t.description}` : ""}</li>)}
        </ul>
      )}
      <label className="st-check">
        <input type="checkbox" checked={m.paid} disabled={!!busy}
          onChange={(e) => void act("paid", () => api.patch(`/api/mcp/${m.id}`, { paid: e.target.checked }))} />
        It may cost money: ask before each job that uses it
      </label>
      <label className="st-check">
        <input type="checkbox" checked={m.director !== false} disabled={!!busy}
          onChange={(e) => void act("director", () => api.patch(`/api/mcp/${m.id}`, { director: e.target.checked }))} />
        The director may use all its tools while it makes a video
      </label>
      <div className="st-mcp-actions">
        <Button size="sm" kind="ghost" busy={busy === "check"} onClick={() => void act("check", () => api.post(`/api/mcp/${m.id}/check`))}>Check again</Button>
        {m.signIn && m.signedIn && (
          <Button size="sm" kind="ghost" busy={busy === "signout"} onClick={() => void act("signout", () => api.post(`/api/mcp/${m.id}/signout`))}>Sign out</Button>
        )}
        <Button size="sm" kind="ghost" busy={busy === "remove"}
          onClick={() => { if (confirm(`Remove ${m.name}? Pictures it made stay; anything set to use it goes back to your GPU.`)) void act("remove", () => api.del(`/api/mcp/${m.id}`)); }}>
          Remove
        </Button>
      </div>
      {error && <p className="mk-error">{error}</p>}
    </div>
  );
}

/** Add a server by its address (streamable HTTP), with a key if it needs one. It's connected to before it's kept. */
function AddMcp({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [header, setHeader] = useState("Authorization");
  const [paid, setPaid] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!open) return <Button size="sm" onClick={() => setOpen(true)}>Add an MCP server</Button>;
  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      const rec = await api.post<McpServer>("/api/mcp", { name, url, key, header: key.trim() ? header : "", paid });
      if (rec.needsSignIn) await startSignIn(rec.id).catch(() => undefined);  // it asks for a sign-in: straight there
      setOpen(false);
      setName(""); setUrl(""); setKey("");
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="st-card st-add">
      <label className="st-field"><span>Name</span>
        <input className="in" value={name} placeholder="What you'll call it" onChange={(e) => setName(e.target.value)} /></label>
      <label className="st-field"><span>Address</span>
        <input className="in" value={url} placeholder="https://…/mcp" onChange={(e) => setUrl(e.target.value)} /></label>
      <label className="st-field"><span>Key (if it needs one)</span>
        <input className="in" type="password" autoComplete="off" value={key} placeholder="Kept on the server, never shown again"
          onChange={(e) => setKey(e.target.value)} /></label>
      {key.trim() && (
        <label className="st-field"><span>Sent as the header</span>
          <input className="in" value={header} onChange={(e) => setHeader(e.target.value)} /></label>
      )}
      <label className="st-check">
        <input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} />
        It may cost money: ask before each job that uses it
      </label>
      <p className="st-note">Servers that speak streamable HTTP, the usual way for hosted ones. Leave the key empty for a
        server you sign in to in the browser. A plain key goes as "Bearer …" in Authorization; servers that want their own
        header name say so in their docs.</p>
      {error && <p className="mk-error">{error}</p>}
      <div className="st-mcp-actions">
        <Button size="sm" kind="primary" busy={busy} disabled={!name.trim() || !url.trim()} onClick={() => void add()}>Connect and add</Button>
        <Button size="sm" kind="ghost" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  );
}
