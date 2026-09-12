// Opt-in adapter for the separately installed, unmodified VRGDG Audio Drive node.
// Ordinary H3LIX requests retain their existing graph and settings.
export const AUDIO_DRIVE = 'vrgdg-source';
export const VOCAL_DRIVE = 'vrgdg-vocal';

function validateVocalAssets(assets) {
  if (assets.filter(a=>a.kind==='image').length<1 || assets.filter(a=>a.kind==='audio').length!==1 ||
      assets.filter(a=>a.kind==='video').length>1 || assets.some(a=>!['image','audio','video'].includes(a.kind)))
    throw new Error('Locked vocals require character images, exactly one continuous vocal excerpt, and at most one source video.');
}

export function normalizeAudioDrive(request = {}) {
  if (request.audioDrive === undefined || request.audioDrive === null || request.audioDrive === 'Off') return request;
  if (![AUDIO_DRIVE,VOCAL_DRIVE].includes(request.audioDrive)) throw new Error('Unknown audio-drive mode.');
  if (request.mode !== 'Reference to Video') throw new Error('Audio Drive requires Reference to Video.');
  if (request.audioDrive === VOCAL_DRIVE) {
    if (request.generationModel !== 'singularity-first-pass') throw new Error('Locked vocals require Singularity first pass.');
    validateVocalAssets(request.assets || []);
    if (!Number.isFinite(Number(request.duration)) || Number(request.duration)<=0 || Number(request.duration)>362/24+1e-8)
      throw new Error('Locked vocal scenes must fit within 362 frames at 24 fps.');
    if (request.postProduction || request.communicationPlan) throw new Error('Locked vocals do not apply additional post-production.');
    return {...request,profile:'advanced',turbo:'On',steps:8,nativeAudio:'Off',ezRife:'Off',spectrum:'Off'};
  }
  if (request.generationModel && request.generationModel !== 'current') throw new Error('Audio Drive uses the current fused Turbo model, not Singularity.');
  const assets = request.assets || [];
  if (assets.length !== 2 || assets.filter(a => a.kind === 'image').length !== 1 || assets.filter(a => a.kind === 'audio').length !== 1)
    throw new Error('Audio Drive requires exactly one character image and one original song excerpt.');
  if (!Number.isFinite(Number(request.duration)) || Number(request.duration) <= 0 || Number(request.duration) > 362/24 + 1e-8)
    throw new Error('Audio Drive scenes must fit within 362 frames at 24 fps.');
  if (request.postProduction || request.communicationPlan) throw new Error('Audio Drive does not apply additional post-production.');
  return {...request, profile:'advanced', generationModel:'current', turbo:'On', steps:4,
    adult:'Off', realism:'Off', spectrum:'Off', ezRife:'Off', nativeAudio:'Off'};
}

export function attachAudioDrive(build, request, assets) {
  if (![AUDIO_DRIVE,VOCAL_DRIVE].includes(request.audioDrive)) return build;
  const graph = build.graph;
  const vocal=request.audioDrive === VOCAL_DRIVE;
  if (vocal) {
    validateVocalAssets(assets);
    if (build.profile !== 'singularity-first-pass' || build.steps !== 8 || build.frames>362 ||
        graph['160']?.class_type !== 'VHS_VideoCombine') throw new Error('Locked vocals require the eight-step Singularity first-pass graph.');
  } else {
  if (build.profile !== 'fused-turbo-h3' || build.steps !== 4 || build.frames > 362)
    throw new Error('Audio Drive requires the four-step fused Turbo graph.');
  if (assets.length !== 2 || assets.filter(a=>a.kind==='image').length!==1 || assets.filter(a=>a.kind==='audio').length!==1)
    throw new Error('Audio Drive reference inputs changed during preparation.');
  }
  if (graph['131']?.class_type !== 'MiniMaxH3ReferenceToVideo' || graph['190']?.class_type !== 'LoadAudio')
    throw new Error('Audio Drive conditioning graph is unavailable.');
  graph['audio-drive'] = {class_type:'VRGDG_MiniMaxH3AudioDrive',inputs:{
    av_latent:['131',1],source_audio:['190',0],audio_vae:['120',0],
  }};
  graph['125'].inputs.latent_image = ['audio-drive',0];
  // The same original waveform is used for reference, locked latent and mux.
  graph[vocal ? '160' : '130'].inputs.audio = ['audio-drive',1];
  delete graph['121'];
  return {...build,audioDrive:request.audioDrive};
}
