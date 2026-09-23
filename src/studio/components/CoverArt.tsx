import type { CSSProperties } from "react";
import { AudioLines } from "lucide-react";
import type { Track } from "../../music-studio/model";
import { Equalizer, cn } from "../ui";

/* Cover with a procedural aurora placeholder when art is missing. */
export function CoverArt({
  track,
  className,
  playing,
  ring,
}: {
  track: Track;
  className?: string;
  playing?: boolean;
  ring?: boolean;
}) {
  const hue =
    (track.id
      .split("")
      .reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 0) +
      360) %
    360;
  const live =
    !!track.status && !["succeeded", "failed", "cancelled"].includes(track.status);
  return (
    <div
      className={cn("cover-art", ring && "cover-ring", className)}
      style={
        track.cover
          ? undefined
          : ({
              "--cover-a": `hsl(${hue} 70% 58%)`,
              "--cover-b": `hsl(${(hue + 72) % 360} 78% 46%)`,
            } as CSSProperties)
      }
    >
      {track.cover ? (
        <img src={track.cover} alt="" loading="lazy" />
      ) : live ? (
        <span className={cn("cover-live", track.status === "running" && "running")}>
          <Equalizer playing={track.status === "running"} />
        </span>
      ) : (
        <AudioLines size={20} aria-hidden="true" />
      )}
    </div>
  );
}
