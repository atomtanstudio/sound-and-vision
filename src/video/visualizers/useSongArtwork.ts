import { useEffect, useRef, useState } from "react";
import { ApiError, createRequestId, request } from "../../music-studio/api";
import type { SongScene } from "./scene";

export type ArtworkJob = {
  id: string;
  state: string;
  created: number;
  error?: string;
  result: (SongScene & { phase?: string }) | null;
  input: {
    takeId: string;
    aspect: string;
    song: { genre: string; lyrics: string; notes: string };
  };
};
export function useSongArtwork(takeId: string, enabled: boolean) {
  const [jobs, setJobs] = useState<ArtworkJob[]>([]);
  const [error, setError] = useState("");
  const [available, setAvailable] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const current = useRef(takeId);
  current.current = takeId;
  const pending = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setJobs([]);
    setError("");
    setAvailable(false);
    setSubmitting(false);
    pending.current = null;
    if (!enabled) return;
    const poll = async () => {
      try {
        const data = await request<{ jobs: ArtworkJob[]; available: boolean }>(
          `/takes/${takeId}/reactive-artwork`,
        );
        if (!cancelled) {
          setJobs(data.jobs);
          setAvailable(data.available);
          setError("");
        }
      } catch (e) {
        if (!cancelled) {
          setAvailable(false);
          setError(
            e instanceof ApiError && e.status === 404
              ? "The song artwork service needs the matching backend update."
              : (e as Error).message,
          );
        }
      }
      if (!cancelled) timer = setTimeout(poll, 2500);
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [takeId, enabled]);
  async function create(body: {
    aspect: string;
    genre: string;
    lyrics: string;
    notes: string;
  }) {
    setSubmitting(true);
    setError("");
    const owner = takeId;
    const signature = JSON.stringify({ takeId, ...body });
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: createRequestId() };
    try {
      const job = await request<ArtworkJob>(
        `/takes/${takeId}/reactive-artwork`,
        { ...body, requestId: pending.current.id },
      );
      if (current.current === owner) {
        setJobs((old) => [
          ...old.filter((j) => j.id !== job.id),
          { ...job, input: { takeId, aspect: body.aspect, song: body } },
        ]);
        pending.current = null;
      }
    } catch (e) {
      if (current.current === owner) setError((e as Error).message);
    } finally {
      if (current.current === owner) setSubmitting(false);
    }
  }
  const own = jobs.filter((j) => j.input.takeId === takeId);
  return {
    jobs: own,
    error,
    available,
    submitting,
    create,
    active: own.some((j) =>
      ["queued", "running", "waiting-for-resource"].includes(j.state),
    ),
  };
}
export type SongArtworkController = ReturnType<typeof useSongArtwork>;
