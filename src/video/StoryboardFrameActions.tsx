import { useEffect, useState } from 'react';
import { Check, CircleAlert, LoaderCircle, RotateCcw } from 'lucide-react';
import type { FilmState } from './FilmReview';

type Job = FilmState['jobs'][number];
const active = (state?: string) => ['queued', 'running', 'waiting-for-resource'].includes(state || '');

export function StoryboardFrameActions({ job, busy, open, recover }: {
  job?: Job; busy: boolean; open: () => void; recover: (id: string) => void;
}) {
  const working = active(job?.state);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!working) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [working, job?.id]);
  const elapsed = job?.queuedAt ? Math.max(0, Math.floor((now - job.queuedAt / 1e6) / 1000)) : null;
  const label = job?.state === 'queued' ? 'Frame queued'
    : job?.state === 'waiting-for-resource' ? 'Waiting to re-render frame'
    : job?.state === 'running' ? 'Re-rendering frame…'
    : job?.state === 'ready' ? 'Frame updated'
    : job?.state === 'failed' ? 'Frame re-render failed'
    : job?.state === 'cancelled' ? 'Frame re-render cancelled' : '';
  return <div className="film-frame-actions">
    <button type="button" className="secondary-button" disabled={busy || working} onClick={open}>
      {working ? <LoaderCircle className="directed-spinner" size={14} /> : <RotateCcw size={14} />}
      {working ? job?.state === 'queued' ? 'Queued…' : 'Re-rendering…' : 'Re-render frame'}
    </button>
    {job && label && <div className={`film-frame-status is-${job.state}`}>
      <div className="film-frame-status-heading">
        <span role="status" aria-live="polite">
          {working ? <LoaderCircle className="directed-spinner" size={16} /> : job.state === 'ready' ? <Check size={16} /> : job.state === 'failed' ? <CircleAlert size={16} /> : null}
          <strong>{label}</strong>
        </span>
        {working && elapsed !== null && <span role="timer" aria-live="off">
          {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')} elapsed
        </span>}
      </div>
      {working && <p>Your request was received. The current frame stays visible until the replacement is ready.</p>}
      {job.state === 'ready' && <p>Re-render complete. Review the image above.</p>}
      {job.state === 'failed' && <><p role="alert">{job.error || 'The image request stopped without an error detail. The current frame is retained.'}</p>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => recover(job.id)}>Recover frame re-render</button></>}
    </div>}
  </div>;
}
