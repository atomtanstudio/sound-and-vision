import { useEffect } from "react";
import { fileUrl } from "../lib/api";
import { go, linkTo, useQuery } from "../lib/router";
import { useSong } from "../state/song";
import { KineticFilm } from "./KineticFilm";
import { LivingAlbum } from "./LivingAlbum";
import "./video.css";
import { machine } from "../lib/machine";

type Kind = "living" | "kinetic" | "music";

/** One song's videos: Living Album Cover, Motion Graphics and Music Video. The kind is kept in the
 *  address (?kind=kinetic), so a reload or a shared link opens the same one. */
export function VideoStudio({ id }: { id: string }) {
  const { project, error, load, takes } = useSong();
  const asked = useQuery("kind");
  const kind: Kind = asked === "kinetic" || asked === "music" ? asked : "living";
  const choose = (k: Kind) => go(k === "living" ? `/video/${id}` : `/video/${id}?kind=${k}`, true);
  useEffect(() => {
    void load(id);
  }, [id, load]);
  if (error && !project) return <main className="sp-msg">{error}</main>;
  if (!project || project.id !== id) return <main className="sp-msg sp-loading">Opening the song…</main>;
  const master = takes.find((t) => t.id === project.masterTake && t.status === "ready");
  return (
    <main className="vs">
      <header className="vs-head">
        {project.cover && <img className="vs-cover" src={fileUrl(project.id, project.cover.small)} alt="" />}
        <div className="vs-title">
          <h1>{project.title}</h1>
          <a {...linkTo(`/music/${project.id}`)}>← The song</a>
        </div>
        <nav className="vs-kinds" aria-label="Kind of video">
          <button type="button" className={"vs-kind" + (kind === "living" ? " on" : "")} aria-pressed={kind === "living"}
            onClick={() => choose("living")}>Living Album Cover</button>
          <button type="button" className={"vs-kind" + (kind === "kinetic" ? " on" : "")} aria-pressed={kind === "kinetic"}
            onClick={() => choose("kinetic")}>Motion Graphics</button>
          <button type="button" className={"vs-kind" + (kind === "music" ? " on" : "")} aria-pressed={kind === "music"}
            onClick={() => choose("music")}>Music Video</button>
        </nav>
      </header>
      {!master ? (
        takes.some((t) => t.id === project.masterTake && t.status !== "ready" && t.status !== "failed") ? (
          <p className="vs-need">The song is still coming in: {machine()} is finding its words, beat and stems. Its videos open here
            when that's done (<a {...linkTo(`/music/${project.id}`)}>see how it's going</a>).</p>
        ) : (
          <p className="vs-need">This song needs its take chosen first: open <a {...linkTo(`/music/${project.id}`)}>the song</a> and press “Use this one”.</p>
        )
      ) : (
        kind === "living" ? <LivingAlbum project={project} /> : <KineticFilm key={kind} project={project} mode={kind} />
      )}
    </main>
  );
}
