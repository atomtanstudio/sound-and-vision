import {
  Heart,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  Video,
  Volume2,
  X,
} from "lucide-react";
import { musicApi } from "../../music-studio/api";
import { useStudio, playable, timeLabel } from "../context";
import { CoverArt } from "./CoverArt";
import { IconBtn, cn } from "../ui";

/* The floating console transport — a glass pill anchored bottom-center. */
export function PlayerDock() {
  const {
    audioRef,
    currentTrack,
    current,
    playing,
    progress,
    duration,
    volume,
    setVolume,
    toggle,
    seek,
    step,
    makeVideo,
    patchTrack,
  } = useStudio();
  if (!current || !currentTrack) return null;
  const canVideo = playable(currentTrack);
  return (
    <div className="dock-wrap">
      <div className="dock" role="region" aria-label="Player">
        <CoverArt track={currentTrack} playing={playing} ring />
        <div className="dock-meta">
          <strong>{currentTrack.title || "Untitled"}</strong>
          <span>{currentTrack.subtitle || currentTrack.project}</span>
        </div>
        <button
          className={cn("dock-fav", currentTrack.favorite && "on")}
          aria-label={currentTrack.favorite ? "Remove favorite" : "Favorite"}
          onClick={() => {
            const favorite = !currentTrack.favorite;
            patchTrack(currentTrack.id, { favorite });
            if (currentTrack.source)
              musicApi.patch(currentTrack.id, { favorite }).catch(() => {});
          }}
        >
          <Heart size={15} fill={currentTrack.favorite ? "currentColor" : "none"} />
        </button>
        <div className="dock-transport">
          <IconBtn label="Previous" onClick={() => step(-1)}>
            <SkipBack size={16} fill="currentColor" />
          </IconBtn>
          <button className="dock-play" aria-label={playing ? "Pause" : "Play"} onClick={toggle}>
            {playing ? <Pause size={17} fill="currentColor" /> : <Play size={17} fill="currentColor" />}
          </button>
          <IconBtn label="Next" onClick={() => step(1)}>
            <SkipForward size={16} fill="currentColor" />
          </IconBtn>
        </div>
        <div className="dock-scrub">
          <time>{timeLabel(progress)}</time>
          <input
            type="range"
            aria-label="Seek"
            min={0}
            max={Math.max(duration, 0.01)}
            step={0.1}
            value={Math.min(progress, duration)}
            onChange={(e) => seek(Number(e.target.value))}
          />
          <time>{timeLabel(duration)}</time>
        </div>
        {canVideo ? (
          <button className="btn btn-ghost btn-sm dock-video" onClick={() => makeVideo(currentTrack)}>
            <Video size={14} /> Make video
          </button>
        ) : null}
        <div className="dock-volume">
          <Volume2 size={14} aria-hidden="true" />
          <input
            type="range"
            aria-label="Volume"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
          />
        </div>
        <IconBtn
          label="Stop"
          onClick={() => {
            const audio = audioRef.current;
            if (!audio) return;
            audio.pause();
            audio.currentTime = 0;
          }}
        >
          <X size={15} />
        </IconBtn>
      </div>
    </div>
  );
}
