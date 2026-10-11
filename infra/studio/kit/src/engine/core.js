// Compositor core.
//
// A frame is built like a comp in After Effects: scenes stack layers (GLSL passes, 2D canvas layers,
// three.js scenes) into a ping-pong buffer in display-referred sRGB. Several sub-frames spread across the
// shutter interval are then averaged in linear light (true motion blur), and a finishing chain
// (lens distortion, chromatic aberration, bloom, grade, grain, vignette) runs once per output frame.
//
// Rendering is synchronous and a pure function of t. Anything that has to be loaded first (H3 plate frames, a scene's
// own pictures) is fetched by the async prepare(t) step, which the tools await before every frame they render.
import * as THREE from 'three';
import { VERT, COMMON } from './glsl.js';
import { hexToRgb } from './math.js';

export const DESIGN_W = 1920, DESIGN_H = 1080;

/** Song times of the sub-frames that make up the output frame centred on t (motion blur across the shutter). */
export function subTimes(t, nsub = 1, shutter = 0.5, fps = 60) {
  const out = [];
  for (let s = 0; s < nsub; s++) out.push(nsub === 1 ? t : t + ((s + 0.5) / nsub - 0.5) * (shutter / fps));
  return out;
}

// Animated radii pass through zero all the time (pops, irises); a hair below zero must not abort a 16,000-frame render.
{
  const P2 = CanvasRenderingContext2D.prototype, arc = P2.arc, ellipse = P2.ellipse;
  P2.arc = function (x, y, r, a0, a1, ccw) { return arc.call(this, x, y, r > 0 ? r : 0, a0, a1, ccw); };
  P2.ellipse = function (x, y, rx, ry, rot, a0, a1, ccw) { return ellipse.call(this, x, y, rx > 0 ? rx : 0, ry > 0 ? ry : 0, rot, a0, a1, ccw); };
}

export function fsMaterial(fragment, uniforms = {}, opts = {}) {
  return new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: COMMON + fragment,
    uniforms: { uRes: { value: new THREE.Vector2(DESIGN_W, DESIGN_H) }, uTime: { value: 0 }, tPrev: { value: null }, ...uniforms },
    depthTest: false, depthWrite: false, blending: THREE.NoBlending, ...opts,
  });
}

const BLEND = { over: 0, add: 1, screen: 2, multiply: 3, difference: 4, overlay: 5, invert: 6, mask: 7, behind: 8, lighten: 9, darken: 10, shadow: 11 };

const LAYER_FRAG = /* glsl */ `
uniform sampler2D tPrev;
uniform sampler2D tLayer;
uniform int uMode;
uniform float uOpacity;
uniform vec2 uOffset;
void main() {
  vec4 d = texture(tPrev, vUv);
  vec4 s = texture(tLayer, vUv + uOffset) * uOpacity;   // premultiplied
  vec3 sc = s.a > 0.0 ? s.rgb / s.a : vec3(0.0);        // straight colour
  vec3 o;
  if (uMode == 0) o = s.rgb + d.rgb * (1.0 - s.a);
  else if (uMode == 1) o = d.rgb + s.rgb;
  else if (uMode == 2) o = 1.0 - (1.0 - d.rgb) * (1.0 - s.rgb);
  else if (uMode == 3) o = d.rgb * mix(vec3(1.0), sc, s.a);
  else if (uMode == 4) o = abs(d.rgb - s.rgb);
  else if (uMode == 5) { vec3 ov = mix(2.0 * d.rgb * sc, 1.0 - 2.0 * (1.0 - d.rgb) * (1.0 - sc), step(0.5, d.rgb)); o = mix(d.rgb, ov, s.a); }
  else if (uMode == 6) o = mix(d.rgb, 1.0 - d.rgb, s.a);
  else if (uMode == 7) o = d.rgb * s.a;
  else if (uMode == 8) o = d.rgb + s.rgb * (1.0 - d.a);
  else if (uMode == 9) o = mix(d.rgb, max(d.rgb, sc), s.a);
  else if (uMode == 10) o = mix(d.rgb, min(d.rgb, sc), s.a);
  else o = d.rgb * (1.0 - s.a);
  gl_FragColor = vec4(o, max(d.a, s.a));
}`;

const THREE_FRAG = /* glsl */ `
uniform sampler2D tPrev;
uniform sampler2D tLayer;
uniform int uTone;
uniform float uExposure;
uniform float uOpacity;
uniform int uMode;
vec3 aces(vec3 x) { const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14; return sat((x * (a * x + b)) / (x * (c * x + d) + e)); }
vec3 neutral(vec3 c) {            // Khronos PBR Neutral — keeps saturated base colours honest
  const float startCompression = 0.8 - 0.04, desaturation = 0.15;
  float x = min(c.r, min(c.g, c.b));
  float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
  c -= offset;
  float peak = max(c.r, max(c.g, c.b));
  if (peak < startCompression) return c;
  float d = 1.0 - startCompression;
  float newPeak = 1.0 - d * d / (peak + d - startCompression);
  c *= newPeak / peak;
  float g = 1.0 - 1.0 / (desaturation * (peak - newPeak) + 1.0);
  return mix(c, vec3(newPeak), g);
}
void main() {
  vec4 d = texture(tPrev, vUv);
  vec4 s = texture(tLayer, vUv);
  float a = sat(s.a);
  vec3 c = a > 1e-4 ? s.rgb / a : s.rgb;
  c *= uExposure;
  if (uTone == 1) c = aces(c); else if (uTone == 2) c = neutral(c); else c = sat(c);
  c = toSRGB(c);
  a *= uOpacity;
  vec3 o = uMode == 1 ? d.rgb + c * a : c * a + d.rgb * (1.0 - a);
  gl_FragColor = vec4(o, max(d.a, a));
}`;

const COPY_FRAG = /* glsl */ `
uniform sampler2D tSrc;
void main() { gl_FragColor = texture(tSrc, vUv); }`;

const FILL_FRAG = /* glsl */ `
uniform vec4 uColor;
void main() { gl_FragColor = uColor; }`;

const ACCUM_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform float uWeight;
void main() { gl_FragColor = vec4(toLinear(sat(texture(tSrc, vUv).rgb)) * uWeight, uWeight); }`;

const BLUR_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform vec2 uDir;      // texel step * radius scale
void main() {
  // 9-tap gaussian evaluated with 5 bilinear fetches
  vec4 c = texture(tSrc, vUv) * 0.2270270270;
  c += (texture(tSrc, vUv + uDir * 1.3846153846) + texture(tSrc, vUv - uDir * 1.3846153846)) * 0.3162162162;
  c += (texture(tSrc, vUv + uDir * 3.2307692308) + texture(tSrc, vUv - uDir * 3.2307692308)) * 0.0702702703;
  gl_FragColor = c;
}`;

// ---- finishing chain ----
const LENS_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform vec2 uShake;      // uv offset
uniform float uRot;
uniform float uZoom;
uniform float uBarrel;    // + barrel / − pincushion
uniform float uCA;        // radial chromatic aberration
uniform vec2 uSplit;      // directional RGB split (uv)
uniform float uGlitch;    // 0..1 slice displacement
uniform float uSeed;
uniform float uPixel;     // mosaic size in px (0 = off)
uniform float uMirror;    // 0 none, 1 mirror-x, 2 quad, 3+ kaleidoscope segments
uniform float uWave;      // horizontal sine wobble amount (uv)
vec2 lens(vec2 uv, float k) {
  vec2 p = (uv - 0.5) * vec2(uRes.x / uRes.y, 1.0);
  p = rot(uRot) * p / uZoom;
  float r2 = dot(p, p);
  p *= 1.0 + k * r2;
  return p / vec2(uRes.x / uRes.y, 1.0) + 0.5 + uShake;
}
vec2 pre(vec2 uv) {
  if (uPixel > 0.5) { vec2 g = uRes / uPixel; uv = (floor(uv * g) + 0.5) / g; }
  if (uGlitch > 0.0) {
    float row = floor(uv.y * mix(6.0, 40.0, hash11(uSeed)));
    float h = hash12(vec2(row, uSeed));
    float on = step(1.0 - uGlitch * 0.7, h);
    uv.x += on * (hash12(vec2(row, uSeed + 3.1)) - 0.5) * 0.25 * uGlitch;
  }
  if (uWave != 0.0) uv.x += sin(uv.y * 38.0 + uTime * 9.0) * uWave;
  if (uMirror > 0.5) {
    vec2 p = (uv - 0.5) * vec2(uRes.x / uRes.y, 1.0);
    if (uMirror < 1.5) p.x = abs(p.x);
    else if (uMirror < 2.5) p = abs(p);
    else { float n = uMirror; float a = atan(p.y, p.x); float seg = TAU / n; a = abs(mod(a, seg) - seg * 0.5); p = length(p) * vec2(cos(a), sin(a)); }
    uv = p / vec2(uRes.x / uRes.y, 1.0) + 0.5;
  }
  return uv;
}
vec3 fetch(vec2 uv) {
  // mirror-repeat at the edges so shakes never reveal black borders
  uv = abs(mod(uv + 1.0, 2.0) - 1.0);
  return texture(tSrc, uv).rgb;
}
void main() {
  vec2 uv = pre(vUv);
  vec3 c;
  if (uCA == 0.0 && uSplit == vec2(0.0)) c = fetch(lens(uv, uBarrel));
  else {
    // spectral sampling: 7 taps along the dispersion for a smooth fringe
    vec3 acc = vec3(0.0), wsum = vec3(0.0);
    for (int i = 0; i < 7; i++) {
      float t = float(i) / 6.0;                    // 0 (red) .. 1 (blue)
      vec3 w = vec3(sat(1.0 - t * 2.0), 1.0 - abs(t * 2.0 - 1.0), sat(t * 2.0 - 1.0));
      vec2 u = lens(uv + uSplit * (t - 0.5), uBarrel + uCA * (t - 0.5));
      acc += fetch(u) * w; wsum += w;
    }
    c = acc / wsum;
  }
  gl_FragColor = vec4(c, 1.0);
}`;

const BLOOM_PRE_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform float uThreshold;
uniform float uKnee;
uniform vec2 uTexel;
vec3 pre(vec3 c) {
  float br = max(c.r, max(c.g, c.b));
  float soft = clamp(br - uThreshold + uKnee, 0.0, 2.0 * uKnee);
  soft = soft * soft / (4.0 * uKnee + 1e-4);
  return c * max(soft, br - uThreshold) / max(br, 1e-4);
}
void main() {
  vec3 c = vec3(0.0);
  c += pre(texture(tSrc, vUv + uTexel * vec2(-1, -1)).rgb);
  c += pre(texture(tSrc, vUv + uTexel * vec2(1, -1)).rgb);
  c += pre(texture(tSrc, vUv + uTexel * vec2(-1, 1)).rgb);
  c += pre(texture(tSrc, vUv + uTexel * vec2(1, 1)).rgb);
  gl_FragColor = vec4(c * 0.25, 1.0);
}`;
const BLOOM_DOWN_FRAG = /* glsl */ `
uniform sampler2D tSrc;
uniform vec2 uTexel;
void main() {
  // 13-tap downsample (Jimenez, "Next Generation Post Processing in Call of Duty: AW")
  vec3 a = texture(tSrc, vUv + uTexel * vec2(-2, 2)).rgb, b = texture(tSrc, vUv + uTexel * vec2(0, 2)).rgb, c = texture(tSrc, vUv + uTexel * vec2(2, 2)).rgb;
  vec3 d = texture(tSrc, vUv + uTexel * vec2(-2, 0)).rgb, e = texture(tSrc, vUv).rgb, f = texture(tSrc, vUv + uTexel * vec2(2, 0)).rgb;
  vec3 g = texture(tSrc, vUv + uTexel * vec2(-2, -2)).rgb, h = texture(tSrc, vUv + uTexel * vec2(0, -2)).rgb, i = texture(tSrc, vUv + uTexel * vec2(2, -2)).rgb;
  vec3 j = texture(tSrc, vUv + uTexel * vec2(-1, 1)).rgb, k = texture(tSrc, vUv + uTexel * vec2(1, 1)).rgb;
  vec3 l = texture(tSrc, vUv + uTexel * vec2(-1, -1)).rgb, m = texture(tSrc, vUv + uTexel * vec2(1, -1)).rgb;
  vec3 o = e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
  gl_FragColor = vec4(o, 1.0);
}`;
const BLOOM_UP_FRAG = /* glsl */ `
uniform sampler2D tSrc;     // lower mip (already accumulated)
uniform sampler2D tBase;    // this level's downsample
uniform vec2 uTexel;        // texel of lower mip
uniform float uSpread;
uniform float uWeight;
uniform float uBase;        // contribution of this level's own downsample
void main() {
  vec2 t = uTexel * uSpread;
  vec3 s = texture(tSrc, vUv + vec2(-t.x, t.y)).rgb + texture(tSrc, vUv + vec2(t.x, t.y)).rgb * 1.0
         + texture(tSrc, vUv + vec2(-t.x, -t.y)).rgb + texture(tSrc, vUv + vec2(t.x, -t.y)).rgb;
  s += (texture(tSrc, vUv + vec2(0, t.y)).rgb + texture(tSrc, vUv + vec2(0, -t.y)).rgb + texture(tSrc, vUv + vec2(t.x, 0)).rgb + texture(tSrc, vUv + vec2(-t.x, 0)).rgb) * 2.0;
  s += texture(tSrc, vUv).rgb * 4.0;
  gl_FragColor = vec4(texture(tBase, vUv).rgb * uBase + s / 16.0 * uWeight, 1.0);
}`;

const FINAL_FRAG = /* glsl */ `
uniform sampler2D tSrc;       // linear
uniform sampler2D tBloom;     // linear
uniform float uBloom;
uniform vec3 uBloomTint;
uniform float uGrain;
uniform float uVignette;
uniform float uVigSoft;
uniform float uFade;          // 0..1 to black
uniform float uFlash;         // additive flash
uniform vec3 uFlashColor;
uniform float uSaturation;
uniform float uContrast;
uniform vec3 uLift;
uniform vec3 uGain;
uniform float uInvert;
uniform float uLetterbox;     // target aspect (0 = off)
uniform float uScan;          // scanline strength
uniform float uHalftone;      // 0..1 mix of a print-dot screen
uniform float uPaper;         // 0..1 paper tooth (static mottling + fibres)
uniform float uFrame;
float softClip(float x) { const float a = 0.82; return x < a ? x : a + (1.0 - a) * tanh((x - a) / (1.0 - a)); }
void main() {
  vec3 c = texture(tSrc, vUv).rgb;
  c += texture(tBloom, vUv).rgb * uBloom * uBloomTint;
  c += uFlashColor * uFlash;
  c = vec3(softClip(c.r), softClip(c.g), softClip(c.b));
  c = toSRGB(c);
  // grade (display-referred)
  c = c * uGain + uLift * (1.0 - c);
  float l = luma(c);
  c = mix(vec3(l), c, uSaturation);
  c = (c - 0.5) * uContrast + 0.5;
  c = mix(c, 1.0 - c, uInvert);
  if (uHalftone > 0.0) {
    vec2 p = rot(0.45) * (vUv * uRes) / 7.0;
    float dotv = length(fract(p) - 0.5);
    float lv = luma(sat(c));
    float ht = smoothstep(0.02, -0.02, dotv - sqrt(1.0 - lv) * 0.62);
    c = mix(c, mix(c * 1.08, c * 0.55, ht), uHalftone);
  }
  if (uPaper > 0.0) {
    vec2 pp = vUv * vec2(uRes.x / uRes.y, 1.0);
    float mott = fbm(pp * 5.0) - 0.5;                                   // slow unevenness in the stock
    float fibre = vnoise(pp * vec2(260.0, 900.0)) * vnoise(pp * vec2(900.0, 240.0) + 7.0) - 0.25;
    c *= 1.0 + uPaper * (mott * 0.07 + fibre * 0.05);
  }
  if (uScan > 0.0) c *= 1.0 - uScan * (0.5 + 0.5 * sin(vUv.y * 1080.0 * PI));
  // vignette
  vec2 q = (vUv - 0.5) * vec2(uRes.x / uRes.y, 1.0);
  float v = smoothstep(uVigSoft, 1.25, length(q) * 1.15);
  c *= 1.0 - v * uVignette;
  // film grain: soft-edged, luminance-weighted, refreshed at 30 Hz (every other frame) so it reads as grain
  // rather than sensor noise — and so the encoder is not asked to spend its whole budget on it
  vec2 gp = vUv * uRes * (1080.0 / uRes.y);
  float gf = floor(uFrame * 0.5);
  float n = (vnoise(vec3(gp * 0.62, gf * 7.13)) - 0.5) * 1.6 + (hash13(vec3(floor(gp), gf)) - 0.5) * 0.5;
  float lg = luma(sat(c));
  c += n * uGrain * mix(0.55, 1.0, 1.0 - abs(lg * 2.0 - 1.0));
  c *= 1.0 - uFade;
  if (uLetterbox > 0.0) {
    float h = (uRes.x / uLetterbox) / uRes.y;
    float m = step(abs(vUv.y - 0.5), h * 0.5);
    c *= m;
  }
  // 1-LSB ordered dither against banding (static pattern: costs nothing to encode)
  c += (hash12(floor(vUv * uRes)) - 0.5) / 255.0;
  gl_FragColor = vec4(sat(c), 1.0);
}`;

export const POST_DEFAULTS = {
  bloom: 0.35, bloomThreshold: 0.72, bloomKnee: 0.25, bloomSpread: 1.0, bloomTint: [1.0, 0.92, 0.85],
  ca: 0.005, split: [0, 0], barrel: 0.0, shake: [0, 0], rot: 0, zoom: 1, glitch: 0, pixel: 0, mirror: 0, wave: 0,
  grain: 0.024, vignette: 0.28, vigSoft: 0.35, fade: 0, flash: 0, flashColor: [1, 1, 1],
  saturation: 1, contrast: 1, lift: [0, 0, 0], gain: [1, 1, 1], invert: 0, letterbox: 0, scan: 0, halftone: 0, paper: 0,
};

export class Engine {
  constructor(canvas, { width = 1920, height = 1080, song = null } = {}) {
    this.W = width; this.H = height;
    // design space: the short side is always 1080 units, so 16:9 is 1920×1080 and 9:16 is 1080×1920
    this.k = Math.min(width, height) / 1080;
    this.DW = width / this.k; this.DH = height / this.k;
    this.song = song;
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, depth: false, stencil: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' }));
    r.setPixelRatio(1);
    r.setSize(width, height, false);
    r.autoClear = false;
    r.outputColorSpace = THREE.SRGBColorSpace;
    this.gl = r.getContext();

    this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
    this.quad = new THREE.Mesh(geo, null);
    this.quad.frustumCulled = false;

    const rt = (w, h, o = {}) => new THREE.WebGLRenderTarget(w, h, {
      type: o.type ?? THREE.HalfFloatType, format: THREE.RGBAFormat, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
      depthBuffer: !!o.depth, stencilBuffer: false, samples: o.samples ?? 0, colorSpace: THREE.NoColorSpace, generateMipmaps: false,
    });
    this.makeRT = rt;
    this.comp = [rt(width, height), rt(width, height)];
    this.compIdx = 0;
    this.stack = [];
    this.rt3d = rt(width, height, { depth: true, samples: 4 });
    this.accum = rt(width, height, { type: THREE.FloatType });
    this.lensRT = rt(width, height);
    this.tmp = [];           // pooled full-res temps for layer copies
    this.tmpIdx = 0;
    this.blurRT = {};        // keyed by downscale
    this.bloomRT = [];
    let bw = width >> 1, bh = height >> 1;
    // six octaves of glow at 1080p; above that, extra octaves are added underneath so the footprint (as a fraction
    // of the frame) is the same at any output size
    this.bloomSkip = Math.max(0, Math.round(Math.log2(this.k)));
    for (let i = 0; i < 6 + this.bloomSkip; i++) { this.bloomRT.push({ down: rt(bw, bh), up: rt(bw, bh), w: bw, h: bh }); bw = Math.max(2, bw >> 1); bh = Math.max(2, bh >> 1); }

    // 2D layer canvas
    this.canvas2d = document.createElement('canvas');
    this.canvas2d.width = width; this.canvas2d.height = height;
    this.ctx = this.canvas2d.getContext('2d', { alpha: true });
    this.layerTex = new THREE.CanvasTexture(this.canvas2d);
    this.layerTex.colorSpace = THREE.NoColorSpace;
    this.layerTex.premultiplyAlpha = true;
    this.layerTex.generateMipmaps = false;
    this.layerTex.minFilter = THREE.LinearFilter; this.layerTex.magFilter = THREE.LinearFilter;

    this.mat = {
      layer: fsMaterial(LAYER_FRAG, { tLayer: { value: null }, uMode: { value: 0 }, uOpacity: { value: 1 }, uOffset: { value: new THREE.Vector2() } }),
      three: fsMaterial(THREE_FRAG, { tLayer: { value: null }, uTone: { value: 1 }, uExposure: { value: 1 }, uOpacity: { value: 1 }, uMode: { value: 0 } }),
      copy: fsMaterial(COPY_FRAG, { tSrc: { value: null } }),
      fill: fsMaterial(FILL_FRAG, { uColor: { value: new THREE.Vector4(0, 0, 0, 1) } }),
      accum: fsMaterial(ACCUM_FRAG, { tSrc: { value: null }, uWeight: { value: 1 } }, { blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, blendEquation: THREE.AddEquation, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor }),
      blur: fsMaterial(BLUR_FRAG, { tSrc: { value: null }, uDir: { value: new THREE.Vector2() } }),
      lens: fsMaterial(LENS_FRAG, { tSrc: { value: null }, uShake: { value: new THREE.Vector2() }, uRot: { value: 0 }, uZoom: { value: 1 }, uBarrel: { value: 0 }, uCA: { value: 0 }, uSplit: { value: new THREE.Vector2() }, uGlitch: { value: 0 }, uSeed: { value: 0 }, uPixel: { value: 0 }, uMirror: { value: 0 }, uWave: { value: 0 } }),
      bloomPre: fsMaterial(BLOOM_PRE_FRAG, { tSrc: { value: null }, uThreshold: { value: 0.8 }, uKnee: { value: 0.2 }, uTexel: { value: new THREE.Vector2() } }),
      bloomDown: fsMaterial(BLOOM_DOWN_FRAG, { tSrc: { value: null }, uTexel: { value: new THREE.Vector2() } }),
      bloomUp: fsMaterial(BLOOM_UP_FRAG, { tSrc: { value: null }, tBase: { value: null }, uTexel: { value: new THREE.Vector2() }, uSpread: { value: 1 }, uWeight: { value: 1 }, uBase: { value: 1 } }),
      final: fsMaterial(FINAL_FRAG, {
        tSrc: { value: null }, tBloom: { value: null }, uBloom: { value: 0 }, uBloomTint: { value: new THREE.Vector3(1, 1, 1) }, uGrain: { value: 0 }, uVignette: { value: 0 }, uVigSoft: { value: 0.35 },
        uFade: { value: 0 }, uFlash: { value: 0 }, uFlashColor: { value: new THREE.Vector3(1, 1, 1) }, uSaturation: { value: 1 }, uContrast: { value: 1 },
        uLift: { value: new THREE.Vector3() }, uGain: { value: new THREE.Vector3(1, 1, 1) }, uInvert: { value: 0 }, uLetterbox: { value: 0 }, uScan: { value: 0 }, uHalftone: { value: 0 }, uPaper: { value: 0 }, uFrame: { value: 0 },
      }),
    };
    for (const m of Object.values(this.mat)) m.uniforms.uRes.value.set(width, height);

    this.postParams = { ...POST_DEFAULTS };
    this.frame = new Frame(this);
    this.timeline = null;
    this.plates = null;      // engine/plates.js, set by main.js
    this.stats = { subframes: 0 };
  }

  /**
   * Load everything the frame centred on t needs (plate frames, a scene's prepare(times, engine) hook) before render().
   * Await it before every render that has to be exact; render() itself never waits for anything.
   */
  async prepare(t, { nsub = 1, shutter = 0.5, fps = 60 } = {}) {
    const times = subTimes(t, nsub, shutter, fps);
    const jobs = [];
    if (this.plates) jobs.push(this.plates.prepare(times));
    if (this.timeline && this.timeline.prepare) jobs.push(this.timeline.prepare(times, this));
    await Promise.all(jobs);
  }

  get cur() { return this.comp[this.compIdx]; }
  get other() { return this.comp[1 - this.compIdx]; }

  blit(material, target) {
    this.quad.material = material;
    this.renderer.setRenderTarget(target);
    this.renderer.render(this.quad, this.cam);
  }

  /** Run a full-screen pass that reads the current comp (tPrev) and replaces it. */
  pass(material, uniforms) {
    const u = material.uniforms;
    if (uniforms) for (const k in uniforms) { if (u[k]) u[k].value = uniforms[k]; else u[k] = { value: uniforms[k] }; }
    if (u.tPrev) u.tPrev.value = this.cur.texture;
    if (u.uRes) u.uRes.value.set(this.W, this.H);
    this.blit(material, this.other);
    this.compIdx = 1 - this.compIdx;
  }

  tempRT() {
    if (this.tmpIdx >= this.tmp.length) this.tmp.push(this.makeRT(this.W, this.H));
    return this.tmp[this.tmpIdx++];
  }

  /** Separable gaussian blur of any texture; returns a texture (valid until the next blur at same scale). */
  blur(tex, radiusPx, iterations = 2) {
    const r = radiusPx * this.k;
    if (r < 0.25) return tex;
    const ds = r > 28 ? 8 : r > 12 ? 4 : r > 4 ? 2 : 1;
    const key = ds;
    if (!this.blurRT[key]) {
      const w = Math.max(2, Math.round(this.W / ds)), h = Math.max(2, Math.round(this.H / ds));
      this.blurRT[key] = [this.makeRT(w, h), this.makeRT(w, h), w, h];
    }
    const [a, b, w, h] = this.blurRT[key];
    const m = this.mat.blur;
    // initial downsample copy
    this.mat.copy.uniforms.tSrc.value = tex;
    this.blit(this.mat.copy, a);
    const step = (r / ds) / 3.2307692308 / Math.sqrt(iterations);
    for (let i = 0; i < iterations; i++) {
      const sc = step * (1 + i * 0.35);
      m.uniforms.tSrc.value = a.texture; m.uniforms.uDir.value.set(sc / w, 0); this.blit(m, b);
      m.uniforms.tSrc.value = b.texture; m.uniforms.uDir.value.set(0, sc / h); this.blit(m, a);
    }
    return a.texture;
  }

  /** Render one output frame centred on time t (seconds). frameIndex (grain, glitch seeds) is the frame containing t. */
  render(t, { nsub = 1, shutter = 0.5, fps = 60, frameIndex = Math.floor(t * fps + 1e-6), toScreen = true } = {}) {
    const r = this.renderer, f = this.frame;
    this.postParams = { ...POST_DEFAULTS, bloomTint: [...POST_DEFAULTS.bloomTint], shake: [0, 0], split: [0, 0], lift: [0, 0, 0], gain: [1, 1, 1], flashColor: [1, 1, 1] };
    r.setRenderTarget(this.accum);
    r.setClearColor(0x000000, 0);
    r.clear(true, false, false);
    const times = subTimes(t, nsub, shutter, fps);
    for (let s = 0; s < nsub; s++) {
      this.renderSub(times[s], s, nsub, frameIndex);
      this.mat.accum.uniforms.tSrc.value = this.cur.texture;
      this.mat.accum.uniforms.uWeight.value = 1 / nsub;
      this.blit(this.mat.accum, this.accum);
    }
    this.finish(frameIndex, toScreen);
  }

  renderSub(t, sub, nsub, frameIndex) {
    const f = this.frame;
    this.compIdx = 0; this.tmpIdx = 0; this.stack.length = 0;
    f.t = t; f.subIndex = sub; f.nsub = nsub; f.frameIndex = frameIndex;
    f.clear('#000');
    if (this.timeline) this.timeline.render(f);
    this.stats.subframes++;
  }

  finish(frameIndex, toScreen) {
    const p = this.postParams, m = this.mat;
    // lens
    const L = m.lens.uniforms;
    L.tSrc.value = this.accum.texture;
    L.uShake.value.set(p.shake[0], p.shake[1]); L.uRot.value = p.rot; L.uZoom.value = p.zoom; L.uBarrel.value = p.barrel; L.uCA.value = p.ca;
    L.uSplit.value.set(p.split[0], p.split[1]); L.uGlitch.value = p.glitch; L.uSeed.value = (frameIndex * 0.6180339887) % 1 * 100; L.uPixel.value = p.pixel * this.k; L.uMirror.value = p.mirror; L.uWave.value = p.wave;
    L.uTime.value = frameIndex / 60;
    this.blit(m.lens, this.lensRT);
    // bloom
    let bloomTex = null;
    if (p.bloom > 0) {
      const B = this.bloomRT;
      m.bloomPre.uniforms.tSrc.value = this.lensRT.texture; m.bloomPre.uniforms.uThreshold.value = p.bloomThreshold; m.bloomPre.uniforms.uKnee.value = p.bloomKnee;
      m.bloomPre.uniforms.uTexel.value.set(0.5 / B[0].w, 0.5 / B[0].h);
      this.blit(m.bloomPre, B[0].down);
      for (let i = 1; i < B.length; i++) {
        m.bloomDown.uniforms.tSrc.value = B[i - 1].down.texture; m.bloomDown.uniforms.uTexel.value.set(1 / B[i - 1].w, 1 / B[i - 1].h);
        this.blit(m.bloomDown, B[i].down);
      }
      let lower = B[B.length - 1].down;
      for (let i = B.length - 2; i >= 0; i--) {
        const U = m.bloomUp.uniforms;
        U.tSrc.value = lower.texture; U.tBase.value = B[i].down.texture; U.uTexel.value.set(1 / B[i + 1].w, 1 / B[i + 1].h); U.uSpread.value = p.bloomSpread; U.uWeight.value = 1.0; U.uBase.value = i < this.bloomSkip ? 0 : 1;
        this.blit(m.bloomUp, B[i].up);
        lower = B[i].up;
      }
      bloomTex = lower.texture;
    }
    const F = m.final.uniforms;
    F.tSrc.value = this.lensRT.texture; F.tBloom.value = bloomTex || this.lensRT.texture; F.uBloom.value = bloomTex ? p.bloom / 5 : 0;
    F.uBloomTint.value.set(...p.bloomTint); F.uGrain.value = p.grain; F.uVignette.value = p.vignette; F.uVigSoft.value = p.vigSoft; F.uFade.value = p.fade;
    F.uFlash.value = p.flash; F.uFlashColor.value.set(...p.flashColor); F.uSaturation.value = p.saturation; F.uContrast.value = p.contrast;
    F.uLift.value.set(...p.lift); F.uGain.value.set(...p.gain); F.uInvert.value = p.invert; F.uLetterbox.value = p.letterbox; F.uScan.value = p.scan; F.uHalftone.value = p.halftone; F.uPaper.value = p.paper;
    F.uFrame.value = frameIndex % 4096;
    this.blit(m.final, toScreen ? null : this.other);
  }

  /** RGBA bytes of the frame just rendered to screen (rows bottom-up). */
  readPixels(out) {
    const gl = this.gl;
    this.renderer.setRenderTarget(null);
    gl.readPixels(0, 0, this.W, this.H, gl.RGBA, gl.UNSIGNED_BYTE, out);
    return out;
  }
}

const parseColor = (c) => (Array.isArray(c) ? c : hexToRgb(c));

/** Per-sub-frame drawing context handed to scenes. */
export class Frame {
  constructor(engine) {
    this.e = engine;
    this.t = 0;          // song time (s)
    this.lt = 0;         // time since clip start
    this.dur = 0;        // clip duration
    this.p = 0;          // clip progress 0..1
    this.subIndex = 0; this.nsub = 1; this.frameIndex = 0;
    this.W = engine.DW; this.H = engine.DH;
    this.cx = this.W / 2; this.cy = this.H / 2;
  }
  get song() { return this.e.song; }
  get pxW() { return this.e.W; }
  get pxH() { return this.e.H; }

  /** Fill the comp with a flat colour. */
  clear(color = '#000') {
    const [r, g, b] = parseColor(color);
    const m = this.e.mat.fill;
    m.uniforms.uColor.value.set(r, g, b, 1);
    this.e.blit(m, this.e.cur);
  }

  /** Full-screen GLSL pass over the comp. The material may sample `tPrev`. */
  shader(material, uniforms) {
    material.uniforms.uTime.value = this.t;
    this.e.pass(material, uniforms);
  }

  _drawCanvas(draw) {
    const { ctx, k } = this.e;
    ctx.reset();
    ctx.setTransform(k, 0, 0, k, 0, 0);
    draw(ctx, this);
    this.e.layerTex.needsUpdate = true;
    return this.e.layerTex;
  }

  _composite(tex, blend = 'over', opacity = 1, offset = null) {
    const m = this.e.mat.layer;
    m.uniforms.tLayer.value = tex; m.uniforms.uMode.value = BLEND[blend] ?? 0; m.uniforms.uOpacity.value = opacity;
    if (offset) m.uniforms.uOffset.value.set(offset[0], offset[1]); else m.uniforms.uOffset.value.set(0, 0);
    this.e.pass(m);
  }

  /**
   * Draw a 2D layer (design space f.W × f.H; 1920×1080 at 16:9) and composite it.
   * opts: { blend, opacity, blur (px), glow: {radius, strength}, shadow: {radius, opacity, dx, dy} }
   */
  canvas(draw, opts = {}) {
    let tex = this._drawCanvas(draw);
    const { blend = 'over', opacity = 1, blur = 0, glow = null, shadow = null } = opts;
    if (glow || shadow) {
      // keep a stable copy; the blur below needs the source twice
      const keep = this.e.tempRT();
      this.e.mat.copy.uniforms.tSrc.value = tex; this.e.blit(this.e.mat.copy, keep);
      tex = keep.texture;
      if (shadow) this._composite(this.e.blur(tex, shadow.radius ?? 24), 'shadow', shadow.opacity ?? 0.5, [-(shadow.dx ?? 0) / this.W, (shadow.dy ?? 12) / this.H]);
      if (glow) this._composite(this.e.blur(tex, glow.radius ?? 30, glow.iterations ?? 2), 'add', glow.strength ?? 0.6);
    }
    if (blur > 0) tex = this.e.blur(tex, blur);
    this._composite(tex, blend, opacity);
  }

  /** Draw a 2D layer and return it as a texture (premultiplied) instead of compositing. */
  layer(draw) {
    const tex = this._drawCanvas(draw);
    const keep = this.e.tempRT();
    this.e.mat.copy.uniforms.tSrc.value = tex; this.e.blit(this.e.mat.copy, keep);
    return keep.texture;
  }

  /** Composite an existing texture (premultiplied alpha). */
  put(tex, opts = {}) {
    const { blend = 'over', opacity = 1, blur = 0, offset = null } = opts;
    this._composite(blur > 0 ? this.e.blur(tex, blur) : tex, blend, opacity, offset);
  }

  blur(tex, radius, iterations) { return this.e.blur(tex, radius, iterations); }

  /** Render a three.js scene (transparent background) and composite it. opts: { tone, exposure, opacity, blur, blend } */
  three(scene, camera, opts = {}) {
    const { tone = 'aces', exposure = 1, opacity = 1, blur = 0, blend = 'over', glow = null } = opts;
    const e = this.e, r = e.renderer;
    r.setRenderTarget(e.rt3d);
    r.setClearColor(0x000000, 0);
    r.clear(true, true, false);
    r.render(scene, camera);
    let tex = e.rt3d.texture;
    const m = e.mat.three;
    if (glow) {
      m.uniforms.tLayer.value = e.blur(tex, glow.radius ?? 30); m.uniforms.uTone.value = tone === 'aces' ? 1 : tone === 'neutral' ? 2 : 0;
      m.uniforms.uExposure.value = exposure; m.uniforms.uOpacity.value = glow.strength ?? 0.5; m.uniforms.uMode.value = 1;
      e.pass(m);
    }
    if (blur > 0) tex = e.blur(tex, blur);
    m.uniforms.tLayer.value = tex; m.uniforms.uTone.value = tone === 'aces' ? 1 : tone === 'neutral' ? 2 : 0;
    m.uniforms.uExposure.value = exposure; m.uniforms.uOpacity.value = opacity; m.uniforms.uMode.value = blend === 'add' ? 1 : 0;
    e.pass(m);
  }

  /** Snapshot of the comp so far (for feedback / refraction style effects). */
  snapshot() {
    const keep = this.e.tempRT();
    this.e.mat.copy.uniforms.tSrc.value = this.e.cur.texture; this.e.blit(this.e.mat.copy, keep);
    return keep.texture;
  }

  /** Render another scene into its own buffer and return it as a texture. */
  sub(scene, t = this.t, clip = null) {
    const e = this.e;
    e.stack.push([e.comp, e.compIdx]);
    if (!e.subComps) e.subComps = [];
    const depth = e.stack.length - 1;
    if (!e.subComps[depth]) e.subComps[depth] = [e.makeRT(e.W, e.H), e.makeRT(e.W, e.H)];
    e.comp = e.subComps[depth]; e.compIdx = 0;
    const saved = { t: this.t, lt: this.lt, dur: this.dur, p: this.p };
    const savedPost = e.postParams;                 // a nested scene must not restyle the parent's finishing
    e.postParams = { ...savedPost };
    this.t = t;
    if (clip) { this.lt = t - clip.t0; this.dur = clip.t1 - clip.t0; this.p = this.lt / this.dur; }
    this.clear('#000');
    scene.render(this);
    const keep = e.tempRT();
    e.mat.copy.uniforms.tSrc.value = e.cur.texture; e.blit(e.mat.copy, keep);
    [e.comp, e.compIdx] = e.stack.pop();
    e.postParams = savedPost;
    Object.assign(this, saved);
    return keep.texture;
  }

  /** Override finishing parameters for this frame (see POST_DEFAULTS). */
  post(params) { Object.assign(this.e.postParams, params); }
}
