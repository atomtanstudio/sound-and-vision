import { useEffect, useState } from "react";
import { Download, FolderInput, RefreshCcw, Trash2, Video, WandSparkles, XCircle } from "lucide-react";
import { musicApi, request } from "../../music-studio/api";
import type { Track } from "../../music-studio/model";
import { useStudio } from "../context";
import { Btn, ErrorNote, Field, Kicker, Modal, Select, TextArea, TextInput, cn } from "../ui";
import { CoverArt } from "./CoverArt";

export const statusLabel = (track: Track) =>
  track.deletedAt
    ? "In trash"
    : track.status === "succeeded" || !track.status
      ? "Finished"
      : track.status === "failed"
        ? "Failed"
        : track.status === "cancelled"
          ? "Cancelled"
          : track.status === "needs-review"
            ? "Needs review"
            : track.status === "waiting-for-resource"
              ? "Waiting for GPU"
              : "Generating";

/* The song dossier: metadata, plan review, files and lifecycle actions. */
export function TrackDetail({
  track,
  onClose,
}: {
  track: Track | null;
  onClose: () => void;
}) {
  const { patchTrack, makeVideo, pushToast, refresh, upsertLocal } = useStudio();
  const [plan, setPlan] = useState<string | null>(null);
  const [error, setError] = useState("");
  const server = !!track?.source;
  useEffect(() => {
    setPlan(null);
    setError("");
    if (track?.status === "needs-review" && track.source)
      musicApi
        .plan(track.id)
        .then((p) => setPlan(p.abc))
        .catch(() => setPlan(""));
  }, [track?.id, track?.status]);
  if (!track) return null;
  const live = !!track.status && !["succeeded", "failed", "cancelled"].includes(track.status);
  const patch = (part: Partial<Track>) => patchTrack(track.id, part);
  const file = (name: string) => `/api/takes/${track.id}/files/${name}`;
  const saveMeta = (part: Partial<Track>) => {
    patch(part);
    if (server)
      musicApi
        .patch(track.id, part as { title?: string; project?: string })
        .then((updated) => upsertLocal([updated]))
        .catch((e) => setError((e as Error).message));
  };
  return (
    <Modal open onClose={onClose} title={track.title || "Untitled"} subtitle={`${track.project} · ${statusLabel(track)}`} wide>
      <div className="detail-grid">
        <div className="detail-side">
          <CoverArt track={track} className="detail-cover" ring={live} />
          <div className="detail-files">
            {server ? (
              <>
                <a className="btn btn-ghost btn-sm" href={file("audio.wav")} download>
                  <Download size={14} /> WAV
                </a>
                <a className="btn btn-ghost btn-sm" href={file("audio.flac")} download>
                  <Download size={14} /> FLAC
                </a>
                <a className="btn btn-ghost btn-sm" href={file("audio.mp3")} download>
                  <Download size={14} /> MP3
                </a>
              </>
            ) : null}
            {track.source === "yue2" ? (
              <a className="btn btn-ghost btn-sm" href={file("request.json")} download>
                <Download size={14} /> Request
              </a>
            ) : null}
            {server ? (
              <a className="btn btn-ghost btn-sm" href={file("delivery.json")} download>
                <Download size={14} /> Delivery
              </a>
            ) : null}
          </div>
          {track.form?.lora ? (
            <p className="detail-lora">
              <Kicker>Trained style</Kicker>
              <span>
                {track.form.lora.id} · strength {track.form.lora.strength}
              </span>
            </p>
          ) : null}
          {track.warnings?.length ? (
            <p className="detail-warnings">{track.warnings.join(" ")}</p>
          ) : null}
          {track.error ? <ErrorNote>{track.error}</ErrorNote> : null}
        </div>
        <div className="detail-main">
          <div className="detail-form">
            <Field label="Title">
              <TextInput value={track.title} onChange={(e) => patch({ title: e.target.value })} onBlur={(e) => saveMeta({ title: e.target.value })} />
            </Field>
            <Field label="Project">
              <TextInput value={track.project} onChange={(e) => patch({ project: e.target.value })} onBlur={(e) => saveMeta({ project: e.target.value })} />
            </Field>
          </div>
          {track.form ? (
            <div className="detail-brief">
              <Kicker>The brief</Kicker>
              <p>{track.form.description || track.form.style}</p>
              {track.form.lyrics ? (
                <>
                  <Kicker>Lyrics</Kicker>
                  <pre>{track.form.lyrics}</pre>
                </>
              ) : null}
            </div>
          ) : null}
          {track.status === "needs-review" && plan !== null ? (
            <div className="detail-plan">
              <Kicker>Review the score plan (ABC notation)</Kicker>
              <TextArea rows={6} value={plan} onChange={(e) => setPlan(e.target.value)} />
              <div className="detail-actions">
                <Btn
                  variant="primary"
                  onClick={() =>
                    musicApi
                      .continuePlan(track.id, plan || undefined)
                      .then(() => {
                        pushToast("Synthesis continues");
                        refresh();
                      })
                      .catch((e) => setError((e as Error).message))
                  }
                >
                  Continue synthesis
                </Btn>
              </div>
            </div>
          ) : null}
          <div className="detail-actions detail-actions-end">
            {server && track.status === "failed" ? (
              <Btn variant="ghost" onClick={() => musicApi.retry(track.id).then(refresh).catch((e) => setError((e as Error).message))}>
                <RefreshCcw size={15} /> Retry
              </Btn>
            ) : null}
            {live && server ? (
              <Btn variant="quiet" onClick={() => musicApi.cancel(track.id).then(refresh).catch((e) => setError((e as Error).message))}>
                <XCircle size={15} /> Cancel
              </Btn>
            ) : null}
            {track.deletedAt ? (
              <Btn
                variant="ghost"
                onClick={() =>
                  musicApi
                    .libraryAction([track.id], "restore")
                    .then(() => {
                      refresh();
                      onClose();
                    })
                    .catch((e) => setError((e as Error).message))
                }
              >
                Restore
              </Btn>
            ) : (
              <>
                <Btn
                  variant="ghost"
                  onClick={() => {
                    if (server)
                      musicApi
                        .libraryAction([track.id], "trash")
                        .then(() => {
                          refresh();
                          onClose();
                        })
                        .catch((e) => setError((e as Error).message));
                    else patchTrack(track.id, { deletedAt: Date.now() });
                  }}
                >
                  <Trash2 size={15} /> Move to trash
                </Btn>
                <Btn
                  variant="ghost"
                  onClick={() => {
                    if (server) request("/projects").then((r) => {
                      const next = (r as { projects: { name: string }[] }).projects.find((p) => p.name !== track.project)?.name;
                      if (next) musicApi.libraryAction([track.id], "move", next).then(refresh).catch((e) => setError((e as Error).message));
                    });
                    else saveMeta({ project: "Loose tracks" });
                  }}
                >
                  <FolderInput size={15} /> Move to project
                </Btn>
                <Btn variant="primary" onClick={() => { makeVideo(track); onClose(); }}>
                  <Video size={15} /> Make video
                </Btn>
              </>
            )}
            {server && !track.cover ? (
              <Btn variant="quiet" onClick={() => request(`/takes/${track.id}/cover`, {}).then(() => { pushToast("Cover art requested"); refresh(); }).catch((e) => setError((e as Error).message))}>
                <WandSparkles size={15} /> Request cover
              </Btn>
            ) : null}
          </div>
          <ErrorNote>{error}</ErrorNote>
        </div>
      </div>
    </Modal>
  );
}
