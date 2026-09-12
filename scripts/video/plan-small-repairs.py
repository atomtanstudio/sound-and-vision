"""Create a continuous, beat-cut narrative/performance edit from measured audio."""
from pathlib import Path
import json,math
root=Path(__file__).resolve().parents[2]
p=root/'deliveries/two-films-20260910/small-repairs'
analysis=json.loads((p/'analysis.json').read_text())
alignment=json.loads((p/'alignment-sections.json').read_text())
pilot=json.loads((p/'pilot-plan.json').read_text())
server='/srv/ai/sound-vision/data/films/two-films-20260910/small-repairs'
raw=[0,8.5,19,27,37.5,46.5,55.2916666667,64.7916666667,75.5,81,89,99.5,109,116.25,125.75,136,141.5,150.5,160.75,170.25,180,191.5]
frames=[0]
for i,t in enumerate(raw[1:],1):
 if i in (6,7): f=round(t*24)
 else:f=round(min(analysis['beats'],key=lambda b:abs(b-t))*24)
 frames.append(f)
frames.append(math.ceil(analysis['duration']*24))
scenes=[
('The morning round','street','narrative','A wide establishing view of the quiet terraced street. The repairman slowly wheels the old steel bicycle toward the workshop door, moving only a few natural steps. Low tracking camera, warm reflections in last night\'s puddles, a few leaves move softly; preserve the actual neighborhood and recognizable man from the reference.'),
('The workbench','singer-workshop','narrative','Medium-wide view in the workshop. The repairman sets the bicycle on its work stand and carefully turns the front wheel with one hand. The camera moves slowly sideways past hanging tools. An ordinary beginning to a working day, simple credible mechanics and restrained movement.'),
('A pocket full of change','singer-workshop','performance','Chest-up performance at the workshop window; calm direct eye contact, slightly rueful smile. A slow subtle push in, his whole face visible.'),
('Room at the bench','singer-workshop','narrative','A close documentary detail of the repairman\'s hands setting a small spanner beside a jar of spare nuts, then pulling an empty wooden chair toward the bench. The camera begins at the hands and settles on the empty chair. The tobacco jacket cuff, scuffed wood and real warm sunlight remain consistent.'),
('Make a space','singer-workshop','performance','A medium portrait from a very slightly lower camera angle, shoulders and both relaxed hands visible. He sings warmly beside the tool board with tiny natural head movements and no exaggerated acting.'),
('One wheel turning','singer-workshop','narrative','Close-up of a mechanically plausible steel bicycle wheel rotating slowly on a repair stand, the repairman\'s sleeve and steady hand at the outer edge. Fine spokes catch warm sunlight in moving lines. A gentle camera arc, tactile grease, steel and rubber, no impossible changes of the bicycle geometry.'),
('First chorus performance','singer-workshop','performance','pilot'),
('The missing screw','singer-workshop','narrative','The repairman and a young adult customer in a muted charcoal jacket share a quiet smile beside the repaired bicycle. The repairman hands over the handlebars gently; the customer tests the brake lever. Medium-wide warm workshop shot, understated believable gestures, no money exchange close-up and no readable signs.'),
('Between jobs','street','narrative','A broad street view from the workshop doorway as the repaired bicycle is gently wheeled away by its adult owner. The repairman remains by the door, watching with a slight satisfied smile. A calm lateral camera movement reveals brick walls and sunlit pavement; keep people at natural scale.'),
('The Sunday call','singer-workshop','performance','Close portrait with the warm workshop window softly reflected in his eyes, earnest and conversational singing. The camera holds still; no other person sings.'),
('Two cups','kitchen','narrative','Medium-wide kitchen scene with the two adult brothers from the reference. The repairman gently slides one coffee mug across the table toward his brother. They glance at each other and exchange a tentative smile. Keep both identities, the little dismantled clock and chipped tabletop stable, no lip movement suggesting they sing the soundtrack.'),
('Time and half a pot','singer-workshop','performance','A quiet medium-close workshop performance, his shoulders relaxed and expression soft. His head turns only a few degrees back toward camera, keeping the lips clearly visible throughout.'),
('Listening','kitchen','narrative','The two brothers sit across the kitchen table in a thoughtful pause. The man in the navy shirt slowly turns a small clock gear between finger and thumb, then sets it down. The repairman listens with a slight nod. Gentle push toward the space between the two mugs, natural hands, restrained real human timing.'),
('Second chorus','singer-workshop','performance','A slightly wider chest-up workshop performance with warm direct eye contact and more open expressive singing on the chorus, still physically restrained. Soft moving daylight across the wall, stable tools, no microphone.'),
('All the parts','kitchen','narrative','Close photographic view of both brothers\' hands arranging the little clock pieces on the folded cloth. One man steadies the case while the other places a single cog. The camera slowly pans from their hands to a coffee mug and back. The visible hands must remain anatomically plausible and the gears retain their shapes.'),
('Fresh air','canal','narrative','Wide view of the repairman beside the canal with the steel bicycle, the recognizable brick warehouses and bridge in the reference. He slowly turns his gaze from the water toward the path, one hand resting on the saddle. Tiny wind in leaves, warm reflections, slow graceful lateral camera move.'),
('Leave a little room','singer-workshop','performance','Intimate near-frontal close-up for the bridge, a thoughtful half-smile and a steady gentle gaze. The camera remains almost still; mouth and jaw follow the actual soft delivery, without unnecessary body movement.'),
('The walk back','street','narrative','A medium-wide street scene of the repairman walking slowly beside his brother in the navy shirt. They wheel the bicycle between them and share a brief understated smile. Warm late afternoon light, ordinary terraced houses, modest forward tracking at walking speed, no dramatic running or artificial slow motion.'),
('Final chorus','singer-workshop','performance','A confident warm chest-up workshop performance, expressive but natural singing directed just beside the lens, tiny hopeful smile, soft amber practical lamps. Maintain clear frontal face and gently approach with the camera.'),
('Room for both','kitchen','narrative','Medium-wide view across the little kitchen. The two brothers sit close enough to work together on the clock, the repairman carefully holds its case while his brother places the face. Quiet mutual concentration followed by a small smile, slow camera slide, natural light turning warmer.'),
('The evening round','canal','narrative','A calm wide golden-hour view of the canal bridge. The repairman slowly walks the repaired bicycle along the railing toward the right of frame, occasionally glancing at the water. The shot breathes with the guitar outro. Preserve the man\'s clothing and the old steel bicycle, long warm reflections and a gentle moving camera.'),
('The door stays open','street','narrative','Final composed wide view of the workshop frontage at dusk. The repairman stands inside the warmly lit open doorway, the repaired bicycle leaning securely nearby; his brother briefly appears beside him. The camera slowly retreats, leaving the open warm doorway in a generous darkening street composition suitable for a closing title. No written signs or generated titles. End naturally with steady light and a composed view, not a freeze frame.'),
]
shots=[]
for i,(name,ref,kind,action) in enumerate(scenes):
 start,end=frames[i]/24,frames[i+1]/24
 if i==6:
  shots.append(pilot['shots'][0]);continue
 seconds=math.ceil((end-start)*2)/2
 words=[w['text'] for q in alignment['cues'] for w in q['words'] if start<=w['start']<end]
 text=' '.join(words)
 performance=(f'<Subject 1> (S1) is visibly singing the original male lead vocal in <Audio 1>. Synchronize his lips, tongue and jaw to the exact recorded syllables and breaths, including the pauses. The excerpt contains: <d>[English] {text}</d> Preserve the reference performance\'s timing and melody; do not speak or sing these words at a new pace. During instrumental gaps his lips relax and close. His entire face remains clearly visible, with no microphone, hands or props covering his mouth. Minimal natural head motion, no broad gestures.' if kind=='performance' else 'The recorded song is audience-only accompaniment. The visible people do not sing, speak or mouth the lyrics; their lips stay relaxed. Let the physical actions follow the pace of the reference without turning them into choreographed dancing.')
 prompt=f'''subject_definitions:
<Subject 1> is the fictional repairman and singer shown in <Picture 1>: olive skin, short dark graying curls, slightly crooked nose, brown eyes, short salt-and-pepper beard, tobacco canvas chore jacket and cream henley.
<Picture 1> defines the exact character identity and the scene environment for this shot. The framing may change to match the shot description.
<Audio 1> is the exact excerpt from the finished original song Small Repairs, including its male lead vocal, live drums, guitars and organ.

summary:
[reference generation + audio reference] One continuous cinematic {kind} scene in a warm documentary roots-soul music video.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - preserve his exact face, age, beard, hair, wardrobe and believable body proportions.
<Picture 1>: fully_preserved - preserve the referenced location, material details, supporting people and warm natural film photography while using the camera framing specified below.
<Audio 1>: fully_copy - use the exact original audio timeline, with no replacement vocal, altered tempo, added lyrics or sound effects.

detailed_description:
The target video is a tactile photographic roots-rock and soul music video, with natural warm amber sunlight, muted olive shadows, fine 35mm grain and soft practical lights. [Shot 1] {action} {performance} Keep every object and person physically consistent throughout the entire {seconds}-second shot. Hands, tools, bicycle wheels, chairs and mugs must retain their natural shapes and plausible weight. Facial proportions, teeth, eyes and hair remain coherent; no morphing or synthetic beauty filter. Use restrained documentary camera movement at slow speed and small amplitude, with stable lens perspective and gentle shallow depth of field. Preserve the lived-in textures of the same small town and the recognizable identity of the main repairman. The environment should feel ordinary and specific rather than a staged luxury advertisement. Human behavior is understated and truthful. Keep the frame free of any text, signs that become readable, logos, subtitles, lyric typography or watermarks, since titles will be composited separately. Avoid internal cuts, speed ramps, frozen images, impossible camera jumps or decorative light flashes. Hold a continuous single photographic take for its full duration, ending with natural ongoing action and enough visual stability for a clean editorial cut.

overall_soundscape:
The supplied song is the complete soundtrack; add no dialogue, singing voices, foley or background noise.

non_diegetic_music:
The original instruments in <Audio 1> continue at their exact tempo. {'The lead voice belongs to the visible singer; do not replace it.' if kind=='performance' else 'The original male singing is heard as audience-only soundtrack while on-screen characters remain silent.'}'''
 shots.append({'index':i,'name':name,'type':kind,'start':start,'end':end,'startFrame':frames[i],'endFrame':frames[i+1],'generationSeconds':seconds,'runId':f'sv-small-repairs-scene-{i:02}-v1','references':[server+'/references/'+ref+'.png'],'prompt':prompt})
plan={**pilot,'shots':shots,'duration':analysis['duration'],'beatSource':'librosa tracking with measured low-frequency onset refinement','performanceSeconds':sum(s['end']-s['start'] for s in shots if s['type']=='performance')}
for a,b in zip(shots,shots[1:]):assert a['endFrame']==b['startFrame']
assert all(5<=s['endFrame']/24-s['startFrame']/24<=15 for s in shots)
(p/'film-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(len(shots),'shots;',round(plan['performanceSeconds'],2),'seconds performance;',frames[-1],'frames')
