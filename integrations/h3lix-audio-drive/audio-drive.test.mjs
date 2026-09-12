import test from 'node:test';
import assert from 'node:assert/strict';
import {buildEzTurboGraph,FUSED_TURBO_PROFILE} from './graphs.mjs';
import {normalizeGenerationRequest} from './jobs.mjs';
import {normalizeAudioDrive} from './audio-drive.mjs';
const assets=[{kind:'image',id:'picture-1',remotePath:'character.png'},{kind:'audio',id:'song',remotePath:'song.wav'}];
const request={mode:'Reference to Video',prompt:'Audio-driven regression fixture',duration:15,seed:42,ratio:'16:9',turbo:'On',steps:4,assets};

test('Audio Drive keeps the exact fused sampling chain and changes only audio conditioning and mux',()=>{
 const base=buildEzTurboGraph({...request,nativeAudio:'Off'},assets,'test');
 const result=buildEzTurboGraph({...request,audioDrive:'vrgdg-source'},assets,'test');
 const g=result.graph;
 assert.equal(g['127'].inputs.unet_name,FUSED_TURBO_PROFILE.model);
 assert.equal(result.steps,4);assert.equal(result.frames,362);
 assert.deepEqual(g['900'],base.graph['900']);assert.deepEqual(g['143'],base.graph['143']);
 assert.deepEqual(g['125'].inputs.latent_image,['audio-drive',0]);
 assert.deepEqual(g['131'].inputs['ref_audios.ref_audio_0'],['190',0]);
 assert.deepEqual(g['audio-drive'].inputs,{av_latent:['131',1],source_audio:['190',0],audio_vae:['120',0]});
 assert.deepEqual(g['130'].inputs.audio,['audio-drive',1]);assert.equal(g['121'],undefined);
 const restored=structuredClone(result);delete restored.audioDrive;delete restored.graph['audio-drive'];
 restored.graph['125'].inputs.latent_image=['131',1];delete restored.graph['130'].inputs.audio;
 assert.deepEqual(restored,base);
});
test('normalization pins Audio Drive to current four-step Turbo even with stale quality controls',()=>{
 const n=normalizeGenerationRequest({...request,audioDrive:'vrgdg-source',profile:'quality',steps:20,turbo:'Off',adult:'On'},request.mode);
 assert.equal(n.profile,'advanced');assert.equal(n.steps,4);assert.equal(n.turbo,'On');assert.equal(n.adult,'Off');
 assert.equal(n.generationModel,'current');assert.equal(n.audioDrive,'vrgdg-source');
});
test('incompatible models, missing or extra references, long scenes and added processing fail explicitly',()=>{
 for(const override of [{generationModel:'singularity-test'},{mode:'Frames to Video'},{assets:assets.slice(0,1)},
   {assets:[...assets,assets[0]]},{duration:16},{postProduction:{}},{audioDrive:'unknown'}])
  assert.throws(()=>normalizeAudioDrive({...request,audioDrive:'vrgdg-source',...override}));
 assert.throws(()=>buildEzTurboGraph({...request,audioDrive:'vrgdg-source'},assets,'bad',{steps:8}));
});
test('request with no Audio Drive flag remains untouched',()=>{
 assert.equal(normalizeAudioDrive(request),request);
 assert.equal(buildEzTurboGraph(request,assets,'test').graph['audio-drive'],undefined);
});
