"""One measured vocal contract shared by prompting, audio references and review."""
import math


def voice_contract(data):
    shot=data['shot'];duration=shot['end']-shot.get('start',0) if 'end' in shot else shot['generationSeconds']
    generated=shot['generationSeconds'];words=[]
    # Subtracting song timestamps can exceed an equal frame-derived duration by
    # a few floating-point bits. Accept that noise, never a genuinely short render.
    if (not all(math.isfinite(v) for v in (duration, generated)) or duration <= 0 or
        (duration > generated and not math.isclose(duration, generated, rel_tol=0, abs_tol=1e-9))):
        raise ValueError('Invalid scene duration; no scene was submitted.')
    duration = min(duration, generated)
    cast_aware = 'characterReferences' in shot
    vocalist = shot.get('vocalistId')
    if shot['type']=='performance' and (not cast_aware or vocalist):
        for word in data['timing']['words']:
            a,b=word['start'],word['end']
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (a,b)) or not 0<=a<b<=duration+.002:
                raise ValueError('Invalid measured vocal timing; no scene was submitted.')
            words.append({**word,'end':min(b,duration)})
    spans=[]
    for position,word in sorted(enumerate(words),key=lambda item:item[1]['start']):
        if spans and word['start']-spans[-1]['end'] <= .08:
            spans[-1]['end']=max(spans[-1]['end'],word['end']);spans[-1]['words'].append((position,word['text']))
        else:spans.append({'start':word['start'],'end':word['end'],'words':[(position,word['text'])]})
    # Adjacent aligned phrases may slightly overlap. Keep the lyric's authored
    # word order even when the timestamp of the next line starts early.
    for span in spans:span['words']=[text for _,text in sorted(span['words'])]
    rests=[];cursor=0
    for span in spans:
        if span['start']>cursor:rests.append({'start':cursor,'end':span['start']})
        cursor=span['end']
    if cursor<generated:rests.append({'start':cursor,'end':generated})
    subject = (next((i+1 for i,c in enumerate(shot.get('characterReferences',[])) if c['id']==vocalist), None)
               if cast_aware else 1)
    if words and subject is None:raise ValueError('The vocalist is missing from the scene cast.')
    locked = bool(words) and data.get('plan',{}).get('renderProfile')=='singularity-first-pass'
    return {'mode':'recorded-vocals' if words else 'silent','visibleDuration':duration,'generationDuration':generated,
            'vocalWindows':spans,'restWindows':rests,'words':words,'speaker':'S1' if words else None,
            'vocalistId':vocalist,'subjectNumber':subject,'gateVersion':3 if locked else 2,
            **({'timingAuthority':'recorded-audio','conditioningMode':'source-audio-locked',
                'wordTimingUse':'approximate-review-only'} if locked else {})}


def voice_direction(data):
    policy=voice_contract(data)
    cast=data['shot'].get('characterReferences')
    if policy['mode']=='silent':
        if cast == []:
            return 'This environment-only scene contains no visible characters or on-camera vocal event.'
        subjects='Every visible character' if cast is not None else '<Subject 1>'
        return (subjects+' is a quiet observer for this entire shot. Their upper and lower lips meet gently '
                'in a settled, closed line from the first frame through the last. Their jaw stays at rest; breathing is through the nose. '
                'The eyes and brows carry the expression while the body performs the stated action. '
                'Any other visible people are equally quiet. This scene contains physical action, with no on-camera vocal event.')
    language=data.get('plan',{}).get('language','en')
    language={'en':'English','es':'Spanish','fr':'French','de':'German','it':'Italian','pt':'Portuguese','zh':'Chinese','ja':'Japanese','ko':'Korean'}.get(language,language)
    events=[]
    subject=f"<Subject {policy['subjectNumber']}>"
    if policy.get('timingAuthority')=='recorded-audio':
        others=' '.join(f"<Subject {i+1}> keeps lips gently closed and jaw at rest throughout, including while the vocalist sings."
                        for i,c in enumerate(cast or []) if c['id'] != policy['vocalistId'])
        return (others+f' {subject} (S1) performs the actual recorded vocal in <Audio 1>. '
                'The continuous recording is the timing authority: match its audible syllables, held notes, breaths and natural pauses from clip time zero. '
                'Begin mouth articulation with the audible voice and let the lips settle during actual vocal rests. '
                'Follow the recorded pace throughout; do not invent, repeat, anticipate, omit or retime words. '
                'Keep the lips visible and the face unobscured while the body carries out the scene action.')
    for rest in policy['restWindows']:
        events.append((rest['start'],f"From {rest['start']:.3f} to {rest['end']:.3f} seconds, {subject} rests with lips gently together and jaw settled, breathing through the nose. Eyes, hands and instrument motion carry the energy; the jaw remains settled."))
    for span in policy['vocalWindows']:
        words=' '.join(span['words'])
        if words and words[-1] not in '.?!':words+='.'
        events.append((span['start'],f"From {span['start']:.3f} to {span['end']:.3f} seconds, {subject} (S1) follows the audible syllables in <Audio 1> and sings <d>[{language}] {words}</d> Their lips then return to rest."))
    others=' '.join(f"<Subject {i+1}> keeps lips gently closed and jaw at rest for the entire shot, including while the vocalist sings. Their own instrument or physical action supplies their performance."
                    for i,c in enumerate(cast or []) if c['id'] != policy['vocalistId'])
    return (others+' The recorded voice in <Audio 1> is the sole cue for visible singing by '+subject+'. Mouth articulation starts with its first audible syllable, '
            'follows its pace, and ends with its final syllable in each window. The body retains the shot action during the pauses. '
            +' '.join(text for _,text in sorted(events)))
