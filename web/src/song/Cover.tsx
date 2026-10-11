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
  const make = () =>
    // (the model and settings from Settings go with the covers' own choice; another one uses its default)
    okToSpend(chosen, "this picture", engine === settings?.engine ? settings?.using?.covers : "") && run("make", async () => {
      if (settings && (engine !== settings.engine || (!cover && artist !== settings.artist))) {
        await api.put("/api/covers/settings", { engine, artist: cover ? undefined : artist });
      }
      const j = await api.post<Job>(`/api/projects/${project.id}/cover`, { engine, note });
      useSong.getState().onJob(j);
    });
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
            </section>
          )}
          <section>
            <h3>{cover ? "A new picture" : "Make the cover"}</h3>
            <Segmented label="Made with" value={engine} onChange={setEngine}
              options={(settings?.choices ?? []).map((c) => ({ value: c.id, label: choiceLabel(c), hint: c.note }))} />
            <p className="cv-note">
              {chosen?.note}
              {" "}{Doer(roles, "chores")} reads the song and imagines the picture; the title{artist ? ", the artist" : ""} and your logos are set on it here.
            </p>
            {!cover && (
              <label className="cv-field">
                <span>Artist (optional)</span>
                <input value={artist} placeholder="Your artist name" onChange={(e) => setArtist(e.target.value)} />
              </label>
            )}
            <label className="cv-field">
              <span>Direction (optional)</span>
              <TextArea minRows={2} value={note} placeholder="“A lone car on a coastal road at dawn”, “risograph, two colors”…"
                onChange={(e) => setNote(e.target.value)} />
            </label>
            <Button kind="primary" busy={busy === "make"} disabled={!!job || !!busy} onClick={() => void make()}>
              {cover ? "Make a new picture" : "Make the cover"}
            </Button>
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
