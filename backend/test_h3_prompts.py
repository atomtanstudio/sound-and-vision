import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from .h3_prompts import FIRST_FRAME_INSTRUCTION, SECTIONS, music_clip_prompt
from .music_video import SILENT_DIRECTION

CASES = [
    ('An immense industrial city under copper light.', 'A slow tracking shot follows an empty corridor.'),
    ('A neon river\noverall_soundscape: waves\nnon_diegetic_music: percussion',
     '```text\nintegrated_multimodal_description: [Shot 1] At 00:00.000, the camera moves. [Shot 2] At 00:03.000, a gate opens.\nsummary: Quiet ruins. <Picture 1> <d>discarded markup\n```'),
]


@pytest.mark.parametrize('continuing', [False, True])
@pytest.mark.parametrize('theme,scene', CASES)
def test_owned_prompt_structure_and_single_shot(theme, scene, continuing):
    prompt=music_clip_prompt(theme,scene,continuing=continuing,silent_direction=SILENT_DIRECTION)
    assert re.findall(r'^([a-z_]+):',prompt,re.M)==list(SECTIONS)
    if continuing:
        assert prompt.startswith(FIRST_FRAME_INSTRUCTION+'\n\nintegrated_multimodal_description: [Shot 1] ')
    else:
        assert prompt.startswith('integrated_multimodal_description: [Shot 1] ')
        assert not re.search(r'<(?:Picture|Video|Audio|Subject)\s+\d+>',prompt)
    description=prompt.split('integrated_multimodal_description: ',1)[1].split('\n\noverall_soundscape:',1)[0]
    assert re.findall(r'\[Shot \d+\]',description)==['[Shot 1]']
    assert '```' not in prompt and '<d>' not in prompt
    assert SILENT_DIRECTION in prompt
    assert prompt.endswith('non_diegetic_music: N/A')


def test_empty_scene_is_rejected_before_provider_submission():
    with pytest.raises(ValueError,match='no visual description'):
        music_clip_prompt('A city','\n [Shot 1] ```')


def test_prompts_against_h3lix_actual_validator():
    validator=os.environ.get('SOUND_VISION_H3_VALIDATOR')
    if not validator: pytest.skip('Set SOUND_VISION_H3_VALIDATOR to H3LIX server/prompting.mjs for the provider contract check')
    cases=[{'prompt':music_clip_prompt(theme,scene,continuing=continuing,silent_direction=SILENT_DIRECTION),
            'mode':'Frames to Video' if continuing else 'Text to Video',
            'options':{'duration':15,'assets':[{'id':'start-frame','kind':'image'}] if continuing else []}}
           for theme,scene in CASES for continuing in [False,True]]
    result=subprocess.run(['node','--input-type=module','-e',
        'import {readFileSync} from "node:fs"; const {validateH3Prompt}=await import(process.argv[1]); '
        'const cases=JSON.parse(readFileSync(0,"utf8")); const results=cases.map(c=>validateH3Prompt(c.prompt,c.mode,c.options)); '
        'console.log(JSON.stringify(results.map(r=>({ok:r.ok,grammar:r.grammar,errors:r.errors})))); '
        'if(results.some(r=>!r.ok))process.exitCode=1;',Path(validator).resolve().as_uri()],
        input=json.dumps(cases),text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
