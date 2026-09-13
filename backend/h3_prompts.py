"""Application-owned H3 T2VA/I2VA syntax for silent, single-shot music-video clips."""
import re

FIRST_FRAME_INSTRUCTION = (
    'For the target video, at 0.00 seconds into the target video, '
    '<Picture 1> (from [Shot 1]) is fully referenced.'
)
SECTIONS = ('integrated_multimodal_description', 'overall_soundscape', 'non_diegetic_music')


def visual_prose(value):
    """The theme/storyboard is prose; it must not define provider fields or assets."""
    text = str(value).replace('```', '')
    text = re.sub(r'\[Shot\s+\d+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<(?:Picture|Video|Audio|Subject)\s+\d+>', 'the scene', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:d|scenetrans|cutoff)>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(?:at|from|starting|begin)\s+\d{2}:\d{2}(?:\.\d+)?\s*,?', 'at the opening', text, flags=re.IGNORECASE)
    fields = '|'.join((*SECTIONS, 'subject_definitions', 'summary', 'retention_analysis', 'detailed_description'))
    text = re.sub(r'\b(?:' + fields + r')\s*:', '', text, flags=re.IGNORECASE)
    return ' '.join(text.split())


def music_clip_prompt(theme, scene, *, continuing=False, silent_direction=''):
    """See the official base guide; I2VA adds the exact first-frame instruction."""
    scene, theme = visual_prose(scene), visual_prose(theme)
    if not scene:
        raise ValueError('The storyboard clip has no visual description. Prepare the video plan again.')
    anchor = (
        'Begin from <Picture 1>, preserving its visual style, subjects, composition, lighting and spatial relationships. '
        'Continue the action forward in one uninterrupted shot. '
        if continuing else 'Cinematic imagery in the requested visual style, in one continuous shot. '
    )
    body = (
        f'integrated_multimodal_description: [Shot 1] {anchor}{scene} '
        f'{silent_direction}Visual theme: {theme}\n\n'
        'overall_soundscape: Quiet environmental ambience only, with no speech or singing.\n\n'
        'non_diegetic_music: N/A'
    )
    return FIRST_FRAME_INSTRUCTION + '\n\n' + body if continuing else body
