import { useRef, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import "@fontsource-variable/manrope";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/newsreader/wght-italic.css";
import "../video.css";
import { VisualizerCanvas, type VisualizerDraw } from "./VisualizerCanvas";
import { LyricOverlay } from "./LyricOverlay";
import type { VisualizerAnalysis } from "./library";
import type { VideoDraft, LyricCue } from "../timeline";

declare global {
  interface Window {
    visualizerRenderReady?: boolean;
    visualizerRenderError?: string;
    renderVisualizerFrame?: (frame: number) => void;
    visualizerRenderInput?: { config: Config; analysis: VisualizerAnalysis };
  }
}
type Config = {
  draft: VideoDraft;
  cues: LyricCue[];
  title: string;
  duration: number;
  width: number;
  height: number;
};
const style = document.createElement("style");
style.textContent =
  "*{box-sizing:border-box}html,body,#root{margin:0;width:100%;height:100%;overflow:hidden;background:#000}.export-stage{width:100vw!important;height:100vh!important;border:0!important;border-radius:0!important;max-width:none!important}";
document.head.append(style);
async function start() {
  if (!window.visualizerRenderInput)
    throw Error("This composition is opened by the video renderer.");
  const { config, analysis } = window.visualizerRenderInput;
  function Composition() {
    const [frame, setFrame] = useState(0);
    const draw = useRef<VisualizerDraw | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const time = frame / analysis.fps;
    const { draft } = config;
    return (
      <div
        className={`video-stage export-stage font-${draft.font} position-${draft.placement}`}
        style={
          {
            "--video-text": draft.textColor,
            "--video-highlight": draft.highlightColor,
          } as CSSProperties
        }
      >
        <VisualizerCanvas
          audioRef={audioRef}
          active={false}
          playing={false}
          time={time}
          preset={0}
          selection={draft.visualizer}
          duration={config.duration}
          strength={draft.visualizerStrength}
          renderRef={draw}
          onError={(message) => {
            window.visualizerRenderError = message;
          }}
          onReady={() => {
            window.renderVisualizerFrame = (frame) => {
              if (frame < 0 || frame >= analysis.frames.length)
                throw Error("Frame outside audio analysis");
              flushSync(() => setFrame(frame));
              draw.current!(frame / analysis.fps, analysis.frames[frame]);
            };
            void document.fonts.ready.then(() => {
              window.visualizerRenderReady = true;
            });
          }}
        />
        <div className="video-shade" style={{ opacity: draft.shade / 100 }} />
        {draft.showLyrics && (
          <LyricOverlay
            draft={draft}
            cues={config.cues}
            time={time}
            title={config.title}
            aligned={config.cues.length > 0}
          />
        )}
      </div>
    );
  }
  createRoot(document.getElementById("root")!).render(<Composition />);
}
void start().catch((error) => {
  window.visualizerRenderError = String(error.message || error);
});
