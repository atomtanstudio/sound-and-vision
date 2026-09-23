import { analyzeSong } from "./songAnalysis";
self.onmessage = (
  event: MessageEvent<{ pcm: Float32Array; sampleRate: number }>,
) => {
  try {
    const analysis = analyzeSong(
      event.data.pcm,
      event.data.sampleRate,
      (value) => self.postMessage({ progress: value }),
    );
    self.postMessage(
      { analysis },
      { transfer: [analysis.data.buffer as ArrayBuffer] },
    );
  } catch (error) {
    self.postMessage({
      error: error instanceof Error ? error.message : String(error),
    });
  }
};
