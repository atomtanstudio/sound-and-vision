import { useEffect, useMemo, useState } from "react";
import { artistOf, useHouseArtist } from "../lib/artist";
import { api, ApiError } from "../lib/api";
import { linkTo } from "../lib/router";
import type { Project } from "../lib/types";
import { useSong } from "../state/song";
import { Button, Modal } from "../ui/controls";
import type { Brand } from "./BrandPage";
import { LookEditor } from "./LookEditor";
import { mergeLook, type Look } from "./look";
import { machine } from "../lib/machine";

/** This song's own look: the title, the artist and the logos on its cover (and its living cover), laid over the
 *  house look from Brand. Saving sets the cover again at once; the picture is kept. */
export function CoverLook({ project, onClose }: { project: Project; onClose: () => void }) {
  const [brand, setBrand] = useState<Brand | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const house = useHouseArtist();
  const own = typeof project.artist === "string" ? project.artist : null;
  const [name, setName] = useState<string | null>(null);
  const shownName = name ?? own ?? "";
  const commitName = async () => {
    if (name === null || name.trim() === (own ?? "")) return;
    setBusy("name");
    setError(null);
    try {
      useSong.getState().onProject(await api.put<Project>(`/api/projects/${project.id}/artist`, { artist: name.trim() || null }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  useEffect(() => { void api.get<Brand>("/api/brand").then(setBrand).catch(() => setError("The brand settings didn't load.")); }, []);
  const look = useMemo(() => (brand ? mergeLook(brand.look, project.layout) : null), [brand, project.layout]);
  const save = async (layout: Look | null) => {
    setBusy(layout ? "save" : "house");
    setError(null);
    try {
      const p = await api.put<Project>(`/api/projects/${project.id}/layout`, { layout });
      useSong.getState().onProject(p);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : `That didn't reach ${machine()}. Try again.`);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal title={`The look of ${project.title}`} onClose={onClose} full>
      {error && <p className="ie-err">{error}</p>}
      {brand && look ? (
        <LookEditor picture={`/api/projects/${project.id}/cover/picture`} infoUrl={`/api/projects/${project.id}/cover/picture/info`}
          W={3000} H={3000} look={look} title={project.title} artist={artistOf({ ...project, artist: name === null ? project.artist : name.trim() || undefined }, house)} logos={brand.logos}
          artistName={{
            label: "This song's artist", value: shownName, saving: busy === "name",
            placeholder: project.source?.artist || house || "Add the artist",
            note: "Left empty, the song carries " + (project.source?.artist ? "the artist its file came with." : "your artist name from Brand."),
            onChange: setName, onCommit: () => void commitName(),
          }}
          saving={busy === "save"} saveLabel="Set the cover with this look" onSave={(l) => void save(l)} onCancel={onClose}
          extra={(
            <div className="lk-group">
              <h4>{project.layout ? "This song has a look of its own" : "This song uses the house look"}</h4>
              <p className="la-note">Changes here are for this song only. The house look is on <a {...linkTo("/share/brand", onClose)}>the Brand page</a>.</p>
              {project.layout && (
                <Button size="sm" kind="ghost" busy={busy === "house"} onClick={() => void save(null)}>Use the house look again</Button>
              )}
            </div>
          )} />
      ) : <p className="mi-soon">Opening…</p>}
    </Modal>
  );
}
