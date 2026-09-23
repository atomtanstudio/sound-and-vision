/** Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0 */
import { useEffect, useRef, useState, type RefObject } from "react";
import {
  inkShaderUrl,
  visualizerShaderUrl,
  type VisualizerAudioFrame,
} from "./library";
import { presetNumber, visualizerAt } from "./schedule";
import { sampleSong } from "./songAnalysis";
import { useSongAnalysis } from "./useSongAnalysis";
import { sceneUniforms, type SongScene } from "./scene";

export type VisualizerDraw = (
  time: number,
  audio: VisualizerAudioFrame,
) => void;

export type VisualizerCanvasProps = {
  audioRef: RefObject<HTMLAudioElement | null>;
  /** Lossless version of the selected soundtrack, also used by the exporter. */
  analysisUrl?: string;
  scene?: SongScene;
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
  onAnalysis?: (status: {
    ready: boolean;
    progress: number;
    error?: string;
  }) => void;
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
  const scene = props.scene;
  const ink =
    !!scene || presetNumber(props.selection || String(props.preset)) === 8;
  const measured = useSongAnalysis(props.analysisUrl, ink && !props.renderRef);
  const measuredRef = useRef(measured);
  measuredRef.current = measured;
  const [systemReduced, setSystemReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const reducedRef = useRef(false);
  // Accessibility affects interactive previews, never an exported composition.
  reducedRef.current = props.renderRef
    ? false
    : (props.reduceMotion ?? systemReduced);
  useEffect(() => {
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystemReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (ink && !props.renderRef)
      current.current.onAnalysis?.({
        ready: !!measured.analysis,
        progress: measured.progress,
        error: measured.error,
      });
  }, [
    ink,
    measured.analysis,
    measured.progress,
    measured.error,
    props.renderRef,
  ]);

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
    let artworkTexture: WebGLTexture | null = null;
    let observedAudio: HTMLAudioElement | null = null,
      graph: AudioGraph | null = null;
    let previousBass = 0,
      onset = 0,
      lastWall = 0,
      track = "";
    const bands = new Float32Array(4),
      detail = new Float32Array(24),
      row = new Float32Array(32),
      zero = new Float32Array(4);
    let lastDraw = "",
      lastAnalysis = measuredRef.current.analysis;
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
      if (audio && !ink) {
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
    void fetch(
      scene
        ? "/visualizers/song-scene.frag"
        : ink
          ? inkShaderUrl
          : visualizerShaderUrl,
      {
        signal: abort.signal,
      },
    )
      .then((response) => {
        if (!response.ok)
          throw Error(`Visualizer source returned ${response.status}.`);
        return response.text();
      })
      .then(async (source) => {
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
        if (scene) {
          const values = sceneUniforms(scene);
          const response = await fetch(scene.artworkUrl, {
            signal: abort.signal,
          });
          if (!response.ok) throw Error("Could not load the song artwork.");
          const bitmap = await createImageBitmap(await response.blob());
          if (stopped) {
            bitmap.close();
            return;
          }
          artworkTexture = gl.createTexture();
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, artworkTexture);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.texImage2D(
            gl.TEXTURE_2D,
            0,
            gl.RGB,
            gl.RGB,
            gl.UNSIGNED_BYTE,
            bitmap,
          );
          bitmap.close();
          gl.uniform1i(gl.getUniformLocation(program, "u_artwork"), 0);
          gl.uniform1i(
            gl.getUniformLocation(program, "u_surfaceCount"),
            values.length,
          );
          gl.uniform1f(
            gl.getUniformLocation(program, "u_duration"),
            props.duration || 1,
          );
          values.forEach((surface, i) => {
            gl.uniformMatrix3fv(
              gl.getUniformLocation(program!, `u_homography[${i}]`),
              false,
              surface.transform,
            );
            gl.uniform4fv(
              gl.getUniformLocation(program!, `u_surfaceStyle[${i}]`),
              surface.style,
            );
            gl.uniform3fv(
              gl.getUniformLocation(program!, `u_color[${i}]`),
              surface.color,
            );
            gl.uniform3fv(
              gl.getUniformLocation(program!, `u_accent[${i}]`),
              surface.accent,
            );
          });
        }
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
            "tick",
            "breath",
            "age",
            "bands[0]",
            "motion",
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
            let energy = 0,
              tick = 0,
              breath = 0,
              age = 3;
            const timestamp = offline
              ? offline.time
              : state.active && audio && Number.isFinite(audio.currentTime)
                ? audio.currentTime
                : state.time;
            detail.fill(0);
            if (offline) {
              const a = offline.audio;
              bands.set([a.bass, a.mid, a.treble, a.onset]);
              energy = a.energy;
              tick = a.tick ?? 0;
              breath = a.breath ?? 0;
              age = a.age ?? 3;
              if (a.spectrum) detail.set(a.spectrum.slice(0, 24));
            } else if (ink) {
              const analysis = measuredRef.current.analysis;
              if (analysis) {
                sampleSong(analysis, timestamp, row);
                bands.set(row.subarray(0, 4));
                tick = row[4];
                energy = row[5];
                breath = row[6];
                age = row[7] * 3;
                detail.set(row.subarray(8));
              } else reset();
              canvas.dataset.analysis = analysis
                ? "ready"
                : measuredRef.current.error
                  ? "error"
                  : "loading";
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
            const dpr = state.renderRef
              ? 1
              : Math.min(devicePixelRatio || 1, 1.5);
            const width = Math.max(
              1,
              Math.min(
                state.renderRef ? 7680 : 1920,
                Math.round(bounds.width * dpr),
              ),
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
            const id = state.selection
              ? visualizerAt(timestamp, state.duration || 0, state.selection)
              : Math.max(0, Math.min(8, Math.trunc(state.preset)));
            const signature = `${width}/${height}/${reducedRef.current ? 0 : timestamp}/${id}/${state.strength ?? 1}/${reducedRef.current}/${state.active}/${state.playing}`;
            if (
              !offline &&
              signature === lastDraw &&
              lastAnalysis === measuredRef.current.analysis
            ) {
              frameRequest = requestAnimationFrame(draw);
              return;
            }
            lastDraw = signature;
            lastAnalysis = measuredRef.current.analysis;
            canvas.dataset.visualizer = scene ? "song" : String(id);
            gl.uniform2f(uniforms.resolution, width, height);
            // Reduced motion freezes geometry and suppresses beat-driven changes.
            gl.uniform1f(
              uniforms.time,
              reducedRef.current ? 0 : Math.max(0, timestamp),
            );
            gl.uniform4fv(uniforms.audio, reducedRef.current ? zero : bands);
            gl.uniform1f(uniforms.energy, reducedRef.current ? 0 : energy);
            gl.uniform1f(uniforms.tick, reducedRef.current ? 0 : tick);
            gl.uniform1f(uniforms.breath, reducedRef.current ? 0 : breath);
            gl.uniform1f(uniforms.age, reducedRef.current ? 3 : age);
            gl.uniform1f(uniforms.motion, 1);
            if (reducedRef.current) detail.fill(0);
            gl.uniform1fv(uniforms["bands[0]"], detail);
            gl.uniform1f(
              uniforms.strength,
              reducedRef.current
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
        } else {
          current.current.onReady?.();
          frameRequest = requestAnimationFrame(draw);
        }
      })
      .catch((error) => {
        if (!abort.signal.aborted) fail(error);
      });
    return () => {
      stopped = true;
      abort.abort();
      if (artworkTexture) gl.deleteTexture(artworkTexture);
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
  }, [ink, scene?.artworkUrl, scene?.artworkSha256]);

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
