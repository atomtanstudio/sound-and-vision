import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { readLocal, writeLocal } from "../music-studio/model";
import { busyJob, type Alignment, type useVideoProduction } from "./production";

type Props = {
  lyrics: string;
  language: string;
  aspect: string;
  optional: boolean;
  production: ReturnType<typeof useVideoProduction>;
  alignment?: Alignment;
  onLyrics: (lyrics: string) => void;
  onLanguage: (language: string) => void;
  onAlign: () => Promise<void>;
};

export function LyricPreparation({
  lyrics,
  language,
  aspect,
  optional,
  production,
  alignment,
  onLyrics,
  onLanguage,
  onAlign,
}: Props) {
  const jobs = [...production.jobs].reverse();
  const transcription = jobs.find(
    (j) => j.kind === "lyric-transcription" && j.input.language === language,
  );
  const result = jobs.find(
    (j) =>
      j.kind === "lyric-transcription" &&
      j.input.language === language &&
      j.state === "succeeded",
  );
  const timingJob = jobs.find(
    (j) =>
      j.kind === "lyric-alignment" &&
      j.input.language === language &&
      j.input.lyrics.trim() === lyrics.trim(),
  );
  const active = jobs.find(
    (j) =>
      ["lyric-transcription", "lyric-alignment"].includes(j.kind) && busyJob(j),
  );
  const blocked = !!active || production.submitting;
  const reviewKey = `sv-transcript-review-v1:${result?.id}`;
  const [reviewLyrics, setReviewLyrics] = useState("");
  const [editing, setEditing] = useState(!!lyrics.trim());
  useEffect(() => {
    setReviewLyrics(
      result ? readLocal<string>(reviewKey, result.result?.lyrics || "") : "",
    );
  }, [result?.id, result?.result?.lyrics, reviewKey]);
  const applied = !!reviewLyrics.trim() && reviewLyrics === lyrics;
  const needsReview = !!result?.result?.lyrics?.trim() && !applied;
  const failed =
    transcription?.state === "failed"
      ? transcription
      : timingJob?.state === "failed"
        ? timingJob
        : undefined;
  const status = production.loading
    ? "Connecting…"
    : active
      ? active.kind === "lyric-transcription"
        ? "Transcribing…"
        : "Aligning…"
      : failed
        ? "Needs attention"
        : needsReview
          ? "Review your draft"
          : alignment
            ? "Timing ready"
            : lyrics.trim()
              ? "Ready to align"
              : optional
                ? "Optional"
                : "Add your lyrics";

  async function transcribe() {
    await production.submit([
      {
        kind: "transcription",
        slot: 0,
        aspect,
        seconds: 8,
        lyrics: "",
        language,
        prompt: "",
      },
    ]);
  }

  return (
    <section
      className="lyric-preparation"
      aria-labelledby="lyric-preparation-title"
    >
      <div className="video-section-heading">
        <div>
          <h2 id="lyric-preparation-title">Lyrics</h2>
          <p>
            {optional
              ? "Add lyrics to your visualizer, or continue with visuals only."
              : "Transcribe your song or add your own lyrics. Review the words, then align them to the vocal."}
          </p>
        </div>
        <span className="lyric-stage" role="status">
          {alignment && !active && <Check size={14} />}
          {status}
        </span>
      </div>
      <div className="lyric-actions">
        <label className="lyric-language">
          Lyric language
          <select
            value={language}
            disabled={blocked}
            onChange={(e) => onLanguage(e.target.value)}
          >
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="it">Italian</option>
            <option value="pt">Portuguese</option>
          </select>
        </label>
        <button
          className={lyrics.trim() ? "secondary-button" : "primary-button"}
          disabled={!production.installed || blocked}
          onClick={() => void transcribe()}
        >
          {active?.kind === "lyric-transcription"
            ? "Transcribing song…"
            : "Transcribe lyrics from song"}
        </button>
        <button
          className="quiet-button"
          aria-expanded={editing}
          aria-controls="video-lyrics-editor"
          onClick={() => setEditing(!editing)}
        >
          {editing
            ? "Hide lyric editor"
            : lyrics.trim()
              ? "Edit lyrics"
              : "Paste or type lyrics"}
        </button>
        <button
          className="secondary-button lyric-align-action"
          disabled={!lyrics.trim() || !production.installed || blocked}
          onClick={() => void onAlign()}
        >
          {active?.kind === "lyric-alignment"
            ? "Aligning lyrics…"
            : alignment
              ? "Align lyrics again"
              : "Align lyrics"}
        </button>
      </div>
      {!production.loading && !production.installed && (
        <p className="video-field-note">
          Automatic transcription and timing need the local lyric-alignment
          runtime. You can still paste and edit lyrics here.
        </p>
      )}
      {!active && !result && !failed && !lyrics.trim() && (
        <p className="video-field-note">
          Transcription starts when you click the button. It runs locally and
          can take a few minutes.
        </p>
      )}
      {production.error && (
        <p className="form-error" role="alert">
          {production.error}
        </p>
      )}
      {active && (
        <div className="lyric-job-state" role="status">
          <div>
            <strong>
              {active.result?.phase ||
                (active.state === "queued"
                  ? "Queued for processing"
                  : "Processing your song")}
            </strong>
            <p>
              Your result will appear here. You can leave this page and return
              while it works.
            </p>
          </div>
          <button
            className="quiet-button"
            disabled={production.submitting}
            onClick={() => void production.action(active, "cancel")}
          >
            Cancel
          </button>
        </div>
      )}
      {failed && !active && (
        <div className="lyric-job-state lyric-job-error" role="alert">
          <div>
            <strong>
              {failed.kind === "lyric-transcription"
                ? "Transcription failed"
                : "Lyric alignment failed"}
            </strong>
            <p>
              {failed.error || "Processing stopped before a result was saved."}
            </p>
            <p>Your song and saved lyrics are unchanged.</p>
          </div>
          <button
            className="secondary-button"
            disabled={blocked}
            onClick={() => void production.action(failed, "retry")}
          >
            Retry{" "}
            {failed.kind === "lyric-transcription"
              ? "transcription"
              : "alignment"}
          </button>
        </div>
      )}
      {transcription?.state === "cancelled" && !active && (
        <p role="status" className="video-field-note">
          Transcription cancelled. You can start it again or add lyrics
          yourself.
        </p>
      )}
      {result && !result.result?.lyrics?.trim() && (
        <div className="lyric-job-state" role="status">
          <div>
            <strong>No lyrics were recognized</strong>
            <p>
              Check the selected language, try transcription again, or paste the
              lyrics yourself. Instrumental tracks can use a visualizer without
              lyrics.
            </p>
          </div>
        </div>
      )}
      {needsReview && (
        <div className="lyric-review">
          <div>
            <h3>Review transcribed lyrics</h3>
            <p>
              Listen to the song and correct any misheard words or lyrics
              invented during instrumental sections.
            </p>
            <p>
              Your current video lyrics stay unchanged until you use this draft.
            </p>
          </div>
          <div>
            <label htmlFor="transcribed-lyrics">Transcription draft</label>
            <textarea
              id="transcribed-lyrics"
              aria-label="Review transcribed lyrics"
              rows={8}
              value={reviewLyrics}
              onChange={(e) => {
                setReviewLyrics(e.target.value);
                writeLocal(reviewKey, e.target.value);
              }}
            />
            <button
              className="primary-button"
              disabled={!reviewLyrics.trim() || blocked}
              onClick={() => {
                onLyrics(reviewLyrics);
                setEditing(true);
              }}
            >
              Use reviewed lyrics
              {lyrics.trim() ? " (replace current lyrics)" : ""}
            </button>
          </div>
        </div>
      )}
      {applied && !active && !needsReview && (
        <p className="video-field-note" role="status">
          Reviewed lyrics are in your video.{" "}
          {alignment
            ? "Timing is ready to review below."
            : "Next, align the lyrics to the vocal."}
        </p>
      )}
      {editing && (
        <div className="lyric-editor" id="video-lyrics-editor">
          <label htmlFor="video-lyrics-text">Video lyrics</label>
          <textarea
            id="video-lyrics-text"
            aria-label="Video lyrics"
            rows={6}
            value={lyrics}
            onChange={(e) => onLyrics(e.target.value)}
            placeholder="Paste or type the words you want to show. Section labels stay out of the video."
          />
          <p className="video-field-note">
            Editing lyrics or changing language requires a new alignment before
            export.
          </p>
        </div>
      )}
    </section>
  );
}
