import { useEffect, useState } from "react";
import { request } from "../music-studio/api";
import "./film-credits.css";

export type FilmCredits = {
  enabled: boolean;
  artist: string;
  songTitle: string;
  recordLabel: string;
};
export const defaultCredits = (title: string, artist = ""): FilmCredits => ({
  enabled: true,
  artist,
  songTitle: title,
  recordLabel: "",
});

export function FilmCreditsEditor({
  value,
  onChange,
  background,
}: {
  value: FilmCredits;
  onChange: (value: FilmCredits) => void;
  background?: string;
}) {
  const [preview, setPreview] = useState<{
    image: string;
    font: { family: string; source: string };
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const timeout = window.setTimeout(() => {
      request<{ image: string; font: { family: string; source: string } }>(
        "/films/credits/preview",
        value,
      )
        .then((result) => {
          if (alive) {
            setPreview(result);
            setError("");
          }
        })
        .catch(() => {
          if (alive) setError("Credit preview is unavailable.");
        });
    }, 350);
    return () => {
      alive = false;
      clearTimeout(timeout);
    };
  }, [value]);
  return (
    <div className="film-credits-editor">
      <label className="film-credits-toggle">
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={(e) => onChange({ ...value, enabled: e.target.checked })}
        />
        Show song credits at the beginning and end
      </label>
      <div className="film-credits-fields">
        {(
          [
            ["artist", "Artist"],
            ["songTitle", "Song title"],
            ["recordLabel", "Record label"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            {label} <span className="optional">optional</span>
            <input
              aria-label={`Credit ${label.toLowerCase()}`}
              value={value[key]}
              maxLength={160}
              onChange={(e) => onChange({ ...value, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>
      <div
        className="film-credits-preview"
        aria-label="Song credit preview"
        style={
          background ? { backgroundImage: `url("${background}")` } : undefined
        }
      >
        {preview && (
          <img src={preview.image} alt="Preview of the song credit text" />
        )}
        {!value.enabled && <span>Credits off</span>}
        {value.enabled &&
          !value.artist.trim() &&
          !value.songTitle.trim() &&
          !value.recordLabel.trim() && <span>Add a credit to preview it</span>}
      </div>
      <p className="film-help">
        Blank fields are omitted. Credits appear for about seven seconds at each
        end.
      </p>
      {preview && (
        <small className="film-help">
          {preview.font.source === "open-source-fallback"
            ? "League Spartan · open-source approximation of the classic Kabel look."
            : `${preview.font.family} · configured font.`}
        </small>
      )}
      {error && (
        <p role="status" className="film-help">
          {error}
        </p>
      )}
    </div>
  );
}
