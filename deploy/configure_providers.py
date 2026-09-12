"""Configure an installation without putting credentials in shell arguments."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.provider_config import load, save, model_paths

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--provider',choices=['openai','local'],required=True)
p.add_argument('--text-backend',choices=['ollama','compatible'])
p.add_argument('--text-url')
p.add_argument('--text-model')
p.add_argument('--text-api-key-file',type=Path)
p.add_argument('--text-use-gpu',action=argparse.BooleanOptionalAction,default=None)
p.add_argument('--comfy-url')
p.add_argument('--image-preset',choices=['krea2','sdxl'])
p.add_argument('--image-model')
p.add_argument('--text-encoder')
p.add_argument('--vae')
p.add_argument('--model-root')
a=p.parse_args();values=vars(a).copy();root=values.pop('root').resolve();key=values.pop('text_api_key_file')
names={'text_backend':'textBackend','text_url':'textUrl','text_model':'textModel','text_use_gpu':'textUseGpu','comfy_url':'comfyUrl',
       'image_preset':'imagePreset','image_model':'imageModel','text_encoder':'textEncoder','model_root':'modelRoot'}
config=load(root).model_dump();config.update({names.get(k,k):v for k,v in values.items() if v is not None})
if key:config['textApiKey']=key.read_text().strip()
from backend.provider_config import ProviderConfig
cfg=save(root,ProviderConfig.model_validate(config))
if cfg.modelRoot:
    (root/'soundvision-model-paths.yaml').write_text(model_paths(cfg))
print('Provider settings saved privately. Restart Sound/Vision when idle, or configure through AI setup without a restart.')
