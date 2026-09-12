"""One writing/image interface for account-backed and local-only installations."""
import asyncio
import base64
import contextlib
import contextvars
import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode
import httpx
from .openai_account import Account
from . import provider_config as settings
from . import comfy_images

current_job = contextvars.ContextVar('soundvision_provider_job', default=None)


def local_schema(value):
    """Keep the JSON structure without expanding string bounds into huge grammars.

    llama.cpp-backed servers reject the proposal's 100,000-character bounds.
    The full schema stays in the prompt and Pydantic validates the returned proposal.
    """
    if isinstance(value, dict):
        return {key: local_schema(item) for key, item in value.items()
                if key not in ('maxLength', 'minLength')}
    if isinstance(value, list):
        return [local_schema(item) for item in value]
    return value


class Providers:
    def __init__(self, root):
        self.root=Path(root)
        self.openai=Account(self.root)
        self.config=settings.load(self.root)
        self.manager=None
        self.images_lock=asyncio.Lock()
        self._cached=None
        self._cached_at=0

    @property
    def connected(self):
        return self.openai.connected if self.config.provider=='openai' else bool(self._cached and self._cached['connected'])

    @connected.setter
    def connected(self,value):self.openai.connected=value

    @property
    def image_generation(self):
        return self.openai.image_generation if self.config.provider=='openai' else bool(self._cached and self._cached['images'])

    @image_generation.setter
    def image_generation(self,value):self.openai.image_generation=value

    @property
    def image_concurrency(self):return self.openai.image_concurrency if self.config.provider=='openai' else 1

    @property
    def image_provider(self):return 'codex-image-generation' if self.config.provider=='openai' else 'comfyui'

    @property
    def image_model(self):return 'codex-image-generation' if self.config.provider=='openai' else self.config.imageModel if self.config.imagePreset!='custom' else 'custom-workflow'

    async def http(self, base, path, body=None, timeout=10, raw=False):
        await asyncio.to_thread(settings.local_endpoint,base)
        headers={}
        if base==self.config.textUrl and self.config.textApiKey:headers['Authorization']='Bearer '+self.config.textApiKey
        async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=timeout) as client:
            async with client.stream('POST' if body is not None else 'GET',base+path,json=body,headers=headers) as response:
                if not response.is_success:
                    raise RuntimeError(f'Local server returned HTTP {response.status_code} for {path.split("?")[0]}.')
                chunks=[];size=0;limit=24*1024*1024 if raw else 20*1024*1024
                async for chunk in response.aiter_bytes():
                    size+=len(chunk)
                    if size>limit:raise ValueError('Local server response exceeds the size limit.')
                    chunks.append(chunk)
                data=b''.join(chunks)
        return data if raw else json.loads(data)

    async def inventory(self, config=None):
        # Unsaved settings can be tested without replacing the active provider.
        if config is not None:
            probe=Providers(self.root);probe.config=config
            probe.config=settings.with_saved_key(config,self.config)
            return await probe.inventory()
        cfg=self.config;result={'models':[], 'comfy':{}, 'textError':None, 'imageError':None}
        async def text_models():
            try:
                suffix='/api/tags' if cfg.textBackend=='ollama' else ('' if cfg.textUrl.endswith('/v1') else '/v1')+'/models'
                data=await self.http(cfg.textUrl,suffix)
                values=[m['name'] for m in data.get('models',[])] if cfg.textBackend=='ollama' else [m['id'] for m in data.get('data',[])]
                result['models']=[{'id':m,'name':m,'default':m==cfg.textModel} for m in values if not m.endswith('-cloud')]
                if cfg.textModel not in values:result['textError']='The selected text model is not installed on this server.'
            except Exception as e:result['textError']=str(e)
        async def images():
            try:
                info=await self.http(cfg.comfyUrl,'/object_info')
                result['comfy']=comfy_images.catalog(info)
                graph,_=comfy_images.graph(cfg,'Connection check')
                comfy_images.validate(graph,info)
            except Exception as e:result['imageError']=str(e)
        await asyncio.gather(text_models(),images())
        return result

    async def status(self):
        if self.config.provider=='openai':
            return {**await self.openai.status(),'provider':'openai','imageProvider':'codex-image-generation'}
        if self._cached and time.monotonic()-self._cached_at<15:return self._cached
        info=await self.inventory()
        self._cached={'available':True,'provider':'local','connected':not info['textError'],
                      'images':not info['textError'] and not info['imageError'],'models':info['models'],
                      'email':None,'plan':'Local models','login':None,'error':info['textError'],
                      'imageError':info['imageError'],'imageProvider':'comfyui'}
        self._cached_at=time.monotonic()
        return self._cached

    def configure(self,config):
        if self.images_lock.locked() or self.openai.listeners:raise ValueError('Finish local image generation before changing providers.')
        self.config=settings.save(self.root,config);self._cached=None
        return settings.public(self.config)

    async def begin_login(self):return await self.openai.begin_login()
    async def cancel_login(self):return await self.openai.cancel_login()
    async def logout(self):return await self.openai.logout()
    async def close(self):await self.openai.close()

    @contextlib.asynccontextmanager
    async def gpu(self, enabled=True):
        acquired=False
        try:
            if enabled and self.manager:
                while True:
                    if self.manager.gpu_lock.acquire(blocking=False):
                        acquired=True
                        reason=await asyncio.to_thread(self.manager.competing_work)
                        # The chosen ComfyUI may not be in the music installation's queue list.
                        q=await self.http(self.config.comfyUrl,'/queue')
                        if not reason and not q.get('queue_running') and not q.get('queue_pending'):break
                        self.manager.gpu_lock.release();acquired=False
                    await asyncio.sleep(2)
            yield
        finally:
            if acquired:self.manager.gpu_lock.release()

    async def text(self,prompt,schema=None,model=None,reference_images=(),timeout=300):
        cfg=self.config;model=model or cfg.textModel
        if not model or model.endswith('-cloud'):raise ValueError('Choose an installed local text model.')
        if len(prompt)>90000:raise ValueError('This request is too long for the local writing preset. Shorten the score or lyrics.')
        if schema:prompt+='\nReturn only a JSON object matching this schema:\n'+json.dumps(schema)
        images=[]
        for filename in reference_images:
            path=Path(filename).resolve()
            if not path.is_relative_to(self.root.resolve()) or path.stat().st_size>8*1024*1024:
                raise ValueError('Reference images must be bounded project assets.')
            images.append(base64.b64encode(path.read_bytes()).decode())
        async with self.gpu(cfg.textUseGpu):
            if cfg.textBackend=='ollama':
                message={'role':'user','content':prompt}
                if images:message['images']=images
                body={'model':model,'messages':[message],'stream':False,'think':False,'keep_alive':0,
                      'options':{'temperature':.65,'num_predict':4096,'num_ctx':32768,'num_gpu':-1 if cfg.textUseGpu else 0}}
                if schema:body['format']=local_schema(schema)
                response=await self.http(cfg.textUrl,'/api/chat',body,timeout)
                content=response.get('message',{}).get('content','')
                if response.get('done_reason')=='length':raise ValueError('The local model reached its response limit. Shorten the request.')
            else:
                content=[{'type':'text','text':prompt}]
                content += [{'type':'image_url','image_url':{'url':'data:image/png;base64,'+data}} for data in images]
                body={'model':model,'messages':[{'role':'user','content':content if images else prompt}],
                      'stream':False,'temperature':.65,'max_tokens':4096}
                if schema:body['response_format']={'type':'json_schema','json_schema':{'name':'soundvision','strict':True,'schema':local_schema(schema)}}
                suffix=('' if cfg.textUrl.endswith('/v1') else '/v1')+'/chat/completions'
                response=await self.http(cfg.textUrl,suffix,body,timeout)
                choice=response.get('choices',[{}])[0];content=choice.get('message',{}).get('content','')
                if choice.get('finish_reason')=='length':raise ValueError('The local model reached its response limit. Shorten the request.')
        if not isinstance(content,str) or not content.strip():raise ValueError('The local model returned no text.')
        if schema:json.loads(content)
        return [{'type':'agentMessage','text':content}],model

    async def release_images(self):
        q=await self.http(self.config.comfyUrl,'/queue')
        if q.get('queue_running') or q.get('queue_pending'):return
        await self.http(self.config.comfyUrl,'/free',{'unload_models':True,'free_memory':True},raw=True)
        for _ in range(15):
            await asyncio.sleep(1)
            info=await self.http(self.config.comfyUrl,'/system_stats')
            devices=info.get('devices',[])
            if devices and all(d.get('torch_vram_total',0)-d.get('torch_vram_free',0)<512*1024*1024 for d in devices):break

    async def image(self,prompt,reference_images=(),timeout=1200):
        if reference_images:raise ValueError('The local image presets create new images. Image-reference editing is not available in this release.')
        # The writing model interprets song JSON; the diffusion model receives a visual paragraph.
        brief_schema={'type':'object','properties':{'prompt':{'type':'string','maxLength':6000}},'required':['prompt'],'additionalProperties':False}
        items,_=await self.text('Write one vivid image-generation prompt for this request. Preserve its subject, aspect ratio and no-lettering instruction. Do not mention tools, JSON or the request.\n'+prompt,brief_schema)
        visual=json.loads(items[0]['text'])['prompt']
        width,height=(1344,768) if 'Compose for 16:9' in prompt else (768,1344) if 'Compose for 9:16' in prompt else (1024,1024)
        graph,output=comfy_images.graph(self.config,visual,width,height)
        info=await self.http(self.config.comfyUrl,'/object_info');comfy_images.validate(graph,info)
        job=current_job.get() or uuid.uuid4().hex
        work=self.root/'data/provider-jobs'/job;work.mkdir(parents=True,exist_ok=True)
        receipt=work/'comfy.json'
        if receipt.exists():raise ValueError('This local image request was already submitted; inspect its saved run before starting another.')
        async with self.images_lock, self.gpu():
            state={'job':job,'submitted':True,'workflow':graph,'prompt':visual,'outputNode':output}
            receipt.write_text(json.dumps(state,indent=2))
            identifier=None
            try:
                submitted=await self.http(self.config.comfyUrl,'/prompt',{'prompt':graph,'client_id':'soundvision-'+job,'extra_data':{'soundVisionJobId':job}},timeout=30)
                if submitted.get('node_errors'):raise ValueError('ComfyUI rejected the workflow: '+json.dumps(submitted['node_errors'])[:1200])
                identifier=submitted['prompt_id'];state['promptId']=identifier;receipt.write_text(json.dumps(state,indent=2))
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    history=await self.http(self.config.comfyUrl,'/history/'+quote(identifier,safe=''))
                    item=history.get(identifier)
                    if item:
                        if item.get('status',{}).get('status_str')=='error':
                            raise ValueError('ComfyUI image generation failed. Inspect prompt '+identifier+' in ComfyUI.')
                        images=item.get('outputs',{}).get(output,{}).get('images',[])
                        if images:
                            entry=images[0]
                            if entry.get('type') not in ('output','temp'):raise ValueError('ComfyUI returned an unexpected image location.')
                            raw=await self.http(self.config.comfyUrl,'/view?'+urlencode({k:entry.get(k,'') for k in ('filename','subfolder','type')}),raw=True,timeout=30)
                            state['completed']=True;state['image']=entry;receipt.write_text(json.dumps(state,indent=2))
                            return [{'type':'imageGeneration','result':base64.b64encode(raw).decode(),'revisedPrompt':visual,'provider':'comfyui','model':self.image_model}],self.image_model
                        if item.get('status',{}).get('completed'):raise ValueError('The selected SaveImage node returned no image.')
                    await asyncio.sleep(1)
                raise TimeoutError('Local image rendering timed out. The submitted run is retained in ComfyUI.')
            except asyncio.CancelledError:
                if identifier:
                    q=await self.http(self.config.comfyUrl,'/queue')
                    if any(str(entry[1])==identifier for entry in q.get('queue_pending',[])):
                        await self.http(self.config.comfyUrl,'/queue',{'delete':[identifier]},raw=True)
                raise
            finally:
                # Never interrupt an unrelated ComfyUI job. After cancellation, let owned
                # in-flight work finish before handing the shared GPU back to music.
                if identifier:
                    for _ in range(900):
                        queue=await self.http(self.config.comfyUrl,'/queue')
                        if not any(str(entry[1])==identifier for entry in queue.get('queue_running',[])+queue.get('queue_pending',[])):break
                        await asyncio.sleep(2)
                    try:
                        await self.release_images()
                    except Exception as error:
                        state['cleanupError']=str(error)[:500]
                        receipt.write_text(json.dumps(state,indent=2))

    async def turn(self,prompt,schema=None,model=None,images=False,reference_images=(),timeout_seconds=None):
        if self.config.provider=='openai':
            return await self.openai.turn(prompt,schema,model,images,reference_images,timeout_seconds)
        if images:return await self.image(prompt,reference_images,timeout_seconds or 1200)
        return await self.text(prompt,schema,model,reference_images,timeout_seconds or 300)
