import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useQuery } from "../lib/router";
import type { Influence, Project } from "../lib/types";
import { useRuns } from "../state/runs";
import { AddInfluence } from "../song/AddInfluence";
import { NewRun, RunCard } from "./Runs";
import "../shell/home.css";
import "../song/music-index.css";
import "./influence.css";
import { machine } from "../lib/machine";

/** The Influence Engine: train a new influence when a sound isn't coming out right, the influences you
 * have, and adding your own. A take's "Needs more influence" lands here with the song attached. */
export function InfluenceEngine() {
  const [list, setList] = useState<Influence[] | null>(null);
  const [song, setSong] = useState<Project | null>(null);
  const runs = useRuns((s) => s.runs);
  const loaded = useRuns((s) => s.loaded);
  const projectId = useQuery("project") || undefined;
  const takeId = useQuery("take") || undefined;

  const load = () => api.get<Influence[]>("/api/influences").then(setList).catch(() => setList([]));
  useEffect(() => {
    void load();
    void useRuns.getState().load().catch(() => undefined);
  }, []);
  useEffect(() => {
    if (projectId) void api.get<Project>(`/api/projects/${projectId}`).then(setSong).catch(() => setSong(null));
    else setSong(null);
  }, [projectId]);
  const keptIds = Object.values(runs).map((r) => r.kept?.influenceId).join();
  useEffect(() => {
    if (keptIds) void load();
  }, [keptIds]);

  const ordered = Object.values(runs).sort((a, b) => b.createdAt - a.createdAt);
  return (
    <main className="hm mi ie">
      <header className="mi-head">
        <div>
          <h1>Influence Engine</h1>
          <p>Influences steer a song model toward a style, a genre or an artist's sound. When a sound isn't coming out
            right, train a new one here: it's researched, gathered and trained on {machine()}, and you choose the result by ear.</p>
        </div>
      </header>

      <section className="ie-sec">
        <h2>Train a new influence</h2>
        <NewRun projectId={projectId} takeId={takeId} songTitle={song?.title} />
      </section>

      {ordered.length > 0 && (
        <section className="ie-sec">
          <h2>Training</h2>
          <div className="ie-runs">
            {ordered.map((r) => <RunCard key={r.id} run={r} />)}
          </div>
        </section>
      )}
      {!loaded && <p className="ie-none">Loading…</p>}

      <section className="ie-sec">
        <h2>Your influences</h2>
        <div className="ie-grid">
          {list?.map((i) => (
            <article key={i.id} className="ie-card">
              <span className="ie-kind">{i.kind}</span>
              <strong>{i.name}</strong>
              <p>{i.about || "No description yet."}</p>
              <span className="ie-meta">{i.models.join(", ").replace("yue2", "YuE2").replace("ace15", "ACE-Step 1.5")} · starts at {Math.round(i.recommended * 100)}%</span>
            </article>
          ))}
          {list && list.length === 0 && <p className="ie-none">None yet.</p>}
        </div>
      </section>
      <section className="ie-sec">
        <h2>Add your own</h2>
        <div className="ie-panel"><AddInfluence onAdded={() => void load()} /></div>
      </section>
    </main>
  );
}
