import { useEffect, useState } from "react";
import { api, ApiError, fileUrl } from "../lib/api";
import type { Job } from "../lib/types";
import { CoverLook } from "../look/CoverLook";
import { useSong } from "../state/song";
import { Button, Modal, Segmented, TextArea } from "../ui/controls";
import { machine } from "../lib/machine";
import { choiceLabel, okToSpend, type PictureChoice, type Using } from "../lib/pictures";
import { Doer, useWho } from "../state/who";

interface CoverSettings {
  engine: string;
  auto: string;
  artist: string;
  choices: PictureChoice[];
  using?: Using;
}

/** The song's sleeve beside its title: the art, or a button to make it. Opens the cover panel. */
export function CoverThumb() {
  const project = useSong((s) => s.project);
  const job = useSong((s) => Object.values(s.jobs).find((j) => j.kind.startsWith("cover.") && j.projectId === project?.id &&
    (j.status === "queued" || j.status === "running")));
  const [open, setOpen] = useState(false);
  if (!project) return null;
  const cover = project.cover;
  return (
    <>
      <button type="button" className={"cv-thumb" + (cover ? "" : " cv-empty") + (job ? " cv-busy" : "")} onClick={() => setOpen(true)}
        title={cover ? "The cover" : "Make cover art"}>
        {cover ? <img src={fileUrl(project.id, cover.small)} alt="Cover" /> : <span>{job ? "" : "+ Cover"}</span>}
        {job && <span className="cv-spin" aria-label={job.message || "Making the cover"} />}
      </button>
      {open && <CoverPanel job={job} onClose={() => setOpen(false)} />}
    </>
  );
}

function CoverPanel({ job, onClose }: { job?: Job; onClose: () => void }) {
  const roles = useWho((w) => w.roles);
  const project = useSong((s) => s.project)!;
  const failed = useSong((s) => Object.values(s.jobs).filter((j) => j.kind.startsWith("cover.") && j.projectId === project.id)
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0]);
  const cover = project.cover;
  const [settings, setSettings] = useState<CoverSettings | null>(null);
  const [engine, setEngine] = useState("local");
  const [note, setNote] = useState("");
  const [mine, setMine] = useState(false); // the person writes the prompt, rather than the small-chores model
  const [own, setOwn] = useState("");
  const [artist, setArtist] = useState(cover?.artist ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [looking, setLooking] = useState(false);

  useEffect(() => {
    void api.get<CoverSettings>("/api/covers/settings").then((s) => {
      setSettings(s);
      setEngine(s.engine);
      if (!cover) setArtist(s.artist);
    });
  }, [cover]);

  const run = async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  const chosen = settings?.choices.find((c) => c.id === engine);
  // a new picture: from a prompt the small-chores model writes (steered by the direction), from the person's own
  // prompt, or from the same prompt as the cover now ("again")
  const make = (how: "new" | "mine" | "again") =>
    // (the model and settings from Settings go with the covers' own choice; another one uses its default)
    okToSpend(chosen, "this picture", engine === settings?.engine ? settings?.using?.covers : "") && run(how, async () => {
      if (settings && (engine !== settings.engine || (!cover && artist !== settings.artist))) {
        await api.put("/api/covers/settings", { engine, artist: cover ? undefined : artist });
      }
      const prompt = how === "mine" ? own.trim() : how === "again" ? cover?.prompt ?? "" : "";
      const j = await api.post<Job>(`/api/projects/${project.id}/cover`, { engine, note: how === "new" ? note : "", prompt });
      useSong.getState().onJob(j);
    });
  const writeMine = (from: string) => {
    setMine(true);
    setOwn(from);
  };
  const earlier = (project.covers ?? []).filter((c) => c.n !== cover?.n).slice(-8).reverse();
  const reset = () => run("text", () => api.post(`/api/projects/${project.id}/cover/text`, { artist }));
  const stale = cover && cover.title !== project.title;

  return (
    <Modal title="Cover art" onClose={onClose} wide>
      <div className="cv-panel">
        <div className="cv-big">
          {cover ? (
            <img src={fileUrl(project.id, cover.small)} alt={`The cover of ${project.title}`} />
          ) : (
            <div className="cv-none">{job ? "" : "No cover yet"}</div>
          )}
          {job && (
            <div className="cv-working" role="status">
              <span className="ln-spin" aria-hidden="true" />
              {job.message || "Making the cover"}
            </div>
          )}
        </div>
        <div className="cv-side">
          {cover && (
            <section>
              <h3>The sleeve</h3>
              <label className="cv-field">
                <span>Artist (optional)</span>
                <input value={artist} placeholder="Your artist name" onChange={(e) => setArtist(e.target.value)} />
              </label>
              <div className="cv-row">
                <Button size="sm" busy={busy === "text"} disabled={artist === cover.artist && !stale}
                  onClick={() => void reset()}>
                  {stale ? "Use the new title" : "Update the sleeve"}
                </Button>
                <Button size="sm" onClick={() => setLooking(true)}>Edit the look</Button>
                <a className="cv-dl" href={fileUrl(project.id, cover.file)} download={`${project.title || "cover"}.jpg`}>
                  Download 3000 px
                </a>
              </div>
              {looking && <CoverLook project={project} onClose={() => setLooking(false)} />}
              {cover.by?.concept && <p className="cv-note">The idea: {cover.by.concept}</p>}
              <p className="cv-note">Made with {cover.made.model}{cover.made.cost ? ` · about ${Math.round(cover.made.cost * 100)}¢` : ""}.</p>
              {cover.prompt && (
                <details className="cv-prompt">
                  <summary>{cover.by?.provider === "you" ? "Your prompt" : "The prompt it was made from"}</summary>
                  <p>{cover.prompt}</p>
                  <button type="button" className="cv-link" onClick={() => writeMine(cover.prompt)}>Change it and make another</button>
                </details>
              )}
            </section>
          )}
          {earlier.length > 0 && (
            <section className="cv-earlier">
              <h3>Earlier pictures</h3>
              <div>
                {earlier.map((c) => (
                  <button key={c.n} type="button" title={c.by?.concept ?? `Picture ${c.n}`} disabled={!!busy || !!job}
                    aria-label={`Make picture ${c.n} the cover again`}
                    onClick={() => void run("use", () => api.post(`/api/projects/${project.id}/cover/use`, { n: c.n }))}>
                    <img src={`/api/projects/${project.id}/covers/${c.n}/thumb.jpg`} alt="" loading="lazy" />
                  </button>
                ))}
              </div>
              <p className="cv-note">Click one to make it the cover again.</p>
            </section>
          )}
          <section>
            <h3>{cover ? "A new picture" : "Make the cover"}</h3>
            <Segmented label="Made with" value={engine} onChange={setEngine}
              options={(settings?.choices ?? []).map((c) => ({ value: c.id, label: choiceLabel(c), hint: c.note }))} />
            <p className="cv-note">{chosen?.note}</p>
            <Segmented size="sm" label="The prompt" value={mine ? "mine" : "theirs"}
              onChange={(v) => (v === "mine" ? writeMine(own || cover?.prompt || "") : setMine(false))}
              options={[{ value: "theirs", label: `${Doer(roles, "chores")} writes it` }, { value: "mine", label: "I'll write it" }]} />
            {!cover && (
              <label className="cv-field">
                <span>Artist (optional)</span>
                <input value={artist} placeholder="Your artist name" onChange={(e) => setArtist(e.target.value)} />
              </label>
            )}
            {mine ? (
              <>
                <label className="cv-field">
                  <span>Your prompt</span>
                  <TextArea minRows={4} maxLength={1400} value={own}
                    placeholder="The picture: what's in it, where, the light, the style…"
                    onChange={(e) => setOwn(e.target.value)} />
                </label>
                <p className="cv-note">Used as you wrote it. The title{artist ? ", the artist" : ""} and your logos are set on it here, so the picture itself needs no words.</p>
              </>
            ) : (
              <>
                <p className="cv-note">{Doer(roles, "chores")} reads the song and imagines a new picture each time; the title{artist ? ", the artist" : ""} and your logos are set on it here.</p>
                <label className="cv-field">
                  <span>Direction (optional)</span>
                  <TextArea minRows={2} value={note} placeholder="“A lone car on a coastal road at dawn”, “risograph, two colors”…"
                    onChange={(e) => setNote(e.target.value)} />
                </label>
              </>
            )}
            <div className="cv-row">
              {mine ? (
                <Button kind="primary" busy={busy === "mine"} disabled={!!job || !!busy || !own.trim()} onClick={() => void make("mine")}>
                  Make it from my prompt
                </Button>
              ) : (
                <Button kind="primary" busy={busy === "new"} disabled={!!job || !!busy} onClick={() => void make("new")}>
                  {cover ? "Make a new picture" : "Make the cover"}
                </Button>
              )}
              {cover?.prompt && (
                <Button busy={busy === "again"} disabled={!!job || !!busy} onClick={() => void make("again")}>
                  Same prompt again
                </Button>
              )}
            </div>
          </section>
          {settings && (
            <section>
              <h3>Songs from the Home prompt</h3>
              <Segmented size="sm" label="A cover with every new song" value={settings.auto}
                onChange={(auto) => void api.put<CoverSettings>("/api/covers/settings", { auto }).then(setSettings)}
                options={[...settings.choices.filter((c) => !c.paid).map((c) => ({ value: c.id, label: choiceLabel(c), hint: c.note })),
                  { value: "off", label: "No cover" }]} />
              <p className="cv-note">Each song typed on Home gets a cover while its takes sing.</p>
            </section>
          )}
          {failed?.status === "failed" && !job && <p className="ie-err">The last try didn't work: {failed.message}</p>}
          {error && <p className="ie-err">{error}</p>}
        </div>
      </div>
    </Modal>
  );
}
