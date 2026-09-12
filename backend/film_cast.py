"""Durable per-character sheets, scene casting and immutable render references."""
import base64
import copy
import hashlib
import io
import json
import time
from pathlib import Path

from fastapi import HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = 1
PROFILE = 'singularity-first-pass'


class Character(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,39}$')
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=160)
    appearance: str = Field(min_length=20, max_length=2000)


class Casting(BaseModel):
    model_config = ConfigDict(extra='forbid')
    castIds: list[str] = Field(max_length=8)
    vocalistId: str | None

    @model_validator(mode='after')
    def distinct(self):
        if len(self.castIds) != len(set(self.castIds)):
            raise ValueError('A character appears only once in the scene cast.')
        if self.vocalistId is not None and self.vocalistId not in self.castIds:
            raise ValueError('The visible vocalist must belong to this scene cast.')
        return self


class CastPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cast: list[Character] = Field(max_length=24)
    scenes: list[Casting]


CAST_RULES = (
    'Create a persistent cast registry for EVERY recognizable person, animal, creature or other recurring character. '
    'For a band, give each member a separate identity and instrument/role: vocalist, guitarist, bassist, drummer, etc. '
    'A singer in a story scene is the SAME character as that singer on stage. Fantasy creatures such as a dragon also need their own identity. '
    'Respect the requested cast; do not reduce a band or ensemble to one lead. Do not add incidental recognizable extras without an identity. '
    'Assign stable lowercase id slugs, distinct names, roles and precise appearance descriptions: species, apparent age, face shape, '
    'skin/scales, hair length and color, facial hair, silhouette, distinctive markings, clothing and owned instrument/props. '
    'Keep identities visibly distinct; hair length, beard, costume and instrument ownership are fixed for the entire film. '
    'Each scene must list only its visible castIds (up to eight; an environment-only scene uses []). '
    'Set vocalistId to ONE visible designated singer only when visible vocals are intended, otherwise null. '
    'Instrumental band members are physically performing their instruments, with resting closed mouths, even while the lead sings. '
    'Scene action and continuity describe physical action and camera ONLY, without singing, speech, lip-sync, lyrics or vocal timing. '
    'The renderer supplies vocal behavior from the recording separately. Use rear views or instrument/environment details for long rests. '
)


def validate_cast(cast, scenes):
    checked = CastPlan.model_validate({'cast': cast, 'scenes': [
        {k: s[k] for k in ('castIds', 'vocalistId')} for s in scenes]}).model_dump()
    ids = [c['id'] for c in checked['cast']]
    if len(ids) != len(set(ids)):
        raise ValueError('Every character needs a unique identity.')
    used = set()
    for scene in checked['scenes']:
        if not set(scene['castIds']).issubset(ids):
            raise ValueError('A scene references a character without a character sheet.')
        used.update(scene['castIds'])
    if used != set(ids):
        raise ValueError('The cast registry must match the characters actually used in the storyboard.')
    return checked['cast']


async def make_sheets(account, work, cast, phase, reference_images=()):
    """One account image per character; retain completed sheets across recovery."""
    from .film_review import read, write
    from .image_jobs import image_batch
    async def create_sheet(character):
        folder = work/'characters'/character['id']
        image_file = folder/'sheet.png'
        intent = folder/'intent.json'
        digest = hashlib.sha256(json.dumps(character, sort_keys=True).encode()).hexdigest()
        if image_file.exists():
            if not intent.exists() or read(intent).get('characterSha256') != digest:
                raise ValueError('A saved character sheet belongs to different casting instructions.')
        else:
            if intent.exists():
                raise RuntimeError(f"The image response for {character['name']} was interrupted. Completed sheets are retained; no duplicate image was requested.")
            prompt = (
                'Generate ONE production character sheet as a clean 2 by 2 grid on a plain neutral background. '
                'All four panels show the EXACT SAME single character, identical face/anatomy, age, hair, facial hair, markings and outfit. '
                'Upper left: clear front-facing head and shoulders. Upper right: left-facing profile head and shoulders. '
                'Lower left: right-facing profile head and shoulders. Lower right: full body including the complete outfit, silhouette, '
                'feet/tail/wings as applicable and their assigned instrument/prop. For nonhuman creatures use equivalent views of their anatomy. '
                'Use neutral closed lips or a resting closed jaw and relaxed eyes in EVERY view. Hair silhouette and facial hair are clearly visible. '
                'No action, dramatic expressions, text, labels, logos, scene montage or other characters. '
                'Any supplied prior reference establishes the existing identity of this named character; preserve it where visible. '
                'Creative character description: ' + json.dumps(character, ensure_ascii=False))
            write(folder/'prompt.json', {'prompt': prompt})
            write(intent, {'submittedAt': time.time(), 'characterSha256': digest})
            kwargs = {'reference_images': list(reference_images)} if reference_images else {}
            items, _ = await account.turn(prompt, images=True, **kwargs)
            images = [i['result'] for i in items if i.get('type') == 'imageGeneration' and i.get('result')]
            if len(images) != 1:
                raise RuntimeError(f"No usable character sheet returned for {character['name']}. Earlier sheets are retained.")
            encoded = images[0].split(',', 1)[1] if images[0].startswith('data:') else images[0]
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 24*1024*1024:
                raise ValueError('Character sheet exceeds the image size limit.')
            with Image.open(io.BytesIO(raw)) as img:
                if img.width*img.height > 20_000_000:
                    raise ValueError('Character sheet dimensions exceed the limit.')
                temporary = folder/'sheet.partial.png'
                img.convert('RGB').save(temporary, format='PNG')
                temporary.replace(image_file)
        return {**character, 'source': str(image_file),
                      'sha256': hashlib.sha256(image_file.read_bytes()).hexdigest(),
                      'views': ['front', 'left profile', 'right profile', 'full body']}
    return await image_batch(account,cast,create_sheet,phase,'Character sheets')


def attach(plan, scenes, cast, casting):
    validate_cast([{k: c[k] for k in ('id','name','role','appearance')} for c in cast], casting)
    by_id = {c['id']: c for c in cast}
    if len(plan['shots']) != len(scenes) or len(scenes) != len(casting):
        raise ValueError('Character assignments must cover every scene.')
    for shot, scene, assignment in zip(plan['shots'], scenes, casting):
        ids = assignment['castIds']
        vocalist = assignment['vocalistId'] if shot['type'] == 'performance' else None
        if not vocalist:
            shot['type'] = scene['type'] = 'narrative'
        refs = [copy.deepcopy(by_id[c]) for c in ids]
        shot.update(castIds=ids, vocalistId=vocalist, characterReferences=refs)
        shot['performanceIntent'] = bool(vocalist)
        if refs:
            shot['references'] = [r['source'] for r in refs]
            shot['referenceSha256'] = refs[0]['sha256']
        shot['referenceHashes'] = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in shot['references']]
        scene.update(castIds=ids, vocalistId=vocalist,
                     identityReferences=[{'source': r['source'], 'role': r['name']+' — '+r['role']} for r in refs[1:]])
    plan.update(cast=cast, characterSheetVersion=VERSION, renderProfile=PROFILE, vocalGateVersion=2)


def check_references(data):
    plan = data['plan']; shot = data['shot']
    if not plan.get('castRequired') and not plan.get('characterSheetVersion'):
        return
    if plan.get('characterSheetVersion') != VERSION:
        raise ValueError('Prepare every character sheet before rendering scenes.')
    expected = shot.get('referenceHashes', [])
    actual = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in shot.get('references', [])]
    if not actual or expected != actual:
        raise ValueError('A character reference is missing or changed. No scene was submitted.')
    refs = shot.get('characterReferences', [])
    if [r['id'] for r in refs] != shot.get('castIds', []):
        raise ValueError('Scene casting does not match its character references.')
    for r in refs:
        if hashlib.sha256(Path(r['source']).read_bytes()).hexdigest() != r['sha256']:
            raise ValueError('A saved character sheet changed. No scene was submitted.')
    if shot.get('vocalistId') and shot['vocalistId'] not in shot.get('castIds', []):
        raise ValueError('The vocalist is missing from the scene cast.')


def prompt_sections(data):
    """Picture order is the actual upload order; sheets never become extra people."""
    shot = data['shot']
    if 'characterReferences' not in shot:
        return None
    offset = 1 if data.get('frameAnchor') or shot.get('storyboardFrame') else 0
    definitions = []
    retention = []
    if shot.get('storyboardFrame') and not data.get('frameAnchor'):
        definitions.append('<Picture 1> is the original storyboard composition. Its setting and pose are context; the source video controls the current edit.')
        retention.append('<Picture 1>: weak_reference - original staging and visual style; preserve the current source video for an edit.')
    for number, c in enumerate(shot['characterReferences'], 1):
        definitions.append(f"<Subject {number}> is {c['name']}, {c['role']}, defined by <Picture {number+offset}>. {c['appearance']}")
        retention.append(f"<Subject {number}> (appears in [Shot 1]): fully_preserved - exact identity, species, facial geometry, hair length, beard, markings, wardrobe and owned instrument from Picture {number+offset}.")
    if not definitions:
        definitions.append('<Picture 1> supplies the visual style and setting for this environment-only scene. No visible characters.')
        if not data.get('frameAnchor'):
            retention.append('<Picture 1>: weak_reference - retain the visual medium, lighting and setting; no visible characters.')
    rules = ('Each character sheet shows multiple views of ONE identity, not multiple people. Render each assigned character exactly once. '
             'Do not reproduce the grid, reference background, alternate views or sheet layout. '
             'Keep every role attached to its own identity; never exchange the guitarist and bassist, hairstyles, facial hair, costumes or instruments. '
             'Only the listed scene cast is visible. ')
    return '\n'.join(definitions), '\n'.join(retention), rules


def review_sheet(data, work):
    """A bounded contact sheet lets the existing review compare every identity."""
    from PIL import ImageDraw, ImageOps
    refs = data['shot'].get('characterReferences', [])
    if not refs:return None
    columns = min(4, len(refs)); rows = (len(refs)+columns-1)//columns
    canvas = Image.new('RGB', (columns*512, rows*550), '#17171b')
    draw = ImageDraw.Draw(canvas)
    for i,c in enumerate(refs):
        x,y = (i%columns)*512,(i//columns)*550
        with Image.open(c['source']) as img:
            tile = ImageOps.contain(img.convert('RGB'), (512,512))
            canvas.paste(tile, (x,y+30))
        draw.text((x+6,y+8), f"Subject {i+1}: {c['name']} / {c['role']}", fill='white')
    target = work/'cast-review.jpg'
    canvas.save(target, quality=88)
    return target


def submit(reviews, film_id, body):
    from .film_review import ACTIVE, read, write
    with reviews.lock:
        film = reviews.load(film_id)
        old = next((j for j in film['jobs'] if j['id'] == body.requestId), None)
        if old:
            if old.get('operation') != 'character-sheets' or old['payload'] != body.model_dump():
                raise HTTPException(409, 'Request ID already belongs to another action.')
            return reviews.public(film)
        reviews.check_revision(film, body.revision)
        if any(j['state'] in ACTIVE for j in film['jobs']):
            raise HTTPException(409, 'Wait for current project jobs before preparing character sheets.')
        if not film['scenes']:
            raise HTTPException(409, 'Finish the storyboard first.')
        if film.get('characterSheetVersion') == VERSION:
            raise HTTPException(409, 'Character sheets are already prepared.')
        film['revision'] += 1
        write(reviews.folder(film_id)/'jobs'/body.requestId/'input.json', {
            'kind':'character-sheets', 'revision':film['revision'], 'plan':read(film['plan']),
            'scenes':film['scenes'], 'continuity':film['continuity']})
        film.setdefault('preparations', []).append({'id':body.requestId, 'state':'queued'})
        film['jobs'].append({'id':body.requestId, 'kind':'prepare', 'operation':'character-sheets',
                            'index':None, 'state':'queued', 'phase':'Queued for character sheets',
                            'payload':body.model_dump(), 'queuedAt':time.time_ns()})
        reviews.save(film); reviews.start(film_id, body.requestId)
        return reviews.public(reviews.load(film_id))


async def upgrade(reviews, film_id, job_id, work, data):
    from .film_review import read, write
    if not reviews.account:
        raise RuntimeError('Connect OpenAI to prepare character sheets.')
    phase = lambda text: reviews.update_job(film_id, job_id, 'running', text)
    plan = copy.deepcopy(data['plan']); scenes = copy.deepcopy(data['scenes'])
    file = work/'cast-plan.json'
    references = list(dict.fromkeys(p for s in plan['shots'] for p in s.get('references', [])))[:4]
    # Scoped prior identity images aid the cast planner; no videos are generated.
    if not file.exists():
        phase('Identifying the complete cast in the existing storyboard')
        prompt = (CAST_RULES+' Preserve existing identities visible in the supplied original references. '
                  'Return the cast and one casting assignment for each scene in the exact existing order. '
                  'Do not change the plot, scene count, timing or scene directions. Creative project data:\n'+json.dumps({
                      'direction':plan.get('direction',''), 'continuity':data['continuity'],
                      'scenes':[{k:s.get(k) for k in ('name','type','action','continuity')} for s in scenes]}, ensure_ascii=False))
        items, model = await reviews.account.turn(prompt, CastPlan.model_json_schema(), reference_images=references)
        text = next(i['text'] for i in reversed(items) if i.get('type') == 'agentMessage')
        board = CastPlan.model_validate_json(text).model_dump()
        validate_cast(board['cast'], board['scenes'])
        if len(board['scenes']) != len(scenes):
            raise ValueError('Casting changed the scene count; the existing film is preserved.')
        write(file, {**board, 'model':model})
    board = read(file)
    cast = await make_sheets(reviews.account, work, board['cast'], phase, references)
    attach(plan, scenes, cast, board['scenes'])
    with reviews.lock:
        film = reviews.load(film_id)
        if film.get('characterSheetVersion') == VERSION:
            return
        if film['revision'] != data['revision']:
            raise RuntimeError('Project notes changed during preparation. Sheets are retained; the existing film is preserved.')
        write(work/'previous-manifest.json', film); write(work/'previous-plan.json', read(film['plan']))
        plan['castRequired'] = True
        write(film['plan'], plan)
        film.update(scenes=scenes, cast=cast, characterSheetVersion=VERSION, renderProfile=PROFILE,
                    revision=film['revision']+1)
        reviews.save(film)
