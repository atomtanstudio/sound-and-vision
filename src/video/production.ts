import { useEffect, useState } from "react";
import { request } from "../music-studio/api";
import type { BackgroundKind } from "./timeline";
export type AlignedWord = {
  text: string;
  start: number | null;
  end: number | null;
  confidence: number;
  review: string | null;
};
export type Alignment = {
  unmatchedVocalWords?: number;
  lyrics: string;
  duration: number;
  reviewCount: number;
  wordCount: number;
  method: string;
  cues: {
    id: string;
    text: string;
    start: number | null;
    end: number | null;
    words: AlignedWord[];
  }[];
};
export type VideoJob = {
  created?: number;
  id: string;
  kind: "video-image" | "video-motion" | "lyric-alignment";
  state: string;
  error: string | null;
  input: {
    kind: BackgroundKind | "alignment";
    takeId: string;
    slot: number;
    aspect: string;
    seconds: number;
    lyrics: string;
    prompt: string;
    language: string;
  };
  result:
    | (Partial<Alignment> & {
        assetUrl?: string;
        name?: string;
        phase?: string;
        sourceDimensions?: number[];
      })
    | null;
};
export const busyJob = (job: VideoJob) =>
  ["queued", "running", "waiting-for-resource"].includes(job.state);
export function useVideoProduction(takeId: string) {
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [error, setError] = useState("");
  const [installed, setInstalled] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    let cancelled = false,
      timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const state = await request<{
          jobs: VideoJob[];
          alignmentInstalled: boolean;
        }>(`/takes/${takeId}/video`);
        if (!cancelled) {
          setJobs(state.jobs);
          setInstalled(state.alignmentInstalled);
          setError("");
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
      if (!cancelled) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [takeId]);
  async function submit(inputs: Omit<VideoJob["input"], "takeId">[]) {
    setSubmitting(true);
    setError("");
    try {
      for (const input of inputs) {
        const job = await request<VideoJob>(`/takes/${takeId}/video`, {
          ...input,
          requestId: crypto.randomUUID(),
        });
        setJobs((old) => [
          ...old.filter((j) => j.id !== job.id),
          { ...job, input: { ...input, takeId } },
        ]);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  async function action(job: VideoJob, operation: "cancel" | "retry") {
    try {
      await request(`/video/jobs/${job.id}/${operation}`, {});
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return { jobs, error, installed, submitting, submit, action };
}
