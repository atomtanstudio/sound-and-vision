import { useEffect, useRef, useState } from "react";
import { Download, Film } from "lucide-react";
import { createRequestId, request } from "../../../music-studio/api";
import { readLocal, writeLocal, type Track } from "../../../music-studio/model";
import { timeLabel } from "../../context";
import { lyricTimingReview, type LyricCue } from "../../../video/timeline";
import {
  Btn,
  CheckRow,
  ErrorNote,
  Kicker,
  Segmented,
  Select,
  TextArea,
  TextInput,
} from "../../ui";

type Config = {
  theme: string;
  coverage: "full" | "repeat";
  clipCount: number;
  clipSeconds: number;
  join: "cut" | "dissolve" | "continue";
  showLyrics: boolean;
};
type MovieJob = {
  id: string;
  kind: string;
  state: string;
  error: string | null;
  input: Record<string, unknown>;
  result: {
    phase?: string;
    scenes?: { name: string; prompt: string }[];
    clipCount?: number;
    duration?: number;
    theme?: string;
    videoUrl?: string;
    downloadUrl?: string;
    omittedLyricWords?: number;
  } | null;
};
const busy = (job: MovieJob) =>
  ["queued", "running", "waiting-for-resource"].includes(job.state);

/* Guided cinematic: theme → storyboard plan → sequential clip render. */
export function CinematicMode({
  track,
  duration,
  aspect,
  lyrics,
  language,
  cues,
}: {
  track: Track;
  duration: number;
  aspect: "16:9" | "9:16";
  lyrics: string;
  language: string;
  cues: LyricCue[];
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
  const [connectionError, setConnectionError] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [omitUnusableWords, setOmitUnusableWords] = useState(false);
  const themeEdited = useRef(!!config.theme);
  const suggestedOnce = useRef(!!config.theme);
  const pendingId = useRef<{ signature: string; id: string } | null>(null);
  const change = (part: Partial<Config>) =>
    setConfig((old) => {
      const next = { ...old, ...part };
      writeLocal(key, next);
      return next;
    });
  const latest = (kind: string) => [...jobs].reverse().find((j) => j.kind === kind);
  const themeJob = latest("song-video-theme");
  const planJob = latest("song-video-plan");
  const renderJob = latest("song-video-render");
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
  async function submit(operation: "theme" | "plan" | "render", body: Record<string, unknown>) {
    setSending(true);
    setError("");
    setNotice("");
    const signature = JSON.stringify({ operation, body });
    if (pendingId.current?.signature !== signature)
      pendingId.current = { signature, id: createRequestId() };
    try {
      const job = await request<MovieJob>(
        `/takes/${track.id}/music-video/${operation}`,
        { ...body, requestId: pendingId.current.id },
      );
      setJobs((old) => [...old.filter((j) => j.id !== job.id), { ...job, input: { ...body, takeId: track.id } }]);
      pendingId.current = null;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  useEffect(() => {
    if (loaded && !suggestedOnce.current) {
      suggestedOnce.current = true;
      if (!themeJob && !themeEdited.current) void submit("theme", { lyrics });
    }
  }, [loaded]);
  useEffect(() => {
    if (
      themeJob?.state === "succeeded" &&
      themeJob.result?.theme &&
      !themeEdited.current
    )
      change({ theme: themeJob.result.theme });
  }, [themeJob?.id, themeJob?.state, themeJob?.result?.theme]);
  const overlap = config.join === "dissolve" ? 0.5 : 0;
  const fullCount = Math.max(1, Math.ceil((duration - overlap) / (config.clipSeconds - overlap)));
  const plannedCount =
    config.coverage === "full" ? fullCount : Math.min(config.clipCount, fullCount);
  const inputs = { ...config, lyrics, language, aspect, duration };
  const plan =
    planJob?.state === "succeeded" &&
    planJob.input.aspect === aspect &&
    planJob.input.duration === duration &&
    planJob.input.coverage === config.coverage &&
    planJob.input.clipSeconds === config.clipSeconds &&
    planJob.input.join === config.join
      ? planJob.result
      : undefined;
  const timing = lyricTimingReview(
    cues.map((cue) => ({
      words: (cue.words || []).map((word) => ({ ...word, confidence: 1 })),
    })),
    duration,
  );
  const hasGaps = config.showLyrics && cues.length > 0 && timing.omitted > 0;
  const statusJob = [...jobs].reverse().find(busy);
  const canResume =
    !!plan &&
    renderJob &&
    renderJob.input.planId === planJob?.id &&
    ["failed", "cancelled"].includes(renderJob.state);
  return (
    <>
      <section className="panel mode-panel">
        <h2>What should your video feel like?</h2>
        <div className="cinematic-theme">
          <TextArea
            rows={3}
            value={config.theme}
            placeholder="Describe a setting, mood, color palette or visual story…"
            onChange={(e) => {
              themeEdited.current = true;
              change({ theme: e.target.value });
            }}
          />
          <Btn
            variant="quiet"
            disabled={!!statusJob || sending}
            onClick={() => {
              themeEdited.current = false;
              void submit("theme", { lyrics });
            }}
          >
            Suggest
          </Btn>
        </div>
        <Segmented
          ariaLabel="Footage coverage"
          size="sm"
          options={[
            { value: "full", label: `New scenes for the whole song · ~${fullCount} clips` },
            { value: "repeat", label: "A smaller set that repeats" },
          ]}
          value={config.coverage}
          onChange={(coverage) => change({ coverage })}
        />
        {config.coverage === "repeat" ? (
          <label className="inline-number">
            <Kicker>Unique clips</Kicker>
            <TextInput
              inputMode="numeric"
              type="number"
              min={1}
              max={fullCount}
              value={config.clipCount}
              onChange={(e) =>
                change({ clipCount: Math.max(1, Math.min(fullCount, Number(e.target.value) || 1)) })
              }
            />
          </label>
        ) : null}
        <div className="cinematic-row">
          <Select aria-label="Clip length" value={config.clipSeconds} onChange={(e) => change({ clipSeconds: Number(e.target.value) })}>
            <option value={15}>15 s clips</option>
            <option value={10}>10 s clips</option>
            <option value={5}>5 s clips</option>
          </Select>
          <Select aria-label="Clip joins" value={config.join} onChange={(e) => change({ join: e.target.value as Config["join"] })}>
            <option value="dissolve">Soft blends</option>
            <option value="cut">Scene cuts</option>
            <option value="continue">Continue scenes in pairs</option>
          </Select>
          <CheckRow checked={config.showLyrics} onChange={(showLyrics) => change({ showLyrics })}>
            On-screen lyrics
          </CheckRow>
        </div>
        {hasGaps ? (
          <div className="cinematic-gaps">
            <p>
              {timing.missing} words have no timestamps, {timing.conflicting} conflict.
            </p>
            <CheckRow checked={omitUnusableWords} onChange={setOmitUnusableWords} disabled={!timing.usable}>
              Omit words with unusable timing ({timing.omitted})
            </CheckRow>
          </div>
        ) : null}
        {(error || connectionError) && <ErrorNote>{error || connectionError}</ErrorNote>}
        {!plan ? (
          <Btn
            variant="primary"
            disabled={!config.theme.trim() || !!statusJob || sending || !loaded}
            onClick={() => void submit("plan", inputs)}
          >
            Prepare video · {plannedCount} clips · {timeLabel(duration)} soundtrack
          </Btn>
        ) : (
          <Btn
            variant="primary"
            disabled={!!statusJob || sending || (hasGaps && !omitUnusableWords)}
            onClick={() =>
              void submit("render", {
                planId: planJob!.id,
                cues: config.showLyrics ? cues : [],
                lyrics,
                omitUnusableWords: config.showLyrics && omitUnusableWords,
                audioFade: null,
              })
            }
          >
            <Film size={16} /> {canResume ? "Resume video" : "Create video"}
          </Btn>
        )}
        {plan ? (
          <details className="storyboard">
            <summary>
              <Kicker>Storyboard</Kicker> <span>{plan.scenes?.length} clip descriptions</span>
            </summary>
            <ol>
              {plan.scenes?.map((scene, i) => (
                <li key={i}>
                  <strong>{scene.name}</strong>
                  <p>{scene.prompt}</p>
                </li>
              ))}
            </ol>
          </details>
        ) : null}
        {statusJob ? (
          <div className="cinematic-progress" role="status">
            <strong>{statusJob.result?.phase || "Queued"}</strong>
            <span>You can leave and return — finished clips are kept.</span>
            {statusJob.kind === "song-video-render" ? (
              <Btn
                size="sm"
                variant="quiet"
                onClick={() =>
                  request<{ message: string }>(`/music-video/jobs/${statusJob.id}/stop`, {})
                    .then((r) => setNotice(r.message))
                    .catch((e) => setError((e as Error).message))
                }
              >
                Stop after current clip
              </Btn>
            ) : null}
          </div>
        ) : null}
        {notice ? <p className="muted small">{notice}</p> : null}
      </section>
      {jobs
        .filter((j) => j.kind === "song-video-render" && j.state === "succeeded" && j.result?.videoUrl)
        .reverse()
        .map((job) => (
          <section className="panel cinematic-result" key={job.id}>
            <h2>Your music video</h2>
            {!!job.result?.omittedLyricWords && (
              <p className="muted small">
                {job.result.omittedLyricWords} lyric words were omitted because their timing was unusable.
              </p>
            )}
            <video controls preload="metadata" src={job.result!.videoUrl!} />
            <a className="btn btn-ghost btn-sm" href={job.result!.downloadUrl} download>
              <Download size={14} /> Download MP4
            </a>
          </section>
        ))}
    </>
  );
}
