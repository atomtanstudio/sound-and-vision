"""ComfyUI image graphs with an explicit output and user-selectable models."""
import copy
import secrets

MODEL_FIELDS = {'UNETLoader':'unet_name', 'CheckpointLoaderSimple':'ckpt_name',
                'CLIPLoader':'clip_name', 'VAELoader':'vae_name'}


def catalog(info):
    def choices(node, field):
        value=info.get(node,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
        return value if isinstance(value,list) else []
    return {'diffusionModels':choices('UNETLoader','unet_name'),
            'checkpoints':choices('CheckpointLoaderSimple','ckpt_name'),
            'textEncoders':choices('CLIPLoader','clip_name'), 'vaes':choices('VAELoader','vae_name')}


def graph(config, prompt, width=1024, height=1024, seed=None):
    seed = secrets.randbits(52) if seed is None else seed
    def node(kind, **inputs):return {'class_type':kind,'inputs':inputs}
    if config.imagePreset == 'custom':
        result=copy.deepcopy(config.workflow or {})
        if config.promptNode not in result or config.promptInput not in result[config.promptNode]['inputs']:
            raise ValueError('Choose the positive prompt node and input in your API workflow.')
        if not isinstance(result[config.promptNode]['inputs'][config.promptInput],str):
            raise ValueError('Choose a text input for the positive prompt, not a linked input.')
        if result.get(config.outputNode,{}).get('class_type') != 'SaveImage':
            raise ValueError('Choose a SaveImage output node in your API workflow.')
        result[config.promptNode]['inputs'][config.promptInput]=prompt
        for item in result.values():
            inputs=item['inputs'];kind=item['class_type']
            if kind in ('KSampler','KSamplerAdvanced'):inputs['seed' if kind=='KSampler' else 'noise_seed']=seed
            if kind=='RandomNoise':inputs['noise_seed']=seed
            if kind=='SaveImage':inputs['filename_prefix']='SoundVision/cover-'+str(seed)
        return result,config.outputNode
    result={
        'prompt':node('CLIPTextEncode',clip=['clip',0],text=prompt),
        'latent':node('EmptyLatentImage',width=width,height=height,batch_size=1),
        'sample':node('KSampler',model=['model',0],positive=['prompt',0],negative=['negative',0],
                      latent_image=['latent',0],seed=seed,steps=8,cfg=1.0,sampler_name='euler',scheduler='simple',denoise=1.0),
        'decode':node('VAEDecode',samples=['sample',0],vae=['vae',0]),
        'output':node('SaveImage',images=['decode',0],filename_prefix='SoundVision/cover-'+str(seed)),
    }
    if config.imagePreset=='krea2':
        result.update(model=node('UNETLoader',unet_name=config.imageModel,weight_dtype='default'),
                      clip=node('CLIPLoader',clip_name=config.textEncoder,type='krea2',device='default'),
                      vae=node('VAELoader',vae_name=config.vae),
                      negative=node('ConditioningZeroOut',conditioning=['prompt',0]))
    else:
        result['model']=node('CheckpointLoaderSimple',ckpt_name=config.imageModel)
        result['prompt']['inputs']['clip']=['model',1]
        result['negative']=node('CLIPTextEncode',clip=['model',1],text='text, watermark, logo, blurry')
        result['decode']['inputs']['vae']=['model',2]
        result['sample']['inputs'].update(steps=25,cfg=6.0,sampler_name='euler',scheduler='normal')
    return result,'output'


def validate(graph, info):
    missing=sorted({n['class_type'] for n in graph.values()}-set(info))
    if missing:raise ValueError('ComfyUI is missing workflow nodes: '+', '.join(missing))
    for node in graph.values():
        kind=node['class_type'];field=MODEL_FIELDS.get(kind)
        if field:
            choices=info[kind].get('input',{}).get('required',{}).get(field,[[]])[0]
            if isinstance(choices,list) and node['inputs'].get(field) not in choices:
                raise ValueError('ComfyUI cannot find '+str(node['inputs'].get(field))+'. Check its model folders and refresh the model list.')
