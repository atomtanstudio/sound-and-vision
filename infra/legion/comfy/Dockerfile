# sv-comfy: Sound / Vision's own ComfyUI, built from public sources.
#
# This rebuilds the image Legion runs as sv-comfy:0.39-c9d8a6e (sha256:6cd2bfc0…, read on 2026-10-10 from its docker
# history, its build files and the running container): ComfyUI 0.39 at core c9d8a6e on CUDA 13.2 with cuDNN 9.20
# (Ubuntu 24.04, Python 3.12), Torch 2.11 + cu130, SageAttention 2.2 compiled for the GPU, and every Python package at
# the version that image has (requirements.lock.txt). That image grew in place from a lab image over several rebuilds;
# this makes the same result in one pass. The node packs the H3 routes need (node_packs.txt, with the lab's KJNodes
# fixes from patches/) and our own sv_nodes are checked out under /opt/ComfyUI/custom_nodes. ComfyUI runs with
# --base-directory on the profile, so setup.sh copies them from here into the profile's custom_nodes.
#
#   docker build -t sv-comfy:0.39-c9d8a6e infra/legion/comfy                     (setup.sh does this)
#   docker build --build-arg TORCH_CUDA_ARCH_LIST="8.9" …                         for another GPU (see below)
#
# TORCH_CUDA_ARCH_LIST is the GPU generation SageAttention's kernels are compiled for, "major.minor": 12.0 for RTX 50xx
# (Legion's 5090), 8.9 for RTX 40xx, 8.6 for RTX 30xx, 8.0 for A100, 9.0 for H100; several with ";". The host's NVIDIA
# driver must support CUDA 13.2 (nvidia-smi shows "CUDA Version: 13.2" or higher). The build needs no GPU; give it
# 50 GB of free disk and an hour or so, most of it compiling SageAttention (MAX_JOBS parallel nvcc jobs).
FROM --platform=linux/amd64 nvidia/cuda:13.2.1-cudnn-devel-ubuntu24.04@sha256:6435dc5a825b0095648d87a3c91240fd7788a85fafaf215739544d389ab74366

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TORCH_CUDA_ARCH_LIST=12.0
ARG MAX_JOBS=8
ARG PYTORCH_VERSION=2.11.0+cu130
ARG TORCHVISION_VERSION=0.26.0+cu130
ARG TORCHAUDIO_VERSION=2.11.0+cu130
ARG SAGEATTENTION_REF=eb615cf6cf4d221338033340ee2de1c37fbdba4a
ARG COMFYUI_REF=c9d8a6e69c4b5ab7fa0f789e7b988c172cd31fc9

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/comfy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST} \
    MAX_JOBS=${MAX_JOBS} \
    EXT_PARALLEL=4 \
    NVCC_APPEND_FLAGS="--threads 8"

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake curl ffmpeg git libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
      ninja-build pkg-config python-is-python3 python3 python3-dev python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/venv /opt/ComfyUI /home/comfy \
 && chown 1000:1000 /opt/venv /opt/ComfyUI /home/comfy

# Everything below is installed as the user ComfyUI runs as (uid/gid 1000, as on Legion), so it owns its venv and tree.
USER 1000:1000

RUN python3 -m venv /opt/venv \
 && python -m pip install pip==26.2.1 setuptools==78.1.0 wheel==0.47.0 packaging==26.3 ninja==1.13.0 cmake==4.4.2

RUN python -m pip install --index-url https://download.pytorch.org/whl/cu130 \
      "torch==${PYTORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}"

RUN python -m pip install --no-build-isolation --no-deps \
      "git+https://github.com/thu-ml/SageAttention.git@${SAGEATTENTION_REF}"

# The rest of the Python packages, exactly (--no-deps: the list is complete, pip resolves nothing), then a check that
# every installed package's requirements are met, as they are on Legion.
COPY requirements.lock.txt /opt/sv-comfy/requirements.lock.txt
RUN python -m pip install --no-deps -r /opt/sv-comfy/requirements.lock.txt \
 && python -m pip check \
 && python -c "import torch, torchvision, torchaudio, triton, sageattention; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'triton', triton.__version__)"

RUN git init -q /opt/ComfyUI \
 && git -C /opt/ComfyUI remote add origin https://github.com/Comfy-Org/ComfyUI.git \
 && git -C /opt/ComfyUI fetch -q --depth 1 origin "${COMFYUI_REF}" \
 && git -C /opt/ComfyUI checkout -q FETCH_HEAD

COPY node_packs.txt /opt/sv-comfy/node_packs.txt
COPY patches/ /opt/sv-comfy/patches/
RUN set -e; \
    while read -r name url ref patch; do \
      case "$name" in ''|'#'*) continue ;; esac; \
      d="/opt/ComfyUI/custom_nodes/$name"; \
      git init -q "$d"; \
      git -C "$d" remote add origin "$url"; \
      git -C "$d" fetch -q --depth 1 origin "$ref"; \
      git -C "$d" checkout -q FETCH_HEAD; \
      if [ -n "$patch" ]; then git -C "$d" apply "/opt/sv-comfy/patches/$patch"; fi; \
      echo "$name $(git -C "$d" rev-parse --short HEAD) ${patch}"; \
    done < /opt/sv-comfy/node_packs.txt
COPY --chown=1000:1000 custom_nodes/sv_nodes /opt/ComfyUI/custom_nodes/sv_nodes

WORKDIR /opt/ComfyUI
EXPOSE 8188
ENTRYPOINT ["/opt/venv/bin/python", "main.py"]
CMD ["--listen", "0.0.0.0", "--port", "8188"]
