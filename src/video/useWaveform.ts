import { useEffect, useState } from "react";
import { waveformPeaks } from "./lyricEditing";

type Waveform = { peaks: Float32Array; duration: number };
// Retain only compact peaks, never decoded PCM or AudioContexts.
const cache = new Map<string, Waveform>();

export function useWaveform(url: string) {
  const [data, setData] = useState<Waveform | null>(
    () => cache.get(url) || null,
  );
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let context: AudioContext | undefined;
    setData(cache.get(url) || null);
    setError("");
    if (cache.has(url)) return;
    void (async () => {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error("Audio could not be loaded");
        const bytes = await response.arrayBuffer();
        if (controller.signal.aborted) return;
        // Low sample rate limits memory while retaining useful vocal/beat detail.
        context = new AudioContext({ sampleRate: 12000 });
        const audio = await context.decodeAudioData(bytes);
        if (controller.signal.aborted) return;
        const channels = Array.from(
          { length: audio.numberOfChannels },
          (_, i) => audio.getChannelData(i),
        );
        const result = {
          peaks: waveformPeaks(channels, Math.ceil(audio.duration * 100)),
          duration: audio.duration,
        };
        if (cache.size >= 4) cache.delete(cache.keys().next().value!);
        cache.set(url, result);
        setData(result);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Waveform unavailable. Playback and timing controls still work. Close and reopen to retry.",
          );
      } finally {
        if (context && context.state !== "closed")
          void context.close().catch(() => {});
      }
    })();
    return () => {
      controller.abort();
      if (context && context.state !== "closed")
        void context.close().catch(() => {});
    };
  }, [url]);
  return { data, error };
}
