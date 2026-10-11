# sv-analysis: Sound / Vision's listening worker (stems, word timing, Whisper, beats).
# A thin layer over sv-comfy's image so it shares the same Torch build for the 5090
# (2.11 + CUDA 13, torchaudio, transformers, CTranslate2, rotary-embedding-torch).
# Run one job per container (docker run --rm --gpus all ...), so it holds no VRAM
# while idle. Build sv-comfy first (comfy/setup.sh), then from the repo:
#   docker build -t sv-analysis:latest infra/legion/analysis
# (the app runs $SV_ANALYSIS_IMAGE, default sv-analysis:latest; BASE_IMAGE names another sv-comfy tag)
ARG BASE_IMAGE=sv-comfy:0.39-c9d8a6e
FROM ${BASE_IMAGE}

USER root
COPY constraints.txt /tmp/constraints.txt
RUN /opt/venv/bin/python -m pip install --no-cache-dir -c /tmp/constraints.txt \
        "audio-separator==0.47.*" "faster-whisper==1.2.*" "beat-this==1.1.*" pyloudnorm audioread \
    && /opt/venv/bin/python -c "from audio_separator.separator import Separator; import faster_whisper, beat_this.inference, librosa, torch; print('sv-analysis deps OK', torch.__version__)"
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["/opt/venv/bin/python"]
