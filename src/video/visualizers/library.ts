/** Original Sound/Vision visualizers. SPDX-License-Identifier: Apache-2.0 */
export type VisualizerPresetId = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type VisualizerAudioFrame = {
  /** Exact output-video timestamp, seconds. */
  time: number;
  /** Normalized measured audio bands and transient/energy envelopes. */
  bass: number;
  mid: number;
  treble: number;
  onset: number;
  energy: number;
};
export type VisualizerAnalysis = {
  version: 1;
  fps: number;
  duration: number;
  frames: VisualizerAudioFrame[];
  /** Measured spectral-flux peaks; no automatic BPM-grid promise. */
  onsets: number[];
  beats: number[];
};
export const originalVisualizerPresets = [
  { id: 0, name: "Vault", description: "Sculptural perspective tunnel" },
  {
    id: 1,
    name: "Mercury",
    description: "Liquid metal and studio reflections",
  },
  {
    id: 2,
    name: "Satellites",
    description: "Particles moving through orbital paths",
  },
  { id: 3, name: "Strata", description: "Living topographic contours" },
  { id: 4, name: "Index", description: "Precision rings and radial geometry" },
  { id: 5, name: "Silk", description: "Luminous flowing ribbon surfaces" },
  { id: 6, name: "Facet", description: "Refractive crystal cluster" },
  { id: 7, name: "Afterimage", description: "Warm analog wave interference" },
] as const;
export const visualizerShaderUrl = "/visualizers/collection.frag";
export const visualizerPreviewUrl = "/visualizers/index.html";
