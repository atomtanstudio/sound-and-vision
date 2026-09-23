/* Talks to the Vite-mounted local MP4 renderer (/local-api/*) — same contract
 * as the legacy editor so renders keep queueing and surviving reloads. */
import { useEffect, useRef, useState } from "react";
import { createRequestId } from "../../../music-studio/api";

export type ExportJob = {
  id: string;
  state: string;
  title: string;
  phase: string;
  error: string | null;
  frames: number;
  totalFrames: number;
  queuePosition: number | null;
  created: number;
  aspect: string;
  lyrics: boolean;
  downloadUrl: string | null;
  videoUrl: string | null;
  preview?: boolean;
  artworkId?: string | null;
  renderHost?: string;
  framesPerSecond?: number | null;
  remainingSeconds?: number | null;
};
export async function localApi<T>(
  endpoint: "visualizer-renders" | "kinetic-renders",
  path = "",
  body?: unknown,
  method?: string,
  timeout = 15000,
): Promise<T> {
  const response = await fetch(`/local-api/${endpoint}${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeout),
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data?.detail === "string"
        ? data.detail
        : "Could not reach the video renderer",
    );
  return data as T;
}

export function useLocalRenders(
  endpoint: "visualizer-renders" | "kinetic-renders",
  takeId: string,
  enabled: boolean,
) {
  const [jobs, setJobs] = useState<ExportJob[]>([]);
  const [available, setAvailable] = useState(false);
  const [songScenes, setSongScenes] = useState(false);
  const [referencePlayer, setReferencePlayer] = useState(false);
  const [renderer, setRenderer] = useState("renderer");
  const [connectionError, setConnectionError] = useState("");
  useEffect(() => {
    setJobs([]);
    setAvailable(false);
    setSongScenes(false);
    setReferencePlayer(false);
    setConnectionError("");
    if (!enabled) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await localApi<{
          available: boolean;
          jobs: ExportJob[];
          renderer?: string;
          capabilities?: { songScenes?: number; referencePlayer?: number };
        }>(endpoint, `?takeId=${encodeURIComponent(takeId)}`);
        if (disposed) return;
        setJobs(result.jobs);
        setAvailable(result.available);
        setSongScenes(result.capabilities?.songScenes === 1);
        setReferencePlayer(result.capabilities?.referencePlayer === 1);
        setRenderer(result.renderer || "Mac");
        setConnectionError("");
      } catch (e) {
        if (!disposed) {
          setAvailable(false);
          setConnectionError((e as Error).message);
        }
      }
      if (!disposed) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [endpoint, takeId, enabled]);
  const active = jobs.some((job) => ["queued", "running"].includes(job.state));
  /* Idempotent submission: the same request body keeps its request id. */
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const requestIdFor = (body: unknown) => {
    const signature = JSON.stringify(body);
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: createRequestId() };
    return pending.current.id;
  };
  const rememberDone = () => (pending.current = null);
  const mergeJob = (job: ExportJob) =>
    setJobs((old) => [job, ...old.filter((item) => item.id !== job.id)]);
  const cancel = async (job: ExportJob) => {
    await localApi(endpoint, `/${job.id}/cancel`, {}, "POST");
  };
  return {
    jobs,
    available,
    songScenes,
    referencePlayer,
    renderer,
    connectionError,
    active,
    requestIdFor,
    rememberDone,
    mergeJob,
    cancel,
  };
}
