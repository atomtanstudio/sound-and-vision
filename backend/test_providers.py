import asyncio
import base64
import json
import socket
import threading
import httpx
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from .api import create_app, Settings
from .provider_config import ProviderConfig, save, load, public, local_endpoint, model_paths, with_saved_key
from .providers import Providers, current_job, local_schema
from .comfy_images import graph, validate


def info():
    result={name:{'input':{'required':{}}} for name in ['CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage','ConditioningZeroOut']}
    for node,field,value in [('UNETLoader','unet_name','krea2_turbo_fp8_scaled.safetensors'),('CLIPLoader','clip_name','qwen3vl_4b_fp8_scaled.safetensors'),('VAELoader','vae_name','qwen_image_vae.safetensors'),('CheckpointLoaderSimple','ckpt_name','sdxl.safetensors')]:
        result[node]={'input':{'required':{field:[[value]]}}}
    return result


def test_private_config_and_model_folder_mapping(tmp_path):
    cfg=save(tmp_path,ProviderConfig(provider='local',textApiKey='private-value',modelRoot='D:\\AI models'))
    assert 'private-value' not in json.dumps(public(cfg))
    assert (tmp_path/'providers.json').stat().st_mode & 0o777 == 0o600
    save(tmp_path,ProviderConfig(provider='local',textModel='another'))
    assert load(tmp_path).textApiKey=='private-value'
    assert 'base_path: "D:\\\\AI models"' in model_paths(cfg)
    assert 'diffusion_models: diffusion_models' in model_paths(cfg)
    save(tmp_path,ProviderConfig(textApiKey=''));assert not load(tmp_path).textApiKey


@pytest.mark.parametrize('change',[
    {'textUrl':'http://127.0.0.1:11435'},
    {'textBackend':'compatible'},
    {'textUrl':'http://127.0.0.1:11434/another-base'},
])
def test_saved_key_is_bound_to_server_address_and_backend(tmp_path,change):
    previous=save(tmp_path,ProviderConfig(provider='local',textApiKey='dummy-old-key'))
    replacement=previous.model_copy(update={**change,'textApiKey':None})
    assert with_saved_key(replacement,previous).textApiKey is None
    assert save(tmp_path,replacement).textApiKey is None
    explicit=replacement.model_copy(update={'textApiKey':'dummy-new-key'})
    assert with_saved_key(explicit,previous).textApiKey=='dummy-new-key'


def test_probe_does_not_send_old_key_to_replacement_server(tmp_path,monkeypatch):
    previous=save(tmp_path,ProviderConfig(provider='local',textBackend='compatible',
        textUrl='http://127.0.0.1:1234/v1',textApiKey='dummy-old-key'))
    changed=previous.model_copy(update={'textBackend':'ollama','textUrl':'http://127.0.0.1:11434','textApiKey':None})
    seen=[]
    def respond(request):
        seen.append(request)
        return httpx.Response(200,json={'models':[{'name':'qwen3.5:4b'}]} if request.url.path=='/api/tags' else info())
    client=httpx.AsyncClient
    monkeypatch.setattr('backend.providers.httpx.AsyncClient',lambda **kwargs:client(transport=httpx.MockTransport(respond),**kwargs))
    asyncio.run(Providers(tmp_path).inventory(changed))
    target=next(request for request in seen if request.url.path=='/api/tags')
    assert 'authorization' not in target.headers
    assert load(tmp_path).textApiKey=='dummy-old-key' # Probe leaves saved settings intact.


def test_setup_writing_test_uses_endpoint_bound_key(tmp_path,monkeypatch):
    previous=save(tmp_path,ProviderConfig(provider='local',textApiKey='dummy-old-key'))
    config=Settings(tmp_path/'data',tmp_path/'model',tmp_path/'vae','x'*40)
    app=create_app(config,start_worker=False);service=app.state.assistance
    captured=[]
    async def write(body,account=None):
        captured.append(account.config.textApiKey)
        return {'proposal':{'style':'Test only'}}
    def submit(job_id,kind,payload,operation,serialized=True):
        # Retain operation for explicit execution after the HTTP request.
        captured.append(operation);return {'id':job_id,'state':'queued'}
    service.write=write;service.submit=submit
    body=previous.model_copy(update={'textUrl':'http://127.0.0.1:11435','textApiKey':None}).model_dump()
    with TestClient(app,headers={'Authorization':'Bearer '+config.token}) as c:
        response=c.post('/api/providers/tests',json={'requestId':'safe-provider-switch','kind':'writing','config':body})
        assert response.status_code==202
    asyncio.run(captured.pop()())
    assert captured==[None]


@pytest.mark.parametrize('address',['8.8.8.8','169.254.169.254','0.0.0.0','224.0.0.1'])
def test_local_mode_rejects_public_metadata_and_nonhost_addresses(monkeypatch,address):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',(address,80))])
    with pytest.raises(ValueError):local_endpoint('http://server:8080')


def test_krea_sdxl_and_custom_graphs_keep_explicit_inputs():
    cfg=ProviderConfig();g,out=graph(cfg,'new prompt',seed=42);validate(g,info())
    assert g['sample']['inputs']['steps']==8 and g['sample']['inputs']['cfg']==1
    assert g['prompt']['inputs']['text']=='new prompt' and out=='output'
    custom=ProviderConfig(imagePreset='custom',workflow=g,promptNode='prompt',outputNode='output')
    new,_=graph(custom,'different',seed=7)
    assert new['prompt']['inputs']['text']=='different' and g['prompt']['inputs']['text']=='new prompt'
    assert new['sample']['inputs']['seed']==7 and new['model']['inputs']==g['model']['inputs']
    sd,_=graph(ProviderConfig(imagePreset='sdxl',imageModel='sdxl.safetensors'),'portrait');validate(sd,info())
    assert sd['prompt']['inputs']['clip']==['model',1]
    with pytest.raises(ValueError,match='cannot find'):validate(graph(ProviderConfig(imageModel='absent'),'p')[0],info())
    with pytest.raises(ValueError):ProviderConfig(workflow={'nodes':[]})


def test_local_status_does_not_start_openai_and_reports_missing_models(tmp_path):
    async def run():
        p=Providers(tmp_path);p.config=ProviderConfig(provider='local')
        async def no_openai():pytest.fail('No OpenAI call is allowed in local mode')
        p.openai.status=no_openai
        async def http(base,path,*args,**kwargs):
            return {'models':[{'name':'qwen3.5:4b'}]} if path=='/api/tags' else info()
        p.http=http
        status=await p.status();assert status['connected'] and status['images'] and status['provider']=='local'
        p.config=p.config.model_copy(update={'imageModel':'missing'});p._cached=None
        status=await p.status();assert status['connected'] and not status['images'] and 'missing' in status['imageError']
    asyncio.run(run())


def test_ollama_schema_cpu_and_unload_options_and_compatible_protocol(tmp_path):
    async def run():
        p=Providers(tmp_path);p.config=ProviderConfig(provider='local');calls=[]
        async def http(base,path,body=None,*args,**kwargs):
            calls.append((path,body));return {'message':{'content':'{"result":"hello"}'},'done_reason':'stop'}
        p.http=http;schema={'type':'object','properties':{'result':{'type':'string'}}}
        result,model=await p.turn('Write',schema)
        body=calls[0][1];assert body['format']==schema and body['keep_alive']==0 and body['options']['num_gpu']==0
        assert body['think'] is False and json.loads(result[0]['text'])['result']=='hello'
        p.config=p.config.model_copy(update={'textBackend':'compatible','textUrl':'http://localhost:1234/v1'})
        async def compatible(base,path,body=None,*args,**kwargs):
            assert path=='/chat/completions' and body['response_format']['json_schema']['schema']==schema
            return {'choices':[{'message':{'content':'{"result":"ok"}'},'finish_reason':'stop'}]}
        p.http=compatible;assert (await p.turn('Write',schema))[1]==model
    asyncio.run(run())


def test_proposal_grammar_retains_structure_and_application_length_validation():
    from .assistance import Proposal
    from pydantic import ValidationError
    schema = Proposal.model_json_schema()
    portable = local_schema(schema)
    assert portable['required'] == schema['required']
    assert portable['properties']['ideas'] == schema['properties']['ideas']
    assert portable['$defs']['Idea']['additionalProperties'] is False
    assert 'maxLength' not in json.dumps(portable)
    assert schema['properties']['lyrics']['maxLength'] == 100000
    with pytest.raises(ValidationError):
        Proposal(title='x' * 201, lyrics='', style='', abc='', summary='', ideas=[])


def test_local_writing_requests_only_editable_fields_and_preserves_originals(tmp_path):
    from .assistance import Assistance, WritingInput
    async def run():
        service = Assistance(SimpleNamespace(root=tmp_path/'data'))
        service.account.config = ProviderConfig(provider='local')
        async def turn(prompt, schema, model):
            assert set(schema['properties']) == {'lyrics','summary'}
            assert 'exactly three' not in prompt and 'complete translated lyrics' in prompt
            return [{'type':'agentMessage','text':'{"lyrics":"Bonjour","summary":"Translated"}'}], 'local-model'
        service.account.turn = turn
        result = await service.write(WritingInput(requestId='local-translation-test',task='Translate lyrics',
            prompt='Translate to French',lyrics='Hello',title='Keep title',style='Keep style',abc='Keep score'))
        assert result['proposal'] == {'title':'Keep title','lyrics':'Bonjour','style':'Keep style',
            'abc':'Keep score','summary':'Translated','ideas':[]}
    asyncio.run(run())


def test_local_image_uses_owned_job_and_releases_shared_gpu(tmp_path,monkeypatch):
    async def run():
        p=Providers(tmp_path);p.config=ProviderConfig(provider='local')
        manager=SimpleNamespace(gpu_lock=threading.Lock(),competing_work=lambda:None);p.manager=manager;calls=[]
        async def text(*args,**kwargs):return [{'text':'{"prompt":"Original abstract cover"}'}],'text-model'
        p.text=text
        async def http(base,path,body=None,*args,**kwargs):
            calls.append((path,body))
            if path=='/object_info':return info()
            if path=='/queue':return {'queue_running':[],'queue_pending':[]}
            if path=='/prompt':
                assert manager.gpu_lock.locked();return {'prompt_id':'owned-test'}
            if path.startswith('/history'):return {'owned-test':{'outputs':{'output':{'images':[{'filename':'own.png','subfolder':'','type':'output'}]}},'status':{'completed':True}}}
            if path.startswith('/view'):return b'fixture bytes'
            if path=='/free':return b''
            if path=='/system_stats':return {'devices':[{'torch_vram_total':0,'torch_vram_free':0}]}
            pytest.fail(path)
        p.http=http
        async def sleep(_):pass
        monkeypatch.setattr('backend.providers.asyncio.sleep',sleep)
        token=current_job.set('provider-image-test')
        try:items,model=await p.image('Cover')
        finally:current_job.reset(token)
        assert base64.b64decode(items[0]['result'])==b'fixture bytes' and items[0]['provider']=='comfyui'
        assert model=='krea2_turbo_fp8_scaled.safetensors'
        assert not manager.gpu_lock.locked() and [path for path,_ in calls].count('/prompt')==1
        assert next(body for path,body in calls if path=='/free')=={'unload_models':True,'free_memory':True}
        assert json.loads((tmp_path/'data/provider-jobs/provider-image-test/comfy.json').read_text())['completed']
    asyncio.run(run())


def test_provider_routes_protect_secrets_and_music_video_release_gate(tmp_path,monkeypatch):
    monkeypatch.delenv('SOUND_VISION_ENABLE_MUSIC_VIDEO',raising=False)
    cfg=Settings(tmp_path/'data',tmp_path/'model',tmp_path/'vae','x'*40)
    app=create_app(cfg,start_worker=False)
    with TestClient(app,headers={'Authorization':'Bearer '+cfg.token}) as c:
        assert c.get('/api/providers',headers={'Authorization':'wrong'}).status_code==401
        assert c.post('/api/films',json={},headers={'Authorization':''}).status_code==401
        assert c.put('/api/providers',json={},headers={'Authorization':''}).status_code==401
        body=ProviderConfig(provider='local',textApiKey='private-key').model_dump()
        response=c.put('/api/providers',json=body);assert response.status_code==200
        assert 'private-key' not in response.text and 'private-key' not in c.get('/api/providers').text
        assert c.post('/api/films',json={}).status_code==409
        assert c.post('/api/films/saved/scenes/17/generate',json={}).status_code==409
        assert c.get('/api/health').json()['features']['musicVideo'] is False
