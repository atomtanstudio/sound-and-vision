/* Same contract as the legacy useVideoProduction hook, plus an `enabled`
 * flag so demo/sample soundtracks don't poll an endpoint that only exists
 * for server takes. */
import { useEffect, useState } from "react";
import { createRequestId, request } from "../../../music-studio/api";
import type { BackgroundKind } from "../../../video/timeline";
import type { VideoJob } from "../../../video/production";
export type { VideoJob };
export { busyJob } from "../../../video/production";

export function useProduction(takeId: string, enabled: boolean) {
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    setJobs([]);
    setError("");
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const state = await request<{ jobs: VideoJob[] }>(`/takes/${takeId}/video`);
        if (!cancelled) {
          setJobs(state.jobs);
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
  }, [takeId, enabled]);
  async function submit(inputs: Omit<VideoJob["input"], "takeId">[]) {
    setSubmitting(true);
    setError("");
    try {
      for (const input of inputs) {
        const job = await request<VideoJob>(`/takes/${takeId}/video`, {
          ...input,
          kind: input.kind as unknown as "images" | "motion" | "alignment" | "transcription",
          requestId: createRequestId(),
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
    setSubmitting(true);
    try {
      const updated = await request<VideoJob>(`/video/jobs/${job.id}/${operation}`, {});
      setJobs((old) => [
        ...old.filter((j) => j.id !== updated.id),
        { ...updated, input: job.input },
      ]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  return { jobs, error, submitting, submit, action };
}
