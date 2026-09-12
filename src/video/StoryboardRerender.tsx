import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, RotateCcw, X } from 'lucide-react';
import { request } from '../music-studio/api';

export function StoryboardRerender({filmId,index,name,imageUrl,close,submit}:{
  filmId:string;index:number;name:string;imageUrl:string;close:()=>void;
  submit:(prompt:string,revision:number)=>Promise<void>;
}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [original,setOriginal]=useState(''),[prompt,setPrompt]=useState('');
  const [revision,setRevision]=useState(0),[loading,setLoading]=useState(true),[submitting,setSubmitting]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    const element=dialog.current!;element.showModal();
    let alive=true;
    request<{prompt:string;revision:number}>(`/films/${filmId}/scenes/${index}/storyboard/prompt`)
      .then(value=>{if(alive){setOriginal(value.prompt);setPrompt(value.prompt);setRevision(value.revision);}})
      .catch(e=>{if(alive)setError(e.message);})
      .finally(()=>{if(alive)setLoading(false);});
    return()=>{alive=false;element.close();};
  },[filmId,index]);
  async function generate(){
    setSubmitting(true);setError('');
    try{await submit(prompt,revision);close();}
    catch(e){setError((e as Error).message);}
    finally{setSubmitting(false);}
  }
  return <dialog ref={dialog} className="modal storyboard-rerender" aria-labelledby="storyboard-rerender-title"
    onCancel={event=>{event.preventDefault();if(!submitting)close();}}
    onClick={event=>{if(event.target===event.currentTarget && !submitting)close();}}>
    <div className="modal-head"><h2 id="storyboard-rerender-title">Re-render storyboard frame {index+1}</h2>
      <button type="button" className="icon-button" aria-label="Close re-render dialog" disabled={submitting} onClick={close}><X size={18}/></button></div>
    <form className="modal-body" onSubmit={event=>{event.preventDefault();void generate();}}>
      <div className="storyboard-rerender-intro"><img src={imageUrl} alt={`Current storyboard frame: ${name}`}/>
        <div><h3>{name}</h3><p>Use the saved prompt for a fresh attempt, or edit it to correct details such as extra arms. Character and location references are reused.</p></div></div>
      {loading?<p role="status">Loading the saved image prompt…</p>:original && <label>Image prompt
        <textarea rows={15} minLength={20} maxLength={65536} required value={prompt} disabled={submitting}
          onChange={event=>setPrompt(event.target.value)}/></label>}
      {error && <p className="directed-error" role="alert">{error}</p>}
      <p>Creates one replacement storyboard image. Existing video takes remain available.</p>
      <div className="storyboard-rerender-actions"><button type="button" className="secondary-button" disabled={submitting} onClick={close}>Cancel</button>
        <button type="submit" className="primary-button" disabled={loading || submitting || !revision || prompt.trim().length<20}>
          {submitting?<LoaderCircle size={16} className="directed-spinner"/>:<RotateCcw size={16}/>}
          {submitting?'Submitting…':prompt===original?'Re-render frame':'Generate revised frame'}</button></div>
    </form>
  </dialog>;
}
