"""Private installation-level provider choices. No credentials are returned to the UI."""
import ipaddress
import json
import os
import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['openai', 'local'] = 'openai'
    textBackend: Literal['ollama', 'compatible'] = 'ollama'
    textUrl: str = 'http://127.0.0.1:11434'
    textModel: str = Field(default='qwen3.5:4b', max_length=200)
    textApiKey: str | None = Field(default=None, max_length=2000)
    textUseGpu: bool = False
    comfyUrl: str = 'http://127.0.0.1:8188'
    imagePreset: Literal['krea2', 'sdxl', 'custom'] = 'krea2'
    imageModel: str = Field(default='krea2_turbo_fp8_scaled.safetensors', max_length=500)
    textEncoder: str = Field(default='qwen3vl_4b_fp8_scaled.safetensors', max_length=500)
    vae: str = Field(default='qwen_image_vae.safetensors', max_length=500)
    modelRoot: str = Field(default='', max_length=2000)
    workflow: dict | None = None
    promptNode: str = Field(default='', max_length=100)
    promptInput: str = Field(default='text', max_length=100)
    outputNode: str = Field(default='', max_length=100)

    @field_validator('textUrl', 'comfyUrl')
    @classmethod
    def endpoint(cls, value):
        parsed = urlsplit(value.strip())
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Use an HTTP(S) server address without credentials, query or fragment.')
        return value.strip().rstrip('/')

    @field_validator('workflow')
    @classmethod
    def workflow_size(cls, value):
        if value is not None:
            if not value or len(value) > 250 or len(json.dumps(value)) > 750_000:
                raise ValueError('Use an API workflow with 1–250 nodes, under 750 KB.')
            if any(not isinstance(n,dict) or not isinstance(n.get('class_type'),str) or
                   not isinstance(n.get('inputs'),dict) for n in value.values()):
                raise ValueError('Export the workflow in ComfyUI API format, not the canvas format.')
        return value


def local_endpoint(url):
    """Local mode cannot silently send song data to a public cloud service."""
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if address.is_link_local or address.is_multicast or address.is_unspecified or not (address.is_private or address.is_loopback):
            raise ValueError('Local providers must use a loopback or private-network server address.')
    return url


def load(root):
    path = Path(root) / 'providers.json'
    return ProviderConfig.model_validate_json(path.read_text()) if path.exists() else ProviderConfig()


def public(config):
    result = config.model_dump(exclude={'textApiKey'})
    result['hasTextApiKey'] = bool(config.textApiKey)
    return result


def with_saved_key(config, previous):
    """An omitted credential may only reuse the same server's saved key."""
    if config.textApiKey is not None:
        return config
    same_server = (config.textUrl == previous.textUrl and
                   config.textBackend == previous.textBackend)
    return config.model_copy(update={'textApiKey': previous.textApiKey if same_server else None})


def save(root, config):
    path = Path(root) / 'providers.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    config = with_saved_key(config, load(root))
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd,'w') as handle:handle.write(config.model_dump_json(indent=2)+'\n')
    os.chmod(temporary,0o600)
    temporary.replace(path)
    return config


def model_paths(config):
    if not config.modelRoot.strip():return ''
    # JSON strings are YAML-compatible and keep Windows paths/newlines quoted.
    return ('soundvision:\n  base_path: '+json.dumps(config.modelRoot.strip())+'\n'
            '  diffusion_models: diffusion_models\n  checkpoints: checkpoints\n'
            '  text_encoders: text_encoders\n  vae: vae\n  loras: loras\n')
