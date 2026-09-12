// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
const canvas = document.querySelector("#canvas"),
  audio = document.querySelector("#audio");
const metrics = (window.visualizerMetrics = {
  frames: 0,
  errors: [],
  compiled: false,
  bass: 0,
  onset: 0,
  preset: 0,
});
const gl = canvas.getContext("webgl2", {
  antialias: false,
  alpha: false,
  preserveDrawingBuffer: true,
});
let context,
  analyser,
  source,
  data,
  wave,
  program,
  preset = 0,
  next = 0,
  blend = 0,
  began = performance.now(),
  fileURL,
  mode = "ambient",
  testTimer,
  voices = new Set(),
  previousBass = 0,
  heldOnset = 0,
  cycleIndex = 0;
const uniforms = {},
  features = new Float32Array(4),
  sequence = [0, 5, 1, 2, 3, 7, 4, 6];
const fail = (error) => {
  metrics.errors.push(String(error));
  const el = document.querySelector("#error");
  el.hidden = false;
  el.textContent = String(error);
};
function shader(type, code) {
  const s = gl.createShader(type);
  gl.shaderSource(s, code);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw Error(gl.getShaderInfoLog(s));
  return s;
}
function ensureAudio() {
  if (context) return;
  context = new AudioContext();
  analyser = context.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.18;
  analyser.minDecibels = -80;
  analyser.maxDecibels = -17;
  data = new Uint8Array(analyser.frequencyBinCount);
  wave = new Float32Array(analyser.fftSize);
  source = context.createMediaElementSource(audio);
  source.connect(analyser);
  analyser.connect(context.destination);
}
function stopTest() {
  clearInterval(testTimer);
  testTimer = null;
  for (const voice of voices) {
    try {
      voice.stop();
    } catch {}
  }
  voices.clear();
  document.querySelector("#test").textContent = "Test rhythm";
}
async function load(url, label) {
  ensureAudio();
  stopTest();
  audio.src = url;
  audio.hidden = false;
  void context.resume().catch(fail);
  mode = "song";
  previousBass = heldOnset = 0;
  document.querySelector("#status").textContent = label;
  try {
    await audio.play();
  } catch {
    document.querySelector("#status").textContent = label + " — press play";
  }
}
function select(id) {
  preset = id;
  next = id;
  blend = 0;
  const info = presets.find((p) => p.id === id);
  document.querySelector("#name").textContent = info.name;
  document.querySelector("#description").textContent = info.description;
  document
    .querySelectorAll("#presets button")
    .forEach((button, i) =>
      button.setAttribute("aria-pressed", String(i === id)),
    );
}
let presets = [];
try {
  if (!gl) throw Error("This preview needs WebGL2.");
  const [code, list] = await Promise.all([
    fetch("./collection.frag").then((r) => r.text()),
    fetch("./presets.json").then((r) => r.json()),
  ]);
  presets = list;
  const vs = shader(
    gl.VERTEX_SHADER,
    "#version 300 es\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}",
  );
  const fs = shader(
    gl.FRAGMENT_SHADER,
    "#version 300 es\nprecision highp float;\nprecision highp int;\n" + code,
  );
  program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw Error(gl.getProgramInfoLog(program));
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  gl.useProgram(program);
  for (const name of [
    "resolution",
    "time",
    "audio",
    "energy",
    "strength",
    "preset",
    "nextPreset",
    "blend",
  ])
    uniforms[name] = gl.getUniformLocation(program, "u_" + name);
  metrics.compiled = true;
  for (const entry of presets) {
    const button = document.createElement("button");
    button.setAttribute("aria-pressed", String(entry.id === 0));
    button.innerHTML = `<img src="./previews/${entry.id}.png" alt=""><span>${entry.name}</span>`;
    button.onclick = () => {
      document.querySelector("#cycle").checked = false;
      select(entry.id);
    };
    document.querySelector("#presets").append(button);
  }
} catch (error) {
  fail(error);
}
document.querySelector("#file").onchange = async (event) => {
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (fileURL) URL.revokeObjectURL(fileURL);
    fileURL = URL.createObjectURL(file);
    await load(fileURL, file.name);
  } catch (error) {
    fail(error);
  }
};
document.querySelector("#demo").onclick = () =>
  load(
    "/api/takes/c6bb67a6f3024be9ac2382ef4297250b/files/audio.mp3",
    "Forwarding Address — Rental Hours",
  ).catch(fail);
document.querySelector("#aspect").onclick = (event) => {
  const portrait = document
    .querySelector("#stage")
    .classList.toggle("portrait");
  event.target.textContent = portrait ? "16:9" : "9:16";
};
document.querySelector("#strength").oninput = (event) => {
  document.querySelector("#strength-value").textContent =
    event.target.value + "%";
};
document.querySelector("#cycle").onchange = () => {
  cycleIndex = -1;
};
document.querySelector("#test").onclick = async () => {
  if (testTimer) {
    stopTest();
    mode = "ambient";
    return;
  }
  ensureAudio();
  audio.pause();
  void context.resume().catch(fail);
  mode = "test";
  began = performance.now();
  document.querySelector("#test").textContent = "Stop test";
  document.querySelector("#status").textContent = "Diagnostic rhythm · 108 BPM";
  let beat = 0;
  const hit = () => {
    const now = context.currentTime;
    const osc = context.createOscillator(),
      gain = context.createGain();
    osc.frequency.setValueAtTime(145, now);
    osc.frequency.exponentialRampToValueAtTime(44, now + 0.16);
    gain.gain.setValueAtTime(0.72, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.24);
    osc.connect(gain);
    gain.connect(analyser);
    voices.add(osc);
    osc.onended = () => {
      voices.delete(osc);
      osc.disconnect();
      gain.disconnect();
    };
    osc.start(now);
    osc.stop(now + 0.26);
    if (beat++ % 2 === 1) {
      const note = context.createOscillator(),
        g = context.createGain();
      note.type = "triangle";
      note.frequency.value = 440;
      g.gain.setValueAtTime(0.1, now);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);
      note.connect(g);
      g.connect(analyser);
      voices.add(note);
      note.onended = () => {
        voices.delete(note);
        note.disconnect();
        g.disconnect();
      };
      note.start(now);
      note.stop(now + 0.16);
    }
  };
  hit();
  testTimer = setInterval(hit, 60000 / 108);
};
audio.onplay = () => {
  ensureAudio();
  void context.resume().catch(fail);
  mode = "song";
};
audio.onseeking = () => {
  heldOnset = previousBass = 0;
};
audio.onerror = () =>
  fail("The audio could not be loaded. Try a local song file.");
let last = 0;
function render(now) {
  if (!program) return;
  const dt = Math.min(0.1, (now - last) / 1000 || 1 / 60);
  last = now;
  const dpr = Math.min(devicePixelRatio, 1.5),
    width = Math.min(1920, Math.round(canvas.clientWidth * dpr)),
    height = Math.round((width * canvas.clientHeight) / canvas.clientWidth);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    gl.viewport(0, 0, width, height);
  }
  const time = mode === "song" ? audio.currentTime : (now - began) / 1000;
  let energy = 0;
  if (analyser && ((mode === "song" && !audio.paused) || mode === "test")) {
    analyser.getByteFrequencyData(data);
    analyser.getFloatTimeDomainData(wave);
    const band = (lo, hi) => {
      const start = Math.max(
          1,
          Math.round((lo * analyser.fftSize) / context.sampleRate),
        ),
        end = Math.min(
          data.length,
          Math.round((hi * analyser.fftSize) / context.sampleRate),
        );
      let sum = 0;
      for (let i = start; i < end; i++) sum += data[i] / 255;
      return Math.max(
        0,
        Math.min(1, (sum / Math.max(1, end - start) - 0.06) / 0.78),
      );
    };
    const bass = band(35, 190),
      mid = band(190, 2400),
      treble = band(2400, 10000);
    heldOnset = Math.max(
      Math.max(0, bass - previousBass) * 5,
      heldOnset * Math.exp(-dt / 0.13),
    );
    previousBass = bass;
    features.set([bass, mid, treble, Math.min(1, heldOnset)]);
    for (const sample of wave) energy += sample * sample;
    energy = Math.min(1, Math.sqrt(energy / wave.length) * 3.5);
  } else if (mode === "ambient") {
    features.fill(0);
  }
  if (document.querySelector("#cycle").checked) {
    const index = Math.floor(time / 20),
      local = time % 20;
    if (index !== cycleIndex) {
      cycleIndex = index;
      select(sequence[index % sequence.length]);
    }
    next = sequence[(index + 1) % sequence.length];
    blend = Math.max(0, (local - 18.7) / 1.3);
  }
  gl.uniform2f(uniforms.resolution, width, height);
  gl.uniform1f(uniforms.time, time);
  gl.uniform4fv(uniforms.audio, features);
  gl.uniform1f(uniforms.energy, energy);
  gl.uniform1f(
    uniforms.strength,
    Number(document.querySelector("#strength").value) / 100,
  );
  gl.uniform1i(uniforms.preset, preset);
  gl.uniform1i(uniforms.nextPreset, next);
  gl.uniform1f(uniforms.blend, blend);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  metrics.frames++;
  metrics.bass = features[0];
  metrics.onset = features[3];
  metrics.preset = preset;
  metrics.time = time;
  metrics.dimensions = [width, height];
  document.querySelector("#meter i").style.width = features[0] * 100 + "%";
  requestAnimationFrame(render);
}
requestAnimationFrame(render);
window.addEventListener("pagehide", () => {
  stopTest();
  audio.pause();
  context?.close();
  if (fileURL) URL.revokeObjectURL(fileURL);
});
