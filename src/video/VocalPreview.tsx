import { useEffect, useRef, useState, type RefObject } from "react";

/** The untouched song remains the master clock; the stem is an editing monitor only. */
export function VocalPreview({
  endpoint,
  masterRef,
  active,
  onWaveform,
}: {
  endpoint?: string;
  masterRef: RefObject<HTMLAudioElement | null>;
  active: boolean;
  onWaveform: (url?: string) => void;
}) {
  const [available, setAvailable] = useState(false),
    [loading, setLoading] = useState(!!endpoint);
  const [enabled, setEnabled] = useState(false),
    [ready, setReady] = useState(false),
    [error, setError] = useState("");
  const stemRef = useRef<HTMLAudioElement>(null);
  const url = endpoint ? `${endpoint}/audio` : undefined;
  useEffect(() => {
    const controller = new AbortController();
    setEnabled(false);
    setAvailable(false);
    setLoading(!!endpoint);
    if (!endpoint) return;
    void fetch(endpoint, {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw Error("Vocal preview unavailable");
        const data = await response.json();
        if (!controller.signal.aborted) setAvailable(!!data.available);
      })
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [endpoint]);
  useEffect(() => {
    onWaveform(enabled && ready ? url : undefined);
  }, [enabled, ready, url, onWaveform]);
  useEffect(() => {
    const master = masterRef.current,
      stem = stemRef.current;
    if (!enabled || !ready || !active || !master || !stem) return;
    const wasMuted = master.muted;
    let disposed = false,
      starting = false,
      frame = 0;
    master.muted = true;
    const sync = () => {
      stem.volume = master.volume;
      stem.playbackRate = master.playbackRate;
      if (Math.abs(stem.currentTime - master.currentTime) > 0.06)
        stem.currentTime = Math.min(
          master.currentTime,
          Number.isFinite(stem.duration) ? stem.duration : master.currentTime,
        );
      if (master.paused || master.seeking) stem.pause();
      else if (stem.paused && !starting) {
        starting = true;
        void stem
          .play()
          .then(() => {
            if (disposed) stem.pause();
          })
          .catch(() => {
            if (!disposed) {
              setEnabled(false);
              setError(
                "Vocal preview could not play. Switched back to the original mix.",
              );
            }
          })
          .finally(() => {
            starting = false;
          });
      }
    };
    const tick = () => {
      sync();
      frame = requestAnimationFrame(tick);
    };
    const events = [
      "play",
      "pause",
      "seeking",
      "seeked",
      "volumechange",
      "ratechange",
    ];
    events.forEach((event) => master.addEventListener(event, sync));
    tick();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      events.forEach((event) => master.removeEventListener(event, sync));
      stem.pause();
      master.muted = wasMuted;
    };
  }, [enabled, ready, active, masterRef]);
  return (
    <div className="lyric-vocal-monitor">
      <label>
        Listen to
        <select
          aria-label="Editing audio"
          value={enabled ? "vocals" : "mix"}
          onChange={(e) => {
            setEnabled(e.target.value === "vocals");
            setReady(false);
            setError("");
          }}
        >
          <option value="mix">Original mix</option>
          <option value="vocals" disabled={!available}>
            Vocals only
          </option>
        </select>
      </label>
      <span>
        {error ||
          (loading
            ? "Checking for a vocal stem…"
            : enabled
              ? ready
                ? "Vocal stem and waveform · editing only. Exports use the original mix."
                : "Loading vocal preview…"
              : available
                ? "A separated vocal stem is available for timing review."
                : "Vocal preview is available after this song has been aligned or transcribed locally.")}
      </span>
      {enabled && url && (
        <audio
          data-vocal-monitor
          ref={stemRef}
          src={url}
          preload="auto"
          onLoadedData={() => setReady(true)}
          onError={() => {
            setEnabled(false);
            setError(
              "Could not load the vocal stem. Listening to the original mix.",
            );
          }}
        />
      )}
    </div>
  );
}
