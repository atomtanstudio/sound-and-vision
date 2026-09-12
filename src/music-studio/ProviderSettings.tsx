import { useEffect, useState } from "react";
import { request } from "./api";

type Node = { class_type: string; inputs: Record<string, unknown> };
export type ProviderSettings = {
  provider: "openai" | "local";
  textBackend: "ollama" | "compatible";
  textUrl: string;
  textModel: string;
  textApiKey?: string | null;
  hasTextApiKey?: boolean;
  textUseGpu: boolean;
  comfyUrl: string;
  imagePreset: "krea2" | "sdxl" | "custom";
  imageModel: string;
  textEncoder: string;
  vae: string;
  modelRoot: string;
  workflow: Record<string, Node> | null;
  promptNode: string;
  promptInput: string;
  outputNode: string;
};
type Probe = {
  models: { id: string; name: string }[];
  comfy: {
    diffusionModels?: string[];
    checkpoints?: string[];
    textEncoders?: string[];
    vaes?: string[];
  };
  textError?: string | null;
  imageError?: string | null;
};

function ModelChoice({
  label,
  value,
  options,
  change,
}: {
  label: string;
  value: string;
  options: string[];
  change: (v: string) => void;
}) {
  const id = "models-" + label.replace(/\W/g, "").toLowerCase();
  return (
    <label>
      {label}
      <input
        aria-label={label}
        list={id}
        value={value}
        onChange={(e) => change(e.target.value)}
      />
      <datalist id={id}>
        {options.map((v) => (
          <option key={v} value={v} />
        ))}
      </datalist>
    </label>
  );
}

export function ProviderSettingsPanel({
  children,
  refresh,
}: {
  children: React.ReactNode;
  refresh: () => void;
}) {
  const [config, setConfig] = useState<ProviderSettings | null>(null),
    [probe, setProbe] = useState<Probe | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [paths, setPaths] = useState("");
  const [testId, setTestId] = useState<string | null>(() =>
    localStorage.getItem("sv-provider-test"),
  );
  const [test, setTest] = useState<{
    state: string;
    error?: string;
    result?: {
      proposal?: { style: string };
      previewUrl?: string;
      model?: string;
    };
  } | null>(null);
  useEffect(() => {
    if (!testId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const job = await request<NonNullable<typeof test>>(
          "/assistance/" + testId,
        );
        if (alive) {
          setTest(job);
          if (["queued", "running", "waiting-for-resource"].includes(job.state))
            timer = setTimeout(poll, 2000);
        }
      } catch (e) {
        if (alive) {
          setError((e as Error).message);
          setTestId(null);
          localStorage.removeItem("sv-provider-test");
        }
      }
    };
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [testId]);
  const testBusy =
    !!testId &&
    (!test ||
      ["queued", "running", "waiting-for-resource"].includes(test.state));
  useEffect(() => {
    let alive = true;
    request<{ config: ProviderSettings; modelPathsYaml: string }>("/providers")
      .then((r) => {
        if (alive) {
          setConfig(r.config);
          setPaths(r.modelPathsYaml);
        }
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);
  function update(patch: Partial<ProviderSettings>) {
    setConfig((old) => {
      if (!old) return null;
      const serverChanged =
        (patch.textUrl !== undefined && patch.textUrl !== old.textUrl) ||
        (patch.textBackend !== undefined &&
          patch.textBackend !== old.textBackend);
      return {
        ...old,
        ...patch,
        ...(serverChanged ? { textApiKey: null, hasTextApiKey: false } : {}),
      };
    });
    setNotice("");
    if ("textUrl" in patch || "comfyUrl" in patch || "textBackend" in patch)
      setProbe(null);
    if ("modelRoot" in patch) setPaths("");
  }
  function payload() {
    if (!config) return {};
    const { hasTextApiKey: _, ...body } = config;
    return body;
  }
  async function run(save: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (save) {
        const r = await request<{
          config: ProviderSettings;
          modelPathsYaml: string;
        }>("/providers", payload(), "PUT");
        setConfig(r.config);
        setPaths(r.modelPathsYaml);
        setNotice("AI setup saved.");
        refresh();
      } else {
        const r = await request<Probe>("/providers/probe", payload());
        setProbe(r);
        setNotice(
          r.textError || r.imageError
            ? "Connection check finished. Resolve the messages below."
            : "Both local providers are ready.",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function testProvider(kind: "writing" | "image") {
    setBusy(true);
    setError("");
    try {
      const id = crypto.randomUUID();
      const job = await request<NonNullable<typeof test>>("/providers/tests", {
        requestId: id,
        kind,
        config: payload(),
      });
      setTest(job);
      localStorage.setItem("sv-provider-test", id);
      setTestId(id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importWorkflow(file: File | undefined) {
    if (!file) return;
    try {
      if (file.size > 750000)
        throw new Error("Use an API workflow under 750 KB.");
      const graph = JSON.parse(await file.text()) as Record<string, Node>;
      if (
        !Object.keys(graph).length ||
        Object.values(graph).some((n) => !n?.class_type || !n?.inputs)
      )
        throw new Error(
          "Export the workflow in ComfyUI API format, not the canvas format.",
        );
      const prompt = Object.entries(graph).find(
        ([, n]) =>
          n.class_type === "CLIPTextEncode" &&
          typeof n.inputs.text === "string",
      );
      const output = Object.entries(graph).find(
        ([, n]) => n.class_type === "SaveImage",
      );
      update({
        workflow: graph,
        promptNode: prompt?.[0] || "",
        promptInput: "text",
        outputNode: output?.[0] || "",
      });
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const promptChoices = config?.workflow
    ? Object.entries(config.workflow).flatMap(([id, n]) =>
        Object.entries(n.inputs)
          .filter(([, v]) => typeof v === "string")
          .map(([field]) => ({
            id,
            field,
            label: `${id} · ${n.class_type} · ${field}`,
          })),
      )
    : [];
  if (!config)
    return (
      <>
        {children}
        {error && <p role="alert">AI setup: {error}</p>}
      </>
    );
  return (
    <div className="provider-settings">
      <fieldset className="provider-fields" disabled={busy || testBusy}>
        <p>
          Choose how this installation creates writing and artwork. Music
          generation runs locally with either option.
        </p>
        <fieldset className="provider-choice">
          <legend>AI provider</legend>
          <label>
            <input
              type="radio"
              name="ai-provider"
              checked={config.provider === "openai"}
              onChange={() => update({ provider: "openai" })}
            />{" "}
            OpenAI account
          </label>
          <label>
            <input
              type="radio"
              name="ai-provider"
              checked={config.provider === "local"}
              onChange={() => update({ provider: "local" })}
            />{" "}
            Local models
          </label>
        </fieldset>
        {config.provider === "openai" ? (
          children
        ) : (
          <>
            <p className="field-note">
              No OpenAI account is needed. Server addresses are reached from the
              Sound/Vision backend, which may be on a different computer from
              this browser.
            </p>
            <h3>Writing</h3>
            <label>
              Text server
              <select
                aria-label="Text server"
                value={config.textBackend}
                onChange={(e) =>
                  update({
                    textBackend: e.target
                      .value as ProviderSettings["textBackend"],
                    textUrl:
                      e.target.value === "ollama"
                        ? "http://127.0.0.1:11434"
                        : "http://127.0.0.1:1234/v1",
                  })
                }
              >
                <option value="ollama">Ollama (recommended)</option>
                <option value="compatible">
                  LM Studio / llama.cpp / compatible server
                </option>
              </select>
            </label>
            <label>
              Text server URL
              <input
                aria-label="Text server URL"
                value={config.textUrl}
                onChange={(e) => update({ textUrl: e.target.value })}
              />
            </label>
            <ModelChoice
              label="Text model"
              value={config.textModel}
              options={probe?.models.map((m) => m.id) || []}
              change={(textModel) => update({ textModel })}
            />
            <p className="field-note">
              Start with Qwen3.5 4B; choose 9B for more capacity. Install it on
              the text server with <code>ollama pull qwen3.5:4b</code>.{" "}
              <a
                href="https://ollama.com/download"
                target="_blank"
                rel="noreferrer"
              >
                Get Ollama ↗
              </a>
            </p>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={config.textUseGpu}
                onChange={(e) => update({ textUseGpu: e.target.checked })}
              />{" "}
              Share the music GPU for writing
            </label>
            <p className="field-note">
              Ollama uses CPU when unchecked and unloads the model after each
              request. For other servers, configure CPU use or model unloading
              in that server.
            </p>
            {config.textBackend === "compatible" && (
              <label>
                Server API key (optional)
                <input
                  aria-label="Local server API key"
                  type="password"
                  autoComplete="off"
                  value={config.textApiKey || ""}
                  placeholder={
                    config.hasTextApiKey
                      ? "Saved for this server; leave blank to keep it"
                      : ""
                  }
                  onChange={(e) => update({ textApiKey: e.target.value })}
                />
              </label>
            )}
            {config.textBackend === "compatible" && (
              <p className="field-note">
                Saved keys are reused only for the same server address and type.
                Enter a new key after changing servers.
              </p>
            )}
            <h3>Images</h3>
            <label>
              ComfyUI URL
              <input
                aria-label="ComfyUI URL"
                value={config.comfyUrl}
                onChange={(e) => update({ comfyUrl: e.target.value })}
              />
            </label>
            <label>
              Image workflow
              <select
                aria-label="Image workflow"
                value={config.imagePreset}
                onChange={(e) =>
                  update({
                    imagePreset: e.target
                      .value as ProviderSettings["imagePreset"],
                    imageModel:
                      e.target.value === "krea2"
                        ? "krea2_turbo_fp8_scaled.safetensors"
                        : "",
                  })
                }
              >
                <option value="krea2">Krea 2 Turbo (recommended)</option>
                <option value="sdxl">SDXL checkpoint</option>
                <option value="custom">Custom ComfyUI API workflow</option>
              </select>
            </label>
            {config.imagePreset !== "custom" && (
              <ModelChoice
                label="Image model"
                value={config.imageModel}
                options={
                  (config.imagePreset === "sdxl"
                    ? probe?.comfy.checkpoints
                    : probe?.comfy.diffusionModels) || []
                }
                change={(imageModel) => update({ imageModel })}
              />
            )}
            {config.imagePreset === "krea2" && (
              <>
                <ModelChoice
                  label="Text encoder"
                  value={config.textEncoder}
                  options={probe?.comfy.textEncoders || []}
                  change={(textEncoder) => update({ textEncoder })}
                />
                <ModelChoice
                  label="Image VAE"
                  value={config.vae}
                  options={probe?.comfy.vaes || []}
                  change={(vae) => update({ vae })}
                />
                <p className="field-note">
                  Krea 2 uses separate diffusion, text-encoder and VAE files.{" "}
                  <a
                    href="https://docs.comfy.org/tutorials/image/krea/krea-2"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Model downloads and folder guide ↗
                  </a>
                </p>
              </>
            )}
            {config.imagePreset === "custom" && (
              <>
                <label>
                  API workflow JSON
                  <input
                    aria-label="API workflow JSON"
                    type="file"
                    accept="application/json,.json"
                    onChange={(e) => void importWorkflow(e.target.files?.[0])}
                  />
                </label>
                <p className="field-note">
                  Export a working text-to-image workflow in ComfyUI API format.
                  Its model and resolution settings are retained; each image
                  gets a fresh sampler seed.
                </p>
                {config.workflow && (
                  <>
                    <label>
                      Positive prompt field
                      <select
                        aria-label="Positive prompt field"
                        value={JSON.stringify([
                          config.promptNode,
                          config.promptInput,
                        ])}
                        onChange={(e) => {
                          const [promptNode, promptInput] = JSON.parse(
                            e.target.value,
                          );
                          update({ promptNode, promptInput });
                        }}
                      >
                        <option value="">Choose a text input</option>
                        {promptChoices.map((p) => (
                          <option
                            key={p.label}
                            value={JSON.stringify([p.id, p.field])}
                          >
                            {p.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Image output
                      <select
                        aria-label="Image output"
                        value={config.outputNode}
                        onChange={(e) => update({ outputNode: e.target.value })}
                      >
                        <option value="">Choose SaveImage</option>
                        {Object.entries(config.workflow)
                          .filter(([, n]) => n.class_type === "SaveImage")
                          .map(([id]) => (
                            <option key={id} value={id}>
                              SaveImage · {id}
                            </option>
                          ))}
                      </select>
                    </label>
                  </>
                )}
              </>
            )}
            <details>
              <summary>Models stored in another folder</summary>
              <p className="field-note">
                The picker reads ComfyUI’s model index, including its normal{" "}
                <code>models/diffusion_models</code> folder. For another
                location, enter the models root on the ComfyUI computer. Saving
                creates a configuration you can download and load in ComfyUI.
              </p>
              <label>
                ComfyUI models root
                <input
                  aria-label="ComfyUI models root"
                  placeholder="/srv/ai/models/comfyui or D:\\AI\\models"
                  value={config.modelRoot}
                  onChange={(e) => update({ modelRoot: e.target.value })}
                />
              </label>
              {paths && (
                <>
                  <button
                    className="text-button"
                    onClick={() => {
                      const url = URL.createObjectURL(
                        new Blob([paths], { type: "text/yaml" }),
                      );
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "soundvision-model-paths.yaml";
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download model-folder configuration
                  </button>
                  <p className="field-note">
                    Start ComfyUI with{" "}
                    <code>
                      --extra-model-paths-config
                      /path/to/soundvision-model-paths.yaml
                    </code>
                    , then refresh the model list here. For Docker, use the
                    model path inside its container.
                  </p>
                </>
              )}
            </details>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => void run(false)}
            >
              {busy ? "Checking…" : "Test connections & refresh models"}
            </button>
            <div className="provider-test-actions">
              <button
                className="secondary-button"
                disabled={busy || testBusy}
                onClick={() => void testProvider("writing")}
              >
                Test writing
              </button>
              <button
                className="secondary-button"
                disabled={busy || testBusy}
                onClick={() => void testProvider("image")}
              >
                Generate test image
              </button>
            </div>
            {test && (
              <div className="provider-checks" role="status">
                {testBusy ? (
                  <p>Testing local models… This can take a few minutes.</p>
                ) : test.error ? (
                  <p>{test.error}</p>
                ) : (
                  <>
                    {test.result?.proposal && (
                      <p>{test.result.proposal.style}</p>
                    )}
                    {test.result?.previewUrl && (
                      <img
                        src={test.result.previewUrl}
                        alt="Local image generation test"
                        style={{ width: "100%", borderRadius: 6 }}
                      />
                    )}
                    <p>{test.result?.model}</p>
                  </>
                )}
              </div>
            )}
            {probe && (
              <div className="provider-checks" role="status">
                <p>
                  Writing:{" "}
                  {probe.textError || "Connected; selected model installed"}
                </p>
                <p>
                  Images:{" "}
                  {probe.imageError ||
                    "Connected; workflow models and nodes available"}
                </p>
              </div>
            )}
          </>
        )}
        <button
          className="primary-button"
          disabled={busy || testBusy}
          onClick={() => void run(true)}
        >
          Save AI setup
        </button>
      </fieldset>
      {testBusy && (
        <button
          className="text-button"
          onClick={() =>
            void request("/assistance/" + testId + "/cancel", {})
              .then(() =>
                setNotice(
                  "Cancellation requested. A running local image finishes before releasing the GPU.",
                ),
              )
              .catch((e) => setError(e.message))
          }
        >
          Cancel test
        </button>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
