import { useEffect, useState } from "react";
import { WandSparkles, LogIn, LogOut } from "lucide-react";
import { request } from "../../music-studio/api";
import { useStudio } from "../context";
import { Btn, ErrorNote, Field, Kicker, Modal, Segmented, Select, TextInput, Toggle, cn } from "../ui";

type ProviderSettings = {
  provider: "openai" | "local";
  textBackend: "ollama" | "compatible";
  textUrl: string;
  textModel: string;
  textApiKey?: string;
  textUseGpu: boolean;
  comfyUrl: string;
  imagePreset: "krea2" | "sdxl" | "custom";
  imageModel: string;
  textEncoder: string;
  vae: string;
  modelRoot: string;
  workflow?: string;
  promptNode: string;
  promptInput: string;
  outputNode: string;
};
const defaultSettings: ProviderSettings = {
  provider: "openai",
  textBackend: "ollama",
  textUrl: "http://127.0.0.1:11434",
  textModel: "",
  textApiKey: "",
  textUseGpu: true,
  comfyUrl: "http://127.0.0.1:8188",
  imagePreset: "krea2",
  imageModel: "",
  textEncoder: "",
  vae: "",
  modelRoot: "",
  workflow: "",
  promptNode: "6",
  promptInput: "text",
  outputNode: "9",
};
type Account = {
  provider?: string;
  available: boolean;
  connected: boolean;
  email?: string;
  plan?: string;
  images?: boolean;
  models?: { id: string; name: string; default?: boolean }[];
  login?: { verificationUrl: string; userCode: string; expiresAt: number } | null;
  error?: string | null;
};
type Probe = {
  models?: { id: string; name: string }[];
  comfy?: Record<string, string[] | undefined>;
  textError?: string;
  imageError?: string;
};

export function SettingsModal() {
  const { settingsOpen, setSettingsOpen, pushToast } = useSettingsToasts();
  const [tab, setTab] = useState<"providers" | "account">("providers");
  const [settings, setSettings] = useState<ProviderSettings>(defaultSettings);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [probed, setProbed] = useState<Probe | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const patch = (part: Partial<ProviderSettings>) =>
    setSettings((old) => ({ ...old, ...part }));
  useEffect(() => {
    if (!settingsOpen) return;
    setError("");
    request<{ config: ProviderSettings }>("/providers")
      .then((r) => setSettings({ ...defaultSettings, ...r.config }))
      .catch(() => {});
    request<Account>("/openai/account")
      .then(setAccount)
      .catch(() => setAccount(null));
  }, [settingsOpen]);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ config: ProviderSettings }>("/providers", settings, "PUT");
      setSettings({ ...defaultSettings, ...result.config });
      pushToast("AI setup saved");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function probe() {
    setBusy(true);
    setError("");
    try {
      setProbed(await request<Probe>("/providers/probe", settings));
    } catch (e) {
      setError((e as Error).message);
      setProbed(null);
    } finally {
      setBusy(false);
    }
  }
  async function accountAction(action: "login" | "logout") {
    setBusy(true);
    setError("");
    try {
      const status = await request<Account>(
        action === "login" ? "/openai/login" : "/openai/logout",
        {},
      );
      setAccount(status);
      if (action === "login" && status.login?.verificationUrl)
        window.open(status.login.verificationUrl, "_blank", "noopener");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const local = settings.provider === "local";
  return (
    <Modal
      open={settingsOpen}
      onClose={() => setSettingsOpen(false)}
      title="AI setup"
      subtitle="Writing assistance, cover art and local model endpoints."
      wide
      footer={
        <>
          <span className="modal-foot-note">{error || ""}</span>
          <Btn variant="primary" loading={busy} onClick={() => void save()}>
            Save setup
          </Btn>
        </>
      }
    >
      <Segmented
        ariaLabel="Settings section"
        options={[
          { value: "providers", label: "Providers" },
          { value: "account", label: "Account" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "providers" ? (
        <div className="settings-body">
          <Segmented
            ariaLabel="Text provider"
            options={[
              { value: "openai", label: "OpenAI account" },
              { value: "local", label: "Local models" },
            ]}
            value={settings.provider}
            onChange={(provider) => patch({ provider })}
          />
          {local && (
            <div className="settings-grid">
              <Field label="Text backend">
                <Select
                  value={settings.textBackend}
                  onChange={(e) => patch({ textBackend: e.target.value as ProviderSettings["textBackend"] })}
                >
                  <option value="ollama">Ollama</option>
                  <option value="compatible">OpenAI-compatible server</option>
                </Select>
              </Field>
              <Field label="Text server URL">
                <TextInput value={settings.textUrl} onChange={(e) => patch({ textUrl: e.target.value })} />
              </Field>
              <Field label="Text model">
                <TextInput list="studio-models" value={settings.textModel} onChange={(e) => patch({ textModel: e.target.value })} placeholder="Probe to list models" />
                <datalist id="studio-models">
                  {(probed?.models || []).map((m) => (
                    <option key={m.id} value={m.id} />
                  ))}
                </datalist>
              </Field>
              {settings.textBackend === "compatible" && (
                <Field label="API key">
                  <TextInput type="password" value={settings.textApiKey || ""} onChange={(e) => patch({ textApiKey: e.target.value })} />
                </Field>
              )}
              <Toggle label="Use GPU for local text" checked={settings.textUseGpu} onChange={(textUseGpu) => patch({ textUseGpu })} />
            </div>
          )}
          <div className="settings-grid">
            <Field label="Image backend (ComfyUI) URL">
              <TextInput value={settings.comfyUrl} onChange={(e) => patch({ comfyUrl: e.target.value })} />
            </Field>
            <Field label="Image workflow preset">
              <Select
                value={settings.imagePreset}
                onChange={(e) => patch({ imagePreset: e.target.value as ProviderSettings["imagePreset"] })}
              >
                <option value="krea2">Krea 2</option>
                <option value="sdxl">SDXL</option>
                <option value="custom">Custom workflow</option>
              </Select>
            </Field>
            <Field label="Diffusion model">
              <TextInput value={settings.imageModel} onChange={(e) => patch({ imageModel: e.target.value })} />
            </Field>
            {settings.imagePreset !== "krea2" && (
              <>
                <Field label="Text encoder">
                  <TextInput value={settings.textEncoder} onChange={(e) => patch({ textEncoder: e.target.value })} />
                </Field>
                <Field label="VAE">
                  <TextInput value={settings.vae} onChange={(e) => patch({ vae: e.target.value })} />
                </Field>
              </>
            )}
            {settings.imagePreset === "custom" && (
              <>
                <Field label="Model root">
                  <TextInput value={settings.modelRoot} onChange={(e) => patch({ modelRoot: e.target.value })} />
                </Field>
                <Field label="Workflow JSON (paste)">
                  <textarea className="input textarea" rows={3} value={settings.workflow || ""} onChange={(e) => patch({ workflow: e.target.value })} />
                </Field>
                <Field label="Prompt node">
                  <TextInput value={settings.promptNode} onChange={(e) => patch({ promptNode: e.target.value })} />
                </Field>
                <Field label="Output node">
                  <TextInput value={settings.outputNode} onChange={(e) => patch({ outputNode: e.target.value })} />
                </Field>
              </>
            )}
          </div>
          <Btn variant="ghost" loading={busy} onClick={() => void probe()}>
            <WandSparkles size={15} /> Probe endpoints
          </Btn>
          {probed && (
            <div className="probe-result" role="status">
              <Kicker>Probe results</Kicker>
              <p>
                {(probed.models?.length || 0)} text models
                {probed.textError ? ` · ${probed.textError}` : ""}
                {probed.comfy ? ` · comfy: ${Object.entries(probed.comfy).map(([k, v]) => `${k} ${v?.length ?? 0}`).join(", ")}` : ""}
                {probed.imageError ? ` · ${probed.imageError}` : ""}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="settings-body">
          {account ? (
            <div className="account-card">
              <span className={cn("status-dot-lg", account.connected ? "dot-ok" : "dot-idle")} />
              <div>
                <strong>{account.connected ? account.email || "Connected" : "Not connected"}</strong>
                <p>
                  {account.provider || "OpenAI"}
                  {account.plan ? ` · ${account.plan}` : ""}
                  {account.available ? "" : " · unavailable"}
                </p>
              </div>
              {account.connected ? (
                <Btn variant="quiet" onClick={() => void accountAction("logout")}>
                  <LogOut size={15} /> Sign out
                </Btn>
              ) : (
                <Btn variant="primary" onClick={() => void accountAction("login")}>
                  <LogIn size={15} /> Sign in
                </Btn>
              )}
            </div>
          ) : (
            <p className="muted">Account status unavailable while the engine is offline.</p>
          )}
          {account?.error ? <ErrorNote>{account.error}</ErrorNote> : null}
        </div>
      )}
    </Modal>
  );
}

function useSettingsToasts() {
  const { settingsOpen, setSettingsOpen, pushToast } = useStudio();
  return { settingsOpen, setSettingsOpen, pushToast };
}
