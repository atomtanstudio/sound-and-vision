const canvas = document.querySelector("#canvas");
const gl = canvas.getContext("webgl2", {
  antialias: false,
  preserveDrawingBuffer: true,
});
const audio = document.querySelector("#audio");
const status = document.querySelector("#status");
const error = document.querySelector("#error");
const metrics = {
  frames: 0,
  shaderCompiled: false,
  audioFrames: 0,
  bass: 0,
  peakBass: 0,
  errors: [],
};
window.shaderStudy = metrics;

function fail(e) {
  const message = e instanceof Error ? e.message : String(e);
  error.hidden = false;
  error.textContent = message;
  metrics.errors.push(message);
}
function compile(type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS))
    throw Error(gl.getShaderInfoLog(shader));
  return shader;
}
let context,
  analyser,
  testTimer,
  songObjectUrl,
  mode = "ambient",
  sourceName = "",
  began = performance.now();
let simulatedStart = 0,
  program,
  texture,
  uTime,
  uResolution,
  uResponse,
  lastSample = 0,
  shaderObjectUrl;
const history = new Uint8Array(512 * 512 * 4);
const silent = new Uint8Array(512 * 512 * 4);
const row = new Uint8Array(512 * 4),
  spectrum = new Uint8Array(512),
  wave = new Uint8Array(1024);
const testVoices = new Set();

function ensureAudio() {
  if (context) return;
  context = new AudioContext();
  analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.28;
  analyser.minDecibels = -85;
  analyser.maxDecibels = -15;
  const source = context.createMediaElementSource(audio);
  source.connect(analyser);
  analyser.connect(context.destination);
}
function clearTexture() {
  history.fill(0);
  metrics.bass = 0;
  metrics.peakBass = 0;
  metrics.audioFrames = 0;
  document.querySelector("#level-fill").style.width = "0%";
}
function stopTest() {
  if (testTimer) clearInterval(testTimer);
  testTimer = null;
  for (const voice of testVoices) {
    try {
      voice.stop();
    } catch {}
  }
  testVoices.clear();
  document.querySelector("#test").textContent = "Test rhythm";
}
async function loadAudio(url, label, objectUrl = false) {
  ensureAudio();
  stopTest();
  // A suspended context may wait indefinitely for a user gesture. Show the
  // loaded player immediately so its Play control can provide that gesture.
  context.resume().catch(fail);
  audio.pause();
  if (songObjectUrl) URL.revokeObjectURL(songObjectUrl);
  songObjectUrl = objectUrl ? url : null;
  audio.src = url;
  audio.hidden = false;
  mode = "song";
  sourceName = label;
  clearTexture();
  status.textContent = label;
  audio.load();
  try {
    await audio.play();
  } catch {
    status.textContent = `${label} · press play`;
  }
}
document.querySelector("#file").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (file) loadAudio(URL.createObjectURL(file), file.name, true).catch(fail);
});
document
  .querySelector("#demo")
  .addEventListener("click", () =>
    loadAudio(
      "/api/takes/55c92ee597594740997721f987b1cfa3/files/audio.mp3",
      "Good Company · Guest Policy",
    ).catch(fail),
  );
audio.addEventListener("error", () =>
  fail("The song could not be loaded. Choose a local audio file."),
);
audio.addEventListener("seeking", clearTexture);
audio.addEventListener("play", () => {
  context?.resume().catch(fail);
  status.textContent = sourceName;
});
document
  .querySelector("#titles")
  .addEventListener(
    "change",
    (event) =>
      (document.querySelector("#caption").hidden = !event.target.checked),
  );
document.querySelector("#aspect").addEventListener("click", (event) => {
  const portrait = document
    .querySelector("#stage")
    .classList.toggle("portrait");
  event.target.textContent = portrait ? "9:16" : "16:9";
});
const responseControl = document.querySelector("#response");
responseControl.addEventListener("input", () => {
  document.querySelector("#response-value").value =
    `${Math.round(Number(responseControl.value) * 100)}%`;
});

// Audible test signal, explicitly labelled: sparse kick + quiet D-minor pads.
// It is only an interaction check, not a generated song or a mood classifier.
document.querySelector("#test").addEventListener("click", async () => {
  try {
    ensureAudio();
    await context.resume();
    audio.pause();
    if (testTimer) {
      stopTest();
      mode = "ambient";
      began = performance.now();
      clearTexture();
      status.textContent = "Ambient motion";
      return;
    }
    mode = "test";
    audio.hidden = true;
    sourceName = "Test rhythm · 72 BPM";
    status.textContent = sourceName;
    clearTexture();
    simulatedStart = context.currentTime;
    let count = 0;
    const tick = () => {
      const now = context.currentTime;
      const kick = context.createOscillator(),
        gain = context.createGain();
      kick.frequency.setValueAtTime(100, now);
      kick.frequency.exponentialRampToValueAtTime(42, now + 0.18);
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(0.25, now + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
      kick.connect(gain);
      gain.connect(analyser);
      kick.start(now);
      kick.stop(now + 0.55);
      testVoices.add(kick);
      kick.onended = () => {
        testVoices.delete(kick);
        kick.disconnect();
        gain.disconnect();
      };
      if (count++ % 4 === 0)
        for (const hz of [146.83, 174.61, 220]) {
          const tone = context.createOscillator(),
            level = context.createGain();
          tone.type = "sine";
          tone.frequency.value = hz;
          level.gain.setValueAtTime(0, now);
          level.gain.linearRampToValueAtTime(0.025, now + 0.6);
          level.gain.linearRampToValueAtTime(0, now + 3.2);
          tone.connect(level);
          level.connect(analyser);
          tone.start(now);
          tone.stop(now + 3.25);
          testVoices.add(tone);
          tone.onended = () => {
            testVoices.delete(tone);
            tone.disconnect();
            level.disconnect();
          };
        }
    };
    tick();
    testTimer = setInterval(tick, 60000 / 72);
    document.querySelector("#test").textContent = "Stop test";
  } catch (e) {
    fail(e);
  }
});

try {
  if (!gl) throw Error("This browser does not support WebGL2.");
  const embedded = document.querySelector("#shader-source");
  let fragment = embedded?.textContent;
  if (!fragment) {
    const response = await fetch("./blue-hour.frag");
    if (!response.ok) throw Error("Could not load the original shader.");
    fragment = await response.text();
  }
  shaderObjectUrl = URL.createObjectURL(
    new Blob([fragment], { type: "text/plain" }),
  );
  document.querySelector(".download").href = shaderObjectUrl;
  if (location.protocol === "file:")
    document.querySelector("#demo").hidden = true;
  const vertex = `#version 300 es\nin vec2 a_position;void main(){gl_Position=vec4(a_position,0,1);}`;
  const prefix = `#version 300 es\nprecision highp float;\nout vec4 fragColor;\n`;
  program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertex));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, prefix + fragment));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw Error(gl.getProgramInfoLog(program));
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 3, -1, -1, 3]),
    gl.STATIC_DRAW,
  );
  const position = gl.getAttribLocation(program, "a_position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  uTime = gl.getUniformLocation(program, "u_time");
  uResolution = gl.getUniformLocation(program, "u_resolution");
  uResponse = gl.getUniformLocation(program, "u_response");
  texture = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.RGBA,
    512,
    512,
    0,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    history,
  );
  gl.uniform1i(gl.getUniformLocation(program, "u_audio"), 0);
  metrics.shaderCompiled = true;
  function frame(now) {
    const rect = canvas.getBoundingClientRect();
    const scale = Math.min(
      devicePixelRatio,
      1.5,
      1920 / Math.max(rect.width, 1),
    );
    const width = Math.max(1, Math.round(rect.width * scale)),
      height = Math.max(1, Math.round(rect.height * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    }
    const reactive = document.querySelector("#reactive").checked;
    const playing =
      mode === "test" || (mode === "song" && !audio.paused && !audio.ended);
    if (analyser && playing && now - lastSample >= 1000 / 60) {
      lastSample = now;
      analyser.getByteFrequencyData(spectrum);
      analyser.getByteTimeDomainData(wave);
      let bass = 0;
      for (let i = 0; i < 512; i++) {
        row[i * 4] = spectrum[i];
        row[i * 4 + 1] = wave[i * 2];
        row[i * 4 + 2] = spectrum[i];
        row[i * 4 + 3] = 255;
        if (i > 0 && i < 10) bass += spectrum[i] / 255 / 9;
      }
      history.copyWithin(512 * 4, 0, history.length - 512 * 4);
      history.set(row, 0);
      metrics.bass = bass;
      metrics.peakBass = Math.max(metrics.peakBass, bass);
      metrics.audioFrames++;
      document.querySelector("#level-fill").style.width =
        `${Math.round(bass * 100)}%`;
    }
    gl.texSubImage2D(
      gl.TEXTURE_2D,
      0,
      0,
      0,
      512,
      512,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      reactive ? history : silent,
    );
    const time =
      mode === "song"
        ? audio.currentTime
        : mode === "test"
          ? context.currentTime - simulatedStart
          : (now - began) / 1000;
    gl.uniform1f(uTime, time);
    gl.uniform1f(uResponse, Number(responseControl.value));
    gl.uniform2f(uResolution, width, height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    metrics.frames++;
    metrics.time = time;
    metrics.mode = mode;
    metrics.reactive = reactive;
    metrics.response = Number(responseControl.value);
    metrics.audioContextState = context?.state ?? "not-started";
    metrics.dimensions = [width, height];
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
} catch (e) {
  fail(e);
}
window.addEventListener("pagehide", () => {
  stopTest();
  audio.pause();
  context?.close();
  if (songObjectUrl) URL.revokeObjectURL(songObjectUrl);
  if (shaderObjectUrl) URL.revokeObjectURL(shaderObjectUrl);
});
