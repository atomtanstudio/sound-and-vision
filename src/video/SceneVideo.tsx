import { useEffect, useState } from 'react';
import { Check, LoaderCircle, RotateCcw } from 'lucide-react';
import type { FilmState } from './FilmReview';

export function SceneVideo({scene,job,lastJob,busy,rerender,accept,recover,onPlay}:{
  scene:FilmState['scenes'][number];job?:FilmState['jobs'][number];lastJob?:FilmState['jobs'][number];
  busy:boolean;rerender:()=>Promise<void>;accept:(id:string)=>void;recover:(id:string)=>void;onPlay:()=>void;
}) {
  const ready=scene.takes.filter(t=>t.state==='ready');
  const newest=ready.at(-1);
  const [previewId,setPreviewId]=useState(newest?.id || '');
  const [submitting,setSubmitting]=useState(false),[error,setError]=useState('');
  useEffect(()=>setPreviewId(newest?.id || ''),[newest?.id]);
  const take=ready.find(t=>t.id===previewId) || newest;
  if(!take)return null;
  async function render(){
    setSubmitting(true);setError('');
    try{await rerender();}catch(e){setError((e as Error).message);}finally{setSubmitting(false);}
  }
  return <div className="directed-scene-video">
    <video key={take.id} controls preload="none" src={take.mediaUrl} poster={take.posterUrl} onPlay={onPlay}/>
    <div className="directed-video-takes">
      <label>Video take
        <select aria-label={`Video take for scene ${scene.index+1}`} value={take.id} onChange={e=>setPreviewId(e.target.value)}>
          {ready.map(t=><option key={t.id} value={t.id}>{t.label}{t.id===scene.selected?' · selected for film':''}</option>)}
        </select>
      </label>
      {take.id===scene.selected?<span className="directed-video-selected"><Check size={14}/> Selected for film</span>:
        <button type="button" className="secondary-button" disabled={busy || !!job || submitting} onClick={()=>accept(take.id)}>Use this take</button>}
    </div>
    <button type="button" className="secondary-button" disabled={busy || !!job || submitting} onClick={()=>void render()}>
      {job || submitting?<LoaderCircle className="directed-spinner" size={15}/>:<RotateCcw size={15}/>}
      {submitting?'Submitting video…':job?job.state==='queued'?'Video queued…':'Re-rendering video…':'Re-render video'}
    </button>
    <p className="film-help">Creates a new video from the current storyboard and song excerpt. Earlier takes stay available.</p>
    {job && <div className="film-frame-status is-running" role="status">
      <strong>{job.state==='queued'?'Video queued':'Rendering new video take…'}</strong><p>{job.phase}</p>
    </div>}
    {!job && lastJob?.state==='ready' && lastJob.operation==='video-rerender' && newest?.id===lastJob.id && take.id===newest.id && newest.id!==scene.selected &&
      <p role="status"><Check size={14}/> {newest.label} is ready. Review it, then choose “Use this take” to select it for the film.</p>}
    {!job && lastJob?.state==='failed' && <div className="film-frame-status is-failed" role="alert">
      <strong>Video re-render needs attention</strong><p>{lastJob.error || 'The render stopped. Your earlier video is still available.'}</p>
      <button type="button" className="secondary-button" disabled={busy} onClick={()=>recover(lastJob.id)}>Recover video render</button>
    </div>}
    {error && <p className="directed-error" role="alert">{error}</p>}
    {take.timingOutdated && <p role="status">This take predates the vocal-timing correction. Re-render the video to test the updated timing.</p>}
    {take.checks?.aiReview && <p role="status">{take.checks.aiReview.result==='needs-review'?'Check this scene: ':'Review: '}{take.checks.aiReview.summary}</p>}
  </div>;
}
