import { useEffect, useState } from "react";
import { SONG_SAMPLE_RATE, type SongAnalysis } from "./songAnalysis";
type State = {
  source: string;
  analysis?: SongAnalysis;
  progress: number;
  error?: string;
};
const cache = new Map<string, SongAnalysis>();
export function useSongAnalysis(source: string | undefined, enabled: boolean) {
  const [state, setState] = useState<State>({ source: "", progress: 0 });
  useEffect(() => {
    if (!enabled || !source) return;
    const found = cache.get(source);
    if (found) {
      setState({ source, analysis: found, progress: 1 });
      return;
    }
    const controller = new AbortController();
    let worker: Worker | undefined,
      stopped = false;
    setState({ source, progress: 0 });
    void (async () => {
      try {
        const response = await fetch(source, { signal: controller.signal });
        if (!response.ok)
          throw Error(
            `Could not load the song for analysis (${response.status}).`,
          );
        const bytes = await response.arrayBuffer();
        if (stopped) return;
        const context = new OfflineAudioContext(2, 1, SONG_SAMPLE_RATE);
        const audio = await context.decodeAudioData(bytes);
        if (stopped) return;
        if (audio.duration > 3600)
          throw Error("Choose a song shorter than one hour.");
        const left = audio.getChannelData(0),
          right = audio.getChannelData(Math.min(1, audio.numberOfChannels - 1));
        const mono = new Float32Array(audio.length);
        for (let i = 0; i < mono.length; i++)
          mono[i] = (left[i] + right[i]) * 0.5;
        worker = new Worker(
          new URL("./songAnalysis.worker.ts", import.meta.url),
          { type: "module" },
        );
        worker.onmessage = (event) => {
          if (stopped) return;
          if (event.data.error) {
            setState({ source, progress: 0, error: event.data.error });
            worker?.terminate();
          } else if (event.data.analysis) {
            const analysis: SongAnalysis = event.data.analysis;
            cache.set(source, analysis);
            if (cache.size > 3) cache.delete(cache.keys().next().value!);
            setState({ source, analysis, progress: 1 });
            worker?.terminate();
          } else setState({ source, progress: event.data.progress });
        };
        worker.onerror = () => {
          if (!stopped)
            setState({
              source,
              progress: 0,
              error:
                "Song analysis could not finish. Reselect the style to retry.",
            });
          worker?.terminate();
        };
        worker.postMessage({ pcm: mono, sampleRate: SONG_SAMPLE_RATE }, [
          mono.buffer,
        ]);
      } catch (error) {
        if (!stopped)
          setState({
            source,
            progress: 0,
            error: error instanceof Error ? error.message : String(error),
          });
      }
    })();
    return () => {
      stopped = true;
      controller.abort();
      worker?.terminate();
    };
  }, [source, enabled]);
  return enabled && state.source === source
    ? state
    : ({ source: source || "", progress: 0 } as State);
}
