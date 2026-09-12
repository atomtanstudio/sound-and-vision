/** Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0 */
import { useEffect, useRef, type RefObject } from "react";
import { visualizerShaderUrl, type VisualizerAudioFrame } from "./library";
import { visualizerAt } from "./schedule";

export type VisualizerDraw = (
  time: number,
  audio: VisualizerAudioFrame,
) => void;

export type VisualizerCanvasProps = {
  audioRef: RefObject<HTMLAudioElement | null>;
  active: boolean;
  playing: boolean;
  time: number;
  preset: number;
  selection?: string;
  duration?: number;
  renderRef?: RefObject<VisualizerDraw | null>;
  onReady?: () => void;
  strength?: number;
  reduceMotion?: boolean;
  className?: string;
  onError?: (message: string) => void;
};

type AudioGraph = {
  context: AudioContext;
  analyser: AnalyserNode;
  source: MediaElementAudioSourceNode;
  spectrum: Uint8Array<ArrayBuffer>;
  waveform: Float32Array<ArrayBuffer>;
};
const graphKey = Symbol.for("soundvision.originalVisualizers.audioGraphs.v1");
function graphRegistry() {
  const scope = globalThis as unknown as Record<
    symbol,
    WeakMap<HTMLAudioElement, AudioGraph>
  >;
  return (scope[graphKey] ??= new WeakMap<HTMLAudioElement, AudioGraph>());
}
function sharedGraph(audio: HTMLAudioElement): AudioGraph {
  const registry = graphRegistry();
  const existing = registry.get(audio);
  if (existing) return existing;
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.18;
  analyser.minDecibels = -80;
  analyser.maxDecibels = -17;
  const source = context.createMediaElementSource(audio);
  source.connect(analyser);
  analyser.connect(context.destination);
  const graph = {
    context,
    analyser,
    source,
    spectrum: new Uint8Array(analyser.frequencyBinCount),
    waveform: new Float32Array(analyser.fftSize),
  };
  registry.set(audio, graph);
  // This listener and graph deliberately survive view changes/HMR. The app's
  // single audio element must never acquire a second MediaElement source.
  const resume = () => {
    void context.resume().catch(() => {});
  };
  audio.addEventListener("play", resume);
  if (!audio.paused) resume();
  return graph;
}

/** Shares the app player, while owning only this canvas's graphics resources. */
export function VisualizerCanvas(props: VisualizerCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const current = useRef(props);
  current.current = props;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", {
      antialias: false,
      alpha: false,
      preserveDrawingBuffer: !!props.renderRef,
    });
    if (!gl) {
      current.current.onError?.("This visualizer needs WebGL2.");
      return;
    }
    let stopped = false,
      frameRequest = 0,
      program: WebGLProgram | null = null;
    let vertex: WebGLShader | null = null,
      fragment: WebGLShader | null = null;
    let observedAudio: HTMLAudioElement | null = null,
      graph: AudioGraph | null = null;
    let previousBass = 0,
      onset = 0,
      lastWall = 0,
      track = "";
    const bands = new Float32Array(4);
    const reset = () => {
      bands.fill(0);
      previousBass = 0;
      onset = 0;
    };
    const events = [
      "loadstart",
      "emptied",
      "seeking",
      "pause",
      "ended",
    ] as const;
    const unobserve = () => {
      if (observedAudio)
        for (const event of events)
          observedAudio.removeEventListener(event, reset);
    };
    const observeAudio = (audio: HTMLAudioElement | null) => {
      if (audio === observedAudio) return;
      unobserve();
      reset();
      observedAudio = audio;
      graph = null;
      track = "";
      if (audio) {
        graph = sharedGraph(audio);
        for (const event of events) audio.addEventListener(event, reset);
      }
    };
    const fail = (error: unknown) => {
      if (!stopped)
        current.current.onError?.(
          error instanceof Error ? error.message : String(error),
        );
    };
    const compile = (type: number, code: string) => {
      const shader = gl.createShader(type);
      if (!shader) throw Error("Could not create the visualizer shader.");
      gl.shaderSource(shader, code);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const message =
          gl.getShaderInfoLog(shader) ||
          "Visualizer shader compilation failed.";
        gl.deleteShader(shader);
        throw Error(message);
      }
      return shader;
    };
    const abort = new AbortController();
    // Connect/resume synchronously before any shader fetch; never await a
    // suspended AudioContext before allowing the app's player to operate.
    try {
      observeAudio(
        current.current.active ? current.current.audioRef.current : null,
      );
    } catch (error) {
      fail(error);
    }
    void fetch(visualizerShaderUrl, { signal: abort.signal })
      .then((response) => {
        if (!response.ok)
          throw Error(`Visualizer source returned ${response.status}.`);
        return response.text();
      })
      .then((source) => {
        if (stopped) return;
        vertex = compile(
          gl.VERTEX_SHADER,
          "#version 300 es\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}",
        );
        fragment = compile(
          gl.FRAGMENT_SHADER,
          "#version 300 es\nprecision highp float;\nprecision highp int;\n" +
            source,
        );
        program = gl.createProgram();
        if (!program) throw Error("Could not create the visualizer program.");
        gl.attachShader(program, vertex);
        gl.attachShader(program, fragment);
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS))
          throw Error(
            gl.getProgramInfoLog(program) || "Visualizer link failed.",
          );
        gl.useProgram(program);
        const uniforms = Object.fromEntries(
          [
            "resolution",
            "time",
            "audio",
            "energy",
            "strength",
            "preset",
            "nextPreset",
            "blend",
          ].map((name) => [name, gl.getUniformLocation(program!, "u_" + name)]),
        );
        const draw = (
          wall: number,
          offline?: { time: number; audio: VisualizerAudioFrame },
        ) => {
          if (stopped) return;
          try {
            const state = current.current;
            observeAudio(state.active ? state.audioRef.current : null);
            const audio = observedAudio;
            const dt = Math.min(0.1, Math.max(0.001, (wall - lastWall) / 1000));
            lastWall = wall;
            const nextTrack = audio?.currentSrc || audio?.src || "";
            if (nextTrack !== track) {
              track = nextTrack;
              reset();
            }
            let energy = 0;
            if (offline) {
              const a = offline.audio;
              bands.set([a.bass, a.mid, a.treble, a.onset]);
              energy = a.energy;
            } else if (
              state.active &&
              state.playing &&
              audio &&
              !audio.paused &&
              !audio.ended &&
              graph
            ) {
              graph.analyser.getByteFrequencyData(graph.spectrum);
              graph.analyser.getFloatTimeDomainData(graph.waveform);
              const band = (low: number, high: number) => {
                const binHz =
                  graph!.context.sampleRate / graph!.analyser.fftSize;
                const start = Math.max(1, Math.round(low / binHz));
                const end = Math.min(
                  graph!.spectrum.length,
                  Math.round(high / binHz),
                );
                let sum = 0;
                for (let i = start; i < end; i++)
                  sum += graph!.spectrum[i] / 255;
                return Math.max(
                  0,
                  Math.min(1, (sum / Math.max(1, end - start) - 0.06) / 0.78),
                );
              };
              const bass = band(35, 190);
              onset = Math.max(
                Math.max(0, bass - previousBass) * 5,
                onset * Math.exp(-dt / 0.13),
              );
              previousBass = bass;
              bands.set([
                bass,
                band(190, 2400),
                band(2400, 10000),
                Math.min(1, onset),
              ]);
              for (const sample of graph.waveform) energy += sample * sample;
              energy = Math.min(
                1,
                Math.sqrt(energy / graph.waveform.length) * 3.5,
              );
            } else reset();
            const bounds = canvas.getBoundingClientRect();
            const dpr = Math.min(devicePixelRatio || 1, 1.5);
            const width = Math.max(
              1,
              Math.min(1920, Math.round(bounds.width * dpr)),
            );
            const height = Math.max(
              1,
              Math.round((width * bounds.height) / Math.max(1, bounds.width)),
            );
            if (canvas.width !== width || canvas.height !== height) {
              canvas.width = width;
              canvas.height = height;
              gl.viewport(0, 0, width, height);
            }
            const timestamp = offline
              ? offline.time
              : audio && Number.isFinite(audio.currentTime)
                ? audio.currentTime
                : state.time;
            const id = state.selection
              ? visualizerAt(timestamp, state.duration || 0, state.selection)
              : Math.max(0, Math.min(7, Math.trunc(state.preset)));
            canvas.dataset.visualizer = String(id);
            gl.uniform2f(uniforms.resolution, width, height);
            // Reduced motion freezes geometry and suppresses beat-driven changes.
            gl.uniform1f(
              uniforms.time,
              state.reduceMotion ? 0 : Math.max(0, timestamp),
            );
            gl.uniform4fv(
              uniforms.audio,
              state.reduceMotion ? new Float32Array(4) : bands,
            );
            gl.uniform1f(uniforms.energy, state.reduceMotion ? 0 : energy);
            gl.uniform1f(
              uniforms.strength,
              state.reduceMotion
                ? 0
                : Math.max(0, Math.min(2, state.strength ?? 1)),
            );
            gl.uniform1i(uniforms.preset, id);
            gl.uniform1i(uniforms.nextPreset, id);
            gl.uniform1f(uniforms.blend, 0);
            gl.drawArrays(gl.TRIANGLES, 0, 3);
            if (!state.renderRef) frameRequest = requestAnimationFrame(draw);
          } catch (error) {
            fail(error);
          }
        };
        if (current.current.renderRef) {
          current.current.renderRef.current = (time, audio) =>
            draw(0, { time, audio });
          current.current.onReady?.();
        } else frameRequest = requestAnimationFrame(draw);
      })
      .catch((error) => {
        if (!abort.signal.aborted) fail(error);
      });
    return () => {
      stopped = true;
      abort.abort();
      cancelAnimationFrame(frameRequest);
      if (current.current.renderRef) current.current.renderRef.current = null;
      unobserve();
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (program) gl.deleteProgram(program);
      if (vertex) gl.deleteShader(vertex);
      if (fragment) gl.deleteShader(fragment);
      // Keep the shared audio graph connected; disconnecting it would mute the
      // app's existing player after this view unmounts.
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={props.className}
      aria-hidden="true"
      style={{
        width: "100%",
        height: "100%",
        display: "block",
      }}
    />
  );
}
