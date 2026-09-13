import { useEffect, useRef, useState, type ReactNode } from "react";
import { Download, Film, WandSparkles } from "lucide-react";
import { readLocal, writeLocal, type Track } from "../music-studio/model";
import { request } from "../music-studio/api";
import { timeLabel, lyricTimingReview, type LyricRenderCue } from "./timeline";

type Config = {
  theme: string;
  coverage: "full" | "repeat";
  clipCount: number;
  clipSeconds: number;
  join: "cut" | "dissolve" | "continue";
  showLyrics: boolean;
};
type Plan = Config & {
  clipCount: number;
  fullClipCount: number;
  duration: number;
  aspect: string;
  scenes: { name: string; prompt: string }[];
};
type MovieJob = {
  id: string;
  kind: string;
  state: string;
  error: string | null;
  input: Record<string, unknown>;
  result:
    | (Partial<Plan> & {
        theme?: string;
        phase?: string;
        videoUrl?: string;
        downloadUrl?: string;
        omittedLyricWords?: number;
      })
    | null;
};
const active = (job: MovieJob) =>
  ["queued", "running", "waiting-for-resource"].includes(job.state);

export function MusicVideoCreator({
  track,
  lyrics,
  language,
  aspect,
  cues,
  lyricControls,
  onAspect,
  timingEditor,
}: {
  track: Track;
  lyrics: string;
  language: string;
  aspect: "16:9" | "9:16";
  cues: LyricRenderCue[];
  lyricControls: ReactNode;
  onAspect: (aspect: "16:9" | "9:16") => void;
  timingEditor: ReactNode;
}) {
  const key = `sv-music-video-v1:${track.id}`;
  const [config, setConfig] = useState<Config>(() => ({
    theme: "",
    coverage: "full",
    clipCount: 4,
    clipSeconds: 15,
    join: "dissolve",
    showLyrics: !!lyrics.trim(),
    ...readLocal<Partial<Config>>(key, {}),
  }));
  const [jobs, setJobs] = useState<MovieJob[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [sending, setSending] = useState(false);
  const [omitUnusableWords, setOmitUnusableWords] = useState(false);
  const [notice, setNotice] = useState("");
  const suggested = useRef(!!config.theme);
  const themeEdited = useRef(!!config.theme);
  const appliedSuggestion = useRef("");
  const pendingId = useRef<{ signature: string; id: string } | null>(null);
  const latest = (kind: string) =>
    [...jobs].reverse().find((j) => j.kind === kind);
  const themeJob = latest("song-video-theme");
  const planJob = latest("song-video-plan");
  const renderJob = latest("song-video-render");
  const busy = jobs.some(active);
  const rendering = jobs.some(
    (j) => j.kind === "song-video-render" && active(j),
  );
  const duration = track.duration || 0;
  const overlap = config.join === "dissolve" ? 0.5 : 0;
  const fullCount = Math.max(
    1,
    Math.ceil((duration - overlap) / (config.clipSeconds - overlap)),
  );
  const plannedCount =
    config.coverage === "full"
      ? fullCount
      : Math.min(config.clipCount, fullCount);
  const timing = lyricTimingReview(cues, duration);
  const hasTimingGaps =
    config.showLyrics && cues.length > 0 && timing.omitted > 0;
  const timingBlocked = hasTimingGaps && (!omitUnusableWords || !timing.usable);
  const inputs = { ...config, lyrics, language, aspect };
  const matches =
    planJob?.state === "succeeded" &&
    Object.entries(inputs).every(
      ([key, value]) => key === "lyrics" || planJob.input[key] === value,
    );
  const plan = matches ? (planJob.result as Plan) : undefined;

  useEffect(() => {
    setOmitUnusableWords(false);
  }, [lyrics, language, planJob?.id]);

  function change(patch: Partial<Config>) {
    setConfig((old) => {
      const value = { ...old, ...patch };
      writeLocal(key, value);
      return value;
    });
  }
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await request<{ jobs: MovieJob[] }>(
          `/takes/${track.id}/music-video`,
        );
        if (!stopped) {
          setJobs(data.jobs);
          setLoaded(true);
          setConnectionError("");
        }
      } catch (e) {
        if (!stopped) setConnectionError((e as Error).message);
      }
      if (!stopped) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [track.id]);

  async function submit(
    operation: "theme" | "plan" | "render",
    body: Record<string, unknown>,
  ) {
    setSending(true);
    setError("");
    setNotice("");
    // Preserve the request ID across an uncertain network response.
    const signature = JSON.stringify({ operation, body });
    if (pendingId.current?.signature !== signature)
      pendingId.current = { signature, id: crypto.randomUUID() };
    try {
      const job = await request<MovieJob>(
        `/takes/${track.id}/music-video/${operation}`,
        { ...body, requestId: pendingId.current.id },
      );
      setJobs((old) => [
        ...old.filter((j) => j.id !== job.id),
        { ...job, input: { ...body, takeId: track.id } },
      ]);
      pendingId.current = null;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  useEffect(() => {
    if (loaded && !suggested.current) {
      suggested.current = true;
      if (!themeJob && !themeEdited.current) void submit("theme", { lyrics });
    }
  }, [loaded]);
  useEffect(() => {
    if (
      themeJob?.state === "succeeded" &&
      themeJob.result?.theme &&
      appliedSuggestion.current !== themeJob.id
    ) {
      appliedSuggestion.current = themeJob.id;
      if (!themeEdited.current) change({ theme: themeJob.result.theme });
    }
  }, [themeJob?.id, themeJob?.state, themeJob?.result?.theme]);
  async function stop() {
    if (!renderJob) return;
    try {
      const result = await request<{ message: string }>(
        `/music-video/jobs/${renderJob.id}/stop`,
        {},
      );
      setNotice(result.message);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const statusJob = [...jobs].reverse().find(active);
  const problem = [renderJob, planJob, themeJob]
    .filter((j): j is MovieJob => !!j)
    .find(
      (j) =>
        j.state === "failed" &&
        (j.kind !== "song-video-theme" || !config.theme),
    );
  const canResume =
    !!plan &&
    renderJob &&
    renderJob.input.planId === planJob?.id &&
    ["failed", "cancelled"].includes(renderJob.state);

  return (
    <div className="music-video-creator">
      <section
        className="music-video-brief"
        aria-labelledby="music-video-theme-title"
      >
        <div className="video-section-heading">
          <div>
            <h2 id="music-video-theme-title">
              What should your video feel like?
            </h2>
            <p>
              Build a full-song film from thematic scenes. The original
              recording supplies the soundtrack.
            </p>
          </div>
          <button
            className="quiet-button"
            disabled={busy || sending}
            onClick={() => {
              themeEdited.current = false;
              void submit("theme", { lyrics });
            }}
          >
            <WandSparkles size={15} />
            Suggest a theme
          </button>
        </div>
        <label htmlFor="music-video-theme" className="sr-only">
          Music video theme
        </label>
        <textarea
          id="music-video-theme"
          rows={4}
          value={config.theme}
          onChange={(e) => {
            themeEdited.current = true;
            change({ theme: e.target.value });
          }}
          placeholder="Describe a setting, mood, color palette or visual story…"
        />
        <p className="video-field-note">
          Suggestions use the song title, style and supplied lyrics. You can
          change the direction freely.
        </p>
        <fieldset className="music-video-coverage">
          <legend>How much new footage?</legend>
          <label className={config.coverage === "full" ? "chosen" : ""}>
            <input
              type="radio"
              name="movie-coverage"
              checked={config.coverage === "full"}
              onChange={() => change({ coverage: "full" })}
            />
            <span>
              <strong>New scenes for the whole song</strong>
              <small>
                About {fullCount} clips for {timeLabel(duration)}
              </small>
            </span>
          </label>
          <label className={config.coverage === "repeat" ? "chosen" : ""}>
            <input
              type="radio"
              name="movie-coverage"
              checked={config.coverage === "repeat"}
              onChange={() => change({ coverage: "repeat" })}
            />
            <span>
              <strong>A smaller set that repeats</strong>
              <small>
                Generate fewer clips and cycle them through the song
              </small>
            </span>
          </label>
        </fieldset>
        {config.coverage === "repeat" && (
          <label className="music-video-count">
            Unique clips
            <input
              aria-label="Unique music video clips"
              type="number"
              min={1}
              max={fullCount}
              value={config.clipCount}
              onChange={(e) =>
                change({
                  clipCount: Math.max(
                    1,
                    Math.min(fullCount, Number(e.target.value) || 1),
                  ),
                })
              }
            />
          </label>
        )}
        <label className="video-checkbox">
          <input
            type="checkbox"
            checked={config.showLyrics}
            onChange={(e) => change({ showLyrics: e.target.checked })}
          />
          On-screen lyrics
        </label>
        <p className="video-field-note">
          {config.showLyrics
            ? "Review the words below. Create video will align them automatically if timing is not ready."
            : "Create a visual film without lyric text."}
        </p>
        <details className="music-video-advanced">
          <summary>
            Advanced controls{" "}
            <span>Clip length, transitions and frame shape</span>
          </summary>
          <div className="music-video-options">
            <label>
              Clip length
              <select
                value={config.clipSeconds}
                onChange={(e) =>
                  change({ clipSeconds: Number(e.target.value) })
                }
              >
                <option value={15}>15 seconds</option>
                <option value={10}>10 seconds</option>
                <option value={5}>5 seconds</option>
              </select>
            </label>
            <label>
              Join clips
              <select
                aria-label="Join music video clips"
                value={config.join}
                onChange={(e) =>
                  change({ join: e.target.value as Config["join"] })
                }
              >
                <option value="dissolve">Soft blends</option>
                <option value="cut">Scene cuts</option>
                <option value="continue">Continue scenes in pairs</option>
              </select>
            </label>
            <label>
              Frame shape
              <select
                aria-label="Music video frame shape"
                value={aspect}
                onChange={(e) => onAspect(e.target.value as "16:9" | "9:16")}
              >
                <option value="16:9">Landscape · 16:9</option>
                <option value="9:16">Portrait · 9:16</option>
              </select>
            </label>
          </div>
          <p className="video-field-note">
            {config.join === "continue"
              ? "Every second clip starts from the previous clip’s final frame, creating longer scenes. Review the join: matching frames can still have a change in motion."
              : config.join === "dissolve"
                ? "Half-second overlaps are included in the clip count so the video covers the full song."
                : "Each scene cuts directly to the next."}{" "}
            Rendered at 1080p. No audio is sent to drive faces.
          </p>
        </details>
      </section>
      {config.showLyrics && lyricControls}
      {config.showLyrics && timingEditor}
      {hasTimingGaps && (
        <section
          className="music-video-timing-review"
          aria-label="Lyric timing review"
        >
          <h3>Review lyric timing before rendering</h3>
          <p>
            {timing.missing} words have no timestamps. {timing.conflicting}{" "}
            words have conflicting timing. Your lyric sheet matches the video
            plan.
          </p>
          <p>
            Correct these words under Advanced controls → Word timing, or choose
            to leave them off the video. Re-aligning may return the same gaps.
          </p>
          <label className="video-checkbox">
            <input
              type="checkbox"
              checked={omitUnusableWords}
              disabled={busy || sending || !timing.usable}
              onChange={(e) => setOmitUnusableWords(e.target.checked)}
            />
            Omit words with unusable timing
          </label>
          {omitUnusableWords && (
            <p role="status">
              {timing.usable} words will use their existing timing;{" "}
              {timing.omitted} words will be omitted from the video. Your saved
              lyrics stay complete.
            </p>
          )}
        </section>
      )}
      {(error || connectionError) && (
        <p className="form-error" role="alert">
          {error || connectionError}
        </p>
      )}
      {problem && !statusJob && (
        <p className="form-error" role="alert">
          {problem.error ===
            "Lyric timing does not match the reviewed lyrics. Align lyrics again." &&
          hasTimingGaps
            ? "The previous attempt omitted untimed lines from its request. All lines are now included; review the timing gaps above before resuming."
            : problem.error}{" "}
          {problem.kind === "song-video-render"
            ? "Any completed clips will be reused when you resume."
            : "Adjust the brief or try preparing again."}
        </p>
      )}
      {statusJob && (
        <div className="music-video-progress" role="status">
          <strong>{statusJob.result?.phase || "Queued"}</strong>
          <p>
            You can leave this page and return. Progress and finished clips are
            saved.
          </p>
          {rendering && (
            <button className="secondary-button" onClick={() => void stop()}>
              Stop after current clip
            </button>
          )}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="music-video-start">
        <div>
          <strong>
            {plan
              ? `${plan.clipCount} clips · ${timeLabel(plan.duration)} video`
              : `${plannedCount} unique clips · ${timeLabel(duration)} soundtrack`}
          </strong>
          <p>
            {plan
              ? "Your storyboard is ready. Clips will render one at a time, then join into a full MP4."
              : "Prepare the storyboard first. No video generation starts until you choose Create video."}
          </p>
        </div>
        {!plan ? (
          <button
            className="primary-button"
            disabled={!config.theme.trim() || busy || sending || !loaded}
            onClick={() => void submit("plan", inputs)}
          >
            Prepare video
          </button>
        ) : (
          <button
            className="primary-button"
            disabled={
              busy ||
              sending ||
              timingBlocked ||
              (config.showLyrics && !lyrics.trim())
            }
            onClick={() =>
              void submit("render", {
                planId: planJob!.id,
                cues: config.showLyrics ? cues : [],
                lyrics,
                omitUnusableWords: config.showLyrics && omitUnusableWords,
              })
            }
          >
            <Film size={16} />
            {canResume ? "Resume video" : "Create video"}
          </button>
        )}
      </div>
      {plan && (
        <details className="music-video-storyboard">
          <summary>
            Review or change the plan{" "}
            <span>{plan.scenes.length} clip descriptions</span>
          </summary>
          <p className="video-field-note">
            To change the story, edit the theme above and prepare a new plan
            before rendering.
          </p>
          <ol>
            {plan.scenes.map((scene, i) => (
              <li key={i}>
                <strong>{scene.name}</strong>
                <p>{scene.prompt}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
      {jobs
        .filter(
          (j) =>
            j.kind === "song-video-render" &&
            j.state === "succeeded" &&
            j.result?.videoUrl,
        )
        .reverse()
        .map((job) => (
          <section className="music-video-result" key={job.id}>
            <h2>Your music video</h2>
            {!!job.result?.omittedLyricWords && (
              <p className="video-field-note">
                {job.result.omittedLyricWords} lyric words were omitted because
                their timing was unusable.
              </p>
            )}
            <video controls preload="metadata" src={job.result!.videoUrl} />
            <a className="secondary-button" href={job.result!.downloadUrl}>
              <Download size={16} />
              Download MP4
            </a>
          </section>
        ))}
    </div>
  );
}
