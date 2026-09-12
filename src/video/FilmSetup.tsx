import { useEffect, useRef, useState } from 'react';
import { Clapperboard, Film, LoaderCircle, Mic2, SlidersHorizontal, WandSparkles } from 'lucide-react';
import { request } from '../music-studio/api';
import { readLocal, writeLocal, type Track } from '../music-studio/model';
import { defaultCredits, FilmCreditsEditor } from './FilmCredits';
import { completeConcept, conceptMinimums, emptyConcept, emptyCreative, type FilmConcept, type FilmSetupPayload } from './film-concept';
import './film-setup.css';

type ConceptJob = { id:string; state:string; result?:{concept:FilmConcept}; error?:string };
type Draft = FilmSetupPayload & { conceptJobId?:string };
type ConceptBody = {requestId:string;takeId:string;direction:string;treatment:FilmSetupPayload['treatment'];creative:FilmSetupPayload['creative'];existingConcept:FilmConcept|null};

export function ConceptFields({ concept, performance, change, disabled=false }: {
  concept:FilmConcept; performance:boolean; change?:(concept:FilmConcept)=>void; disabled?:boolean;
}) {
  const edit = (key:keyof FilmConcept,label:string,rows=3) => <label key={key}>
    <span>{label}</span>
    {change ? <textarea aria-label={label} rows={rows} disabled={disabled} value={concept[key]}
      minLength={conceptMinimums[key]} maxLength={key==='protagonist'?700:key==='relationships'?1200:['motivation','visualMotif'].includes(key)?1000:1500}
      onChange={(e)=>change({...concept,[key]:e.target.value})} /> : <p>{concept[key]}</p>}
  </label>;
  return <div className="film-concept-fields">
    {edit('premise','The film in a few sentences')}
    <details open className="film-concept-people">
      <summary>{performance ? 'Performers and intention' : 'Characters and motivation'}</summary>
      <div className="film-control-grid">
        {edit('protagonist',performance?'Performers':'Who we follow')}
        {edit('motivation',performance?'Performance intention':'What they want, and why')}
      </div>
      {edit('relationships',performance?'Roles on stage':'How the characters are connected',2)}
    </details>
    <div className="film-story-arc">
      {([
        ['beginning',performance?'Opening':'Introduction'],
        ['conflict',performance?'Build':'Conflict'],
        ['turningPoint',performance?'Peak':'Turning point'],
        ['resolution',performance?'Closing image':'Resolution'],
      ] as const).map(([key,label],index)=><div key={key} className="film-story-beat">
        <span className="film-beat-number" aria-hidden="true">{index+1}</span>{edit(key,label)}
      </div>)}
    </div>
    <details><summary>Visual thread and continuity</summary>
      {edit('visualMotif','Visual thread',2)}
      {edit('continuityRules','What must stay consistent',2)}
    </details>
  </div>;
}

export function FilmSetup({track,busy,onCreate}:{track:Track;busy:boolean;onCreate:(payload:FilmSetupPayload)=>Promise<void>}) {
  const key=`sv-film-creative:${track.id}`;
  const [draft,setDraft]=useState<Draft>(()=>{
    const previous=readLocal<{title?:string;artist?:string;direction?:string}>(`sv-film-setup:${track.id}`,{});
    return readLocal<Draft>(key,{
      title:previous.title || track.title,artist:previous.artist || '',direction:previous.direction || '',
      treatment:'mixed',creative:{...emptyCreative},concept:null,workflow:'short-film',sceneSeconds:10,
      sceneTiming:'storyboard',renderTier:'native',credits:defaultCredits(previous.title || track.title,previous.artist || ''),
    });
  });
  const [error,setError]=useState('');
  const [submitting,setSubmitting]=useState(false);
  const intent=useRef<ConceptBody|null>(null);
  const conceptJobId=draft.conceptJobId;
  const writing=!!conceptJobId || submitting;
  const locked=busy || writing;
  const performance=draft.treatment==='performance';
  const patch=(value:Partial<Draft>)=>setDraft((old)=>({...old,...value}));
  useEffect(()=>{writeLocal(key,draft);},[key,draft]);
  useEffect(()=>{
    if(!conceptJobId)return;
    let alive=true, timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      try {
        const job=await request<ConceptJob>(`/assistance/${conceptJobId}`);
        if(!alive)return;
        if(job.state==='succeeded' && job.result?.concept){
          setDraft((old)=>({...old,concept:job.result!.concept,conceptJobId:undefined}));
          intent.current=null;setError('');return;
        }
        if(['failed','cancelled'].includes(job.state)){
          patch({conceptJobId:undefined});intent.current=null;setError(job.error || 'Concept writing was cancelled.');return;
        }
      } catch(e){if(alive)setError((e as Error).message);}
      if(alive)timer=setTimeout(poll,1500);
    };
    void poll();
    return()=>{alive=false;clearTimeout(timer);};
  },[conceptJobId]);
  async function develop(){
    setSubmitting(true);setError('');
    const input={takeId:track.id,direction:draft.direction,treatment:draft.treatment,creative:draft.creative,
      existingConcept:completeConcept(draft.concept)?draft.concept:null};
    if(!intent.current || JSON.stringify({...intent.current,requestId:undefined})!==JSON.stringify(input))
      intent.current={requestId:crypto.randomUUID(),...input};
    try {
      const job=await request<ConceptJob>('/films/concepts',intent.current);
      patch({conceptJobId:job.id});
    } catch(e){setError((e as Error).message);} finally {setSubmitting(false);}
  }
  const control=(field:keyof Draft['creative'],label:string,placeholder:string,rows=2)=><label>
    <span>{label} <small>Optional</small></span>
    <textarea rows={rows} disabled={locked} value={draft.creative[field]} placeholder={placeholder}
      maxLength={['cast','mustInclude','avoid'].includes(field)?1500:field==='setting'?700:field==='mood'?300:500}
      onChange={(e)=>patch({creative:{...draft.creative,[field]:e.target.value}})} />
  </label>;
  return <div className="film-setup">
    <ol className="film-workflow-steps" aria-label="Film creation stages">
      <li aria-current="step"><span>1</span> Develop the concept</li>
      <li><span>2</span> Cast & storyboard</li>
      <li><span>3</span> Animate & edit</li>
    </ol>
    <div className="film-setup-heading"><h2>Make a short film from your song</h2>
      <p>Bring a complete idea, a few words, or let the lyrics suggest the story. Shape it here before creating images.</p></div>
    <fieldset className="film-format-choice" disabled={locked}>
      <legend>What kind of film?</legend>
      {([
        ['story',Film,'Story','A complete narrative; the song stays off camera.'],
        ['mixed',Clapperboard,'Story + performance','A coherent story woven together with the performers.'],
        ['performance',Mic2,'Performance','A solo artist or band, with a deliberate build and finish.'],
      ] as const).map(([value,Icon,label,description])=><button type="button" key={value}
        className={draft.treatment===value?'selected':''} aria-pressed={draft.treatment===value}
        onClick={()=>patch({treatment:value})}><Icon size={19}/><strong>{label}</strong><span>{description}</span></button>)}
    </fieldset>
    <section className="film-idea-section">
      <div className="film-section-heading"><h3>Your starting idea</h3><span>Optional</span></div>
      <textarea aria-label="Your starting idea" rows={4} maxLength={6000} disabled={locked} value={draft.direction}
        placeholder="A character, a setting, an ending, or a rough idea. Leave this blank to build a concept from the lyrics."
        onChange={(e)=>patch({direction:e.target.value})}/>
      <details className="film-creative-choices"><summary><SlidersHorizontal size={16}/> Guide the creative choices <span>Leave anything blank for the director</span></summary>
        <div className="film-control-grid">
          {control('visualStyle','Visual style','Cinematic realism, animation, noir, painted fantasy…')}
          {control('setting','Setting and era','A coastal town in winter; contemporary rehearsal room…')}
          {control('cast','Characters or band members','Who appears, their roles, relationships and appearance.',3)}
          {control('mood','Emotional tone','Tense, warm, melancholic, hopeful, playful…',3)}
          {control('ending','Ending preference',performance?'A final stage image or musical release.':'A resolution you want the film to earn.')}
          {control('camera','Camera and movement','Still and intimate, handheld, slow tracking, energetic…')}
          {control('mustInclude','Must include','An important action, location, object or story detail.')}
          {control('avoid','Keep out','Unwanted imagery, actions, characters or visual styles.')}
        </div>
      </details>
      <div className="film-concept-actions">
        <button type="button" className="primary-button" disabled={locked} onClick={()=>void develop()}>
          {writing?<LoaderCircle size={17} className="directed-spinner"/>:<WandSparkles size={17}/>}
          {writing?'Developing the film…':draft.concept?'Develop this concept':draft.direction.trim()?'Develop my idea':'Find a concept in the lyrics'}
        </button>
        {!draft.concept && <button className="secondary-button" type="button" disabled={locked}
          onClick={()=>patch({concept:{...emptyConcept}})}>Write the concept myself</button>}
        {conceptJobId && <button className="secondary-button" type="button" onClick={()=>void request(`/assistance/${conceptJobId}/cancel`,{}).catch(e=>setError(e.message))}>Cancel</button>}
        <p>Writes a complete concept. No images or video are created yet.</p>
      </div>
      {error && <p className="directed-error" role="alert">{error}</p>}
    </section>
    {draft.concept && <section className="film-treatment-section">
      <div className="film-section-heading"><h3>{performance?'Performance treatment':'The complete story'}</h3><span>Every field is editable</span></div>
      <ConceptFields concept={draft.concept} performance={performance} disabled={locked} change={(concept)=>patch({concept})}/>
    </section>}
    <details className="film-production-options"><summary><SlidersHorizontal size={16}/> Pacing, detail and credits</summary>
      <div className="film-control-grid">
        <label>Scene pacing<select disabled={locked} value={draft.sceneTiming} onChange={(e)=>patch({sceneTiming:e.target.value as Draft['sceneTiming']})}>
          <option value="storyboard">Let the story choose the cuts</option><option value="beats">Favor cuts near musical beats</option><option value="fixed">Use even scene lengths</option>
        </select></label>
        <label>Preferred scene length<select disabled={locked} value={draft.sceneSeconds} onChange={(e)=>patch({sceneSeconds:Number(e.target.value)})}>
          {[5,8,10,12,15].map(n=><option key={n} value={n}>About {n} seconds</option>)}</select></label>
        <label>Render detail<select disabled={locked} value={draft.renderTier} onChange={(e)=>patch({renderTier:e.target.value as Draft['renderTier']})}>
          <option value="native">Full detail · 1344 × 768 source</option><option value="standard">Preview detail · 960 × 544 source</option>
        </select></label>
        <p>Both finish as a 1080p film. You can adjust cuts before animation and repair individual scenes afterward.</p>
      </div>
      <FilmCreditsEditor value={draft.credits} onChange={(credits)=>patch({credits,artist:credits.artist})}/>
    </details>
    <div className="film-storyboard-submit">
      <label>Film title<input disabled={locked} value={draft.title} maxLength={160} onChange={(e)=>patch({title:e.target.value})}/></label>
      <div><button className="primary-button" type="button" disabled={locked || !draft.title.trim() || !completeConcept(draft.concept)}
        onClick={()=>{const {conceptJobId:_,...payload}=draft;void onCreate(payload);}}>
        {busy?<LoaderCircle size={17} className="directed-spinner"/>:<Clapperboard size={17}/>} Create character sheets & storyboard
      </button><p>{completeConcept(draft.concept)?'Creates a sheet for each character and an image for each scene. You’ll review them before animating.':'Develop a concept above, or complete the story fields, to continue.'}</p></div>
    </div>
  </div>;
}
