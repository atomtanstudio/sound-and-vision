"""Visual repair planning and bounded review; never an automatic render loop."""
import asyncio
import copy
import json
import math
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from .film_review import read, write


class RepairPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    intent: str = Field(max_length=500)
    observations: list[str] = Field(max_length=6)
    method: Literal['frame-regenerate','source-edit','reuse-shot']
    scope: Literal['entire-scene','interval']
    startSeconds: float = Field(ge=0, allow_inf_nan=False)
    endSeconds: float = Field(gt=0, allow_inf_nan=False)
    sourceStartSeconds: float = Field(ge=0, allow_inf_nan=False)
    sourceEndSeconds: float = Field(ge=0, allow_inf_nan=False)
    anchorFrame: int = Field(ge=0)
    cutPolicy: Literal['single-shot','preserve-source']
    speechPolicy: Literal['silent','original-performance']
    action: str = Field(min_length=20,max_length=3500)
    continuity: str = Field(max_length=1500)
    explanation: str = Field(max_length=1000)
    needsClarification: bool
    question: str = Field(max_length=500)


class VisualReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    result: Literal['no-obvious-issue','needs-review','uncertain']
    summary: str = Field(max_length=1000)
    findings: list[str] = Field(max_length=6)
    mouth: Literal['no-obvious-issue','possible-mouthing','not-assessable','not-visible']


def sample_frames(count, fps, cuts=()):
    candidates={0,count-1,*[round((count-1)*i/7) for i in range(1,7)]}
    for cut in cuts[:4]:candidates.add(min(count-1,max(0,round(cut*fps)+2)))
    return sorted(candidates)


def inspection_sheet(source, folder, count, fps, cuts=(), title='Selected source take', extra_frames=()):
    from PIL import Image, ImageDraw, ImageFont
    folder.mkdir(parents=True,exist_ok=True)
    metadata=folder/'frames.json';sheet=folder/'sheet.jpg'
    if sheet.exists() and metadata.exists():return read(metadata),sheet
    frames=sorted(set(sample_frames(count,fps,cuts)) | {min(count-1,max(0,f)) for f in extra_frames})
    expression='+'.join(f'eq(n\\,{f})' for f in frames)
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(source),'-vf',f'select={expression},scale=640:360',
                    '-fps_mode','vfr','-q:v','2',str(folder/'frame-%03d.jpg')],check=True,timeout=120)
    font_file=Path(__file__).resolve().parent.parent/'assets/fonts/SV-Manrope.ttf'
    font=ImageFont.truetype(str(font_file),20) if font_file.exists() else ImageFont.load_default()
    columns=3;canvas=Image.new('RGB',(640*columns,396*math.ceil(len(frames)/columns)), '#101014')
    draw=ImageDraw.Draw(canvas)
    for i,frame in enumerate(frames):
        x=(i%columns)*640;y=(i//columns)*396
        with Image.open(folder/f'frame-{i+1:03d}.jpg') as image:canvas.paste(image.convert('RGB'),(x,y+36))
        draw.text((x+8,y+7),f'{title} | F{frame} | {frame/fps:.2f}s',fill='white',font=font)
    canvas.save(sheet,quality=90)
    result={'frames':frames,'fps':fps,'sourceFrameCount':count,'sampling':'selected frames, not continuous video'}
    write(metadata,result)
    return result,sheet


async def review_voice(reviews,film_id,job_id,work,data):
    """Flag sampled mouth poses, without claiming audio-visual synchronization."""
    from .film_voice import voice_contract
    checks=read(work/'checks.json')
    if checks.get('aiReview'):return
    policy=checks.get('voicePolicy') or voice_contract(data);checks['voicePolicy']=policy
    locked=policy.get('timingAuthority')=='recorded-audio'
    reviews.update_job(film_id,job_id,'running','Checking faces against vocal and rest windows')
    try:
        shot=data['shot'];count=shot['endFrame']-shot['startFrame'];fps=data['plan']['fps']
        # Add evidence inside rests and around vocal transitions; avoid one
        # giant sheet for fast lyrics by bounding the additional frame budget.
        extra=[]
        for rest in ([] if locked else policy['restWindows']):
            for t in (rest['start']+.12,(rest['start']+rest['end'])/2,rest['end']-.12):
                if rest['start']<=t<min(rest['end'],policy['visibleDuration']):extra.append(round(t*fps))
        evidence,sheet=await asyncio.to_thread(inspection_sheet,work/'background.mp4',work/'voice-review',count,fps,
            checks.get('possibleInternalCuts',[]),'Vocal timing review',extra[:12])
        prompt=(('Inspect these timestamped frames for cast continuity and visible mouth poses. They are sampled frames, not continuous video or audio. '
            'The vocalist follows locked recorded audio. Word and rest windows are approximate alignment estimates, not verified silence boundaries. '
            'Do not flag the vocalist for an open mouth inside an estimated REST window. Set mouth to not-assessable for exact lip sync, which needs audio-video playback. '
            'Other cast members should stay silent; flag their suspected articulation with timestamp and character. ' if locked else
            'Inspect these timestamped frames against the measured vocal policy. They are sampled frames, not continuous video or audio. '
            'Report visible mouth poses that suggest speech during rest windows, unexpected cuts, or gross identity changes. '
            'Only the designated vocalist may articulate during vocal windows. Every other character stays silent even while the vocalist sings. '
            'Set possible-mouthing for suspected articulation during REST windows or by another cast member, and cite the timestamp and character. ') +
            'If a cast reference sheet is attached, compare each visible identity with its labeled original: hair length, beard, face, clothing and instrument ownership. '
            'Flag role swaps or identity drift as needs-review. Reference panels are different views of one character, not extra cast. '
            'Use uncertain/not-assessable for small or obscured faces; an open mouth alone is a possible issue, not proof of speaking. '
            'Do not claim exact lip sync, uninterrupted silence, or successful motion from still frames. '
            +json.dumps({'voicePolicy':policy,'cast':[{k:c[k] for k in ('id','name','role','appearance')} for c in shot.get('characterReferences',[])],
                        'sceneAction':shot['prompt'],'measuredCutCandidates':checks.get('possibleInternalCuts',[])},ensure_ascii=False))
        from .film_cast import review_sheet
        cast_sheet=review_sheet(data,work)
        items,model=await reviews.account.turn(prompt,VisualReview.model_json_schema(),reference_images=[sheet,*([cast_sheet] if cast_sheet else [])])
        text=next(i['text'] for i in reversed(items) if i.get('type')=='agentMessage')
        review=VisualReview.model_validate_json(text).model_dump()
        if review['mouth']=='possible-mouthing':review['result']='needs-review'
        elif review['mouth']=='not-assessable' and review['result']=='no-obvious-issue':review['result']='uncertain'
        review.update(model=model,coverage=('Sampled frames checked for cast continuity; exact lip sync requires playback with the recorded audio.' if locked else
                                           'Sampled frames checked against vocal/rest windows; full playback is still required.'),evidence=evidence)
    except Exception as error:
        review={'result':'uncertain','summary':'Automatic mouth review was unavailable. Play this scene to check it.',
                'findings':[str(error)[:350]],'mouth':'not-assessable'}
    checks['aiReview']=review;write(work/'checks.json',checks)


def normalize_plan(plan, data, frames):
    plan=copy.deepcopy(plan);fps=data['plan']['fps'];shot=data['shot'];count=shot['endFrame']-shot['startFrame']
    if plan['needsClarification']:raise ValueError(plan['question'] or 'Describe which change you want before rendering.')
    if plan['scope']=='entire-scene':start,end=0,count
    else:start,end=round(plan['startSeconds']*fps),round(plan['endSeconds']*fps)
    if not 0<=start<end<=count or end-start<2*fps:raise ValueError('The proposed repair range is invalid; no render was started.')
    if plan['anchorFrame'] not in frames:raise ValueError('The repair planner selected a frame it was not shown.')
    # Partial replacements must join the existing source at their original start.
    if start or end!=count:plan['anchorFrame']=start
    if plan['cutPolicy']=='single-shot' and plan['method']!='reuse-shot':plan['method']='frame-regenerate'
    if plan['method']=='source-edit' and (start or end!=count):plan['method']='frame-regenerate'
    if data['shot']['type']!='performance' or not data['timing']['words']:plan['speechPolicy']='silent'
    if plan['method']=='reuse-shot':
        a,b=round(plan['sourceStartSeconds']*fps),round(plan['sourceEndSeconds']*fps)
        if plan['scope']!='entire-scene' or plan['speechPolicy']!='silent':
            raise ValueError('Reusing a slowed shot is only available for a silent full-scene repair.')
        validate_reuse(a,b,count,fps,data['baseTake'].get('checks',{}).get('possibleInternalCuts',[]))
        plan.update(sourceRange={'startFrame':a,'endFrame':b},playbackSpeed=(b-a)/count,
                    sourceStartSeconds=a/fps,sourceEndSeconds=b/fps)
    plan.update(startSeconds=start/fps,endSeconds=end/fps,repairRange={'startFrame':start,'endFrame':end})
    return plan


def validate_reuse(start,end,count,fps,cuts):
    if not 0<=start<end<=count or end-start<max(2*fps,math.ceil(count/2)):
        raise ValueError('The continuous section must cover at least half the scene and two seconds; no render was started.')
    if any(start<round(t*fps)<end for t in cuts):
        raise ValueError('The proposed continuous section contains a measured cut; no render was started.')


def resolve_input(data, plan):
    resolved=copy.deepcopy(data)
    resolved.update(method=plan['method'],repairRange=plan['repairRange'] if plan['method']=='frame-regenerate' else None,
        repairAnchorFrame=plan['anchorFrame'],correction=plan['action'],sceneContinuity=plan['continuity'],
        smartPlan=plan,requestedMethod='smart')
    if plan['speechPolicy']=='silent':
        resolved['shot']['type']='narrative'
        resolved['timing']={'words':[],'spans':[],'uncertainWords':0,'leadingRest':resolved['shot']['end']-resolved['shot']['start']}
    return resolved


async def plan_repair(reviews, film_id, job_id, work, data):
    planned=work/'planned-input.json'
    if planned.exists():return read(planned)
    if not reviews.account:raise RuntimeError('Connect OpenAI for Smart repair. No render was started.')
    reviews.update_job(film_id,job_id,'running','Inspecting the source frames and interpreting your edit')
    shot=data['shot'];fps=data['plan']['fps'];count=shot['endFrame']-shot['startFrame']
    cuts=data['baseTake'].get('checks',{}).get('possibleInternalCuts',[])
    cuts=await asyncio.to_thread(detected_cuts,Path(data['baseTake']['source']))
    data=copy.deepcopy(data)
    data['baseTake'].setdefault('checks',{})['possibleInternalCuts']=cuts
    evidence,sheet=await asyncio.to_thread(inspection_sheet,Path(data['baseTake']['source']),work/'inspection',count,fps,cuts)
    supplied={
        'userNote':data['correction'],'userContinuity':data['sceneContinuity'],
        'storyboardAction':shot.get('prompt',''),'sceneName':shot['name'],'duration':count/fps,
        'sourceCutCandidates':cuts,'availableAnchorFrames':evidence['frames'],
        'sceneType':shot['type'],'vocalWindows':data['timing']['spans'],
        'filmContinuity':data['continuity'],
        'neighborScenes':[{'name':s['name'],'continuity':s['continuity']} for s in data['story'] if abs(s['index']-shot['index'])==1],
    }
    prompt=('You are a careful music-video editor. Infer the intended result from the plain-language user note, '
        'then choose a repair that can achieve it. Inspect the attached chronological frame sheet. Return the requested JSON only. '
        'You see sampled frames, not continuous playback. Treat user-reported behavior as evidence and distinguish it from your own observations. '
        'Source cut candidates are measurements, not instructions to preserve cuts. The user intent overrides old storyboard and generic preservation rules. '
        'If the user wants fewer/no cuts, better continuity in a cut-heavy scene, or a single continuous view, choose entire-scene and single-shot. '
        'Prefer reuse-shot when an existing continuous section already shows the desired quiet behavior and spans at least half the target duration. '
        'reuse-shot extracts that source section and slows it to fill the whole scene, without changing the soundtrack, adding a freeze, looping, or generating new action. '
        'Set sourceStartSeconds/sourceEndSeconds to that clean section, staying inside measured cut boundaries. Use a small safety margin before an unwanted cut. '
        'Only reuse for silent, restrained scenes where slower motion is appropriate. Never use it to repair visible singing, fast action, beat-specific gestures, or defects throughout the section. '
        'If no suitable continuous section exists, choose frame-regenerate. For other methods set sourceStartSeconds/sourceEndSeconds to zero. '
        'Do not feed an unwanted montage back as a video reference. Choose one actual provided anchorFrame showing a coherent useful setting and clean pose. '
        'If the user wants a person to stop singing/talking/mouthing, use silent; do not replace or change the original soundtrack. '
        'For a quiet non-performance closing shot, favor a still posture, relaxed closed lips, a restrained camera, and very little facial activity. '
        'An available rear or three-quarter-rear view can avoid distracting mouth motion when that fits the scene; do not invent a different person or setting. '
        'The anchor must come from the displayed source frames. Do not preserve a defective sequence of shots. '
        'Use source-edit only for an appearance/detail edit that should retain the actual source shot sequence and motion. '
        'Use interval only when the note identifies a limited interval and the remainder should be preserved. Times are relative to this scene. '
        'Write action in 60–100 English words as a concrete positive visual brief for H3, in chronological order, describing what the viewer should see, not a complaint about the old result. Keep continuity to 25–50 words. '
        'For single-shot, explicitly describe one continuous camera setup and one simple action; omit unwanted cut timestamps and references to the old montage. '
        'Do not invent dialogue, lyrics, people, props, motion or a new story. Avoid over-specifying a face when it is not visible. '
        'Use needsClarification only for a material unresolved contradiction, not routine creative choices. Explain your strategy briefly in plain language. '
        'SUPPLIED CREATIVE DATA:\n'+json.dumps(supplied,ensure_ascii=False))
    items,model=await reviews.account.turn(prompt,RepairPlan.model_json_schema(),reference_images=[sheet])
    response=next(i['text'] for i in reversed(items) if i.get('type')=='agentMessage')
    plan=normalize_plan(RepairPlan.model_validate_json(response).model_dump(),data,evidence['frames'])
    plan.update(model=model,visualEvidence=evidence,sourceTakeId=data['baseTake']['id'])
    write(work/'smart-plan.json',plan)
    resolved=resolve_input(data,plan);write(planned,resolved)
    write(work/'context-brief.json',{'provider':'openai-vision-planner','model':model,
          'brief':{'singleAction':plan['action'],'objectContinuity':plan['continuity']}})
    # The snapshot remains immutable; the reviewable plan is separate metadata.
    with reviews.lock:
        film=reviews.load(film_id);scene=reviews.scene(film,shot['index'])
        take=next(t for t in scene['takes'] if t['id']==job_id)
        take['smartPlan']=plan;reviews.save(film)
    return resolved


def detected_cuts(source):
    result=subprocess.run(['ffmpeg','-hide_banner','-i',str(source),'-vf',"select='gt(scene,0.24)',showinfo",'-an','-f','null','-'],capture_output=True,text=True,check=True,timeout=120)
    import re
    return [float(t) for t in re.findall(r'pts_time:([0-9.]+)',result.stderr)]


async def review_repair(reviews,film_id,job_id,work,data):
    checks=read(work/'checks.json')
    if checks.get('aiReview'):return
    reviews.update_job(film_id,job_id,'running','Checking the new shot against your intent')
    shot=data['shot'];count=shot['endFrame']-shot['startFrame'];fps=data['plan']['fps'];plan=data['smartPlan']
    try:
        cuts=await asyncio.to_thread(detected_cuts,work/'background.mp4')
        checks['possibleInternalCuts']=cuts
        evidence,sheet=await asyncio.to_thread(inspection_sheet,work/'background.mp4',work/'review-frames',count,fps,cuts,'New candidate')
        prompt=('Review this candidate against the supplied repair intent. The first sheet is the source and the second is the candidate. '
            'They are timestamped samples, not continuous video. Report only visible evidence; do not claim perfect lip sync, a silent mouth throughout, or a flawless motion sequence. '
            'Assess shot consistency, visible people/clothing, gross object changes, and whether sampled facial poses suggest talking when silence was requested. '
            'Use uncertain/not-assessable when the face is too small or frames cannot settle the issue. '
            'A single-shot request with measured interior cuts is needs-review. Be concise and specific; do not claim the requested change succeeded just because it was requested. '
            +json.dumps({'intent':plan['intent'],'action':plan['action'],'speechPolicy':plan['speechPolicy'],
                        'cutPolicy':plan['cutPolicy'],'repairRange':plan['repairRange'],'fps':fps,'measuredCutCandidates':cuts},ensure_ascii=False))
        items,model=await reviews.account.turn(prompt,VisualReview.model_json_schema(),reference_images=[work/'inspection/sheet.jpg',sheet])
        text=next(i['text'] for i in reversed(items) if i.get('type')=='agentMessage')
        review=VisualReview.model_validate_json(text).model_dump()
        region=plan['repairRange'];inside=[t for t in cuts if region['startFrame']/fps+.08<t<region['endFrame']/fps-.08]
        if plan['cutPolicy']=='single-shot' and inside:
            review['result']='needs-review'
            review['findings'].insert(0,'Unwanted cut candidates remain at '+', '.join(f'{t:.2f}s' for t in inside))
        if plan['speechPolicy']=='silent' and review['mouth']=='possible-mouthing':
            review['result']='needs-review'
        elif plan['speechPolicy']=='silent' and review['mouth']=='not-assessable' and review['result']=='no-obvious-issue':
            review['result']='uncertain'
        review.update(model=model,coverage='Sampled frames plus measured cut detection; full playback is still required.')
    except Exception as error:
        review={'result':'uncertain','summary':'Automatic visual review was unavailable. The candidate is retained for playback review.',
                'findings':[str(error)[:350]],'mouth':'not-assessable'}
    checks['aiReview']=review;write(work/'checks.json',checks)
