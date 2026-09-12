// Blue Hour — an original Sound/Vision shader study.
// Copyright 2026 Sound/Vision contributors. SPDX-License-Identifier: Apache-2.0
// FragCoord: paste this file into Main, then choose a song in the Audio inspector.
// R = weighted spectrum; G = waveform; B = raw spectrum; y = recent history.
uniform vec2 u_resolution;
uniform float u_time;
uniform sampler2D u_audio;
// Optional custom control. An unset value (0) uses the normal response.
uniform float u_response;

float grainHash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    q += dot(q, q.yzx + 19.19);
    return fract((q.x + q.y) * q.z);
}

float velvetNoise(vec2 p) {
    vec2 cell = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(grainHash(cell), grainHash(cell + vec2(1, 0)), u.x),
               mix(grainHash(cell + vec2(0, 1)), grainHash(cell + vec2(1, 1)), u.x), u.y);
}

float softField(vec2 p) {
    float sum = 0.0, weight = 0.5;
    mat2 turn = mat2(0.80, 0.60, -0.60, 0.80);
    for (int i = 0; i < 5; i++) {
        sum += weight * velvetNoise(p);
        p = turn * p * 2.02 + vec2(2.13, 7.17);
        weight *= 0.5;
    }
    return sum;
}

float spectrumBand(float a, float b, float history) {
    float energy = 0.0;
    for (int i = 0; i < 8; i++) {
        float x = mix(a, b, (float(i) + 0.5) / 8.0);
        energy += texture(u_audio, vec2(x, history)).b;
    }
    return energy / 8.0;
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution;
    vec2 p = (gl_FragCoord.xy - 0.5 * u_resolution) / min(u_resolution.x, u_resolution.y);
    float t = u_time;

    // Preserve the current attack. Comparing it with older sound separates
    // a new bass hit from a sustained note; time alone cannot create a pulse.
    float currentLow = spectrumBand(0.002, 0.019, 0.5 / 512.0);
    float previousLow = 0.0;
    for (int i = 0; i < 3; i++) {
        float age = (8.5 + float(i) * 8.0) / 512.0;
        previousLow += spectrumBand(0.002, 0.019, age) / 3.0;
    }
    float hit = smoothstep(0.025, 0.18, max(0.0, currentLow - previousLow));
    float low = smoothstep(0.06, 0.78, currentLow);
    float air = smoothstep(0.015, 0.45, spectrumBand(0.14, 0.40, 0.5 / 512.0));
    float response = u_response > 0.0 ? clamp(u_response, 0.25, 2.0) : 1.0;
    float breath = (low * 0.24 + hit * 0.26) * response;
    p *= 1.0 - (0.055 * low + 0.10 * hit) * response;

    vec2 q = mat2(0.94, 0.342, -0.342, 0.94) * p;
    vec2 wind = vec2(t * 0.023, -t * 0.011);
    vec2 warp = vec2(softField(q * 1.6 + wind),
                     softField(q * 1.5 - wind * 0.7 + 11.7));
    q += (warp - 0.5) * (0.50 + breath);

    vec3 ink = vec3(0.019, 0.038, 0.064);
    vec3 slate = vec3(0.19, 0.28, 0.36);
    vec3 silverBlue = vec3(0.55, 0.64, 0.70);
    vec3 color = ink;
    float atmosphere = softField(q * 1.3 + wind * 0.4);
    color += vec3(0.06, 0.10, 0.145) * atmosphere;

    // Three translucent, wind-folded sheets. Different depths drift at
    // different rates; fine contour threads sit inside their broad highlights.
    for (int i = 0; i < 3; i++) {
        float layer = float(i);
        float center = -0.38 + layer * 0.36;
        float fold = q.y - center
            + 0.20 * sin(q.x * 2.0 + layer * 1.4 + t * 0.037)
            + 0.17 * sin(q.x * 4.1 - t * 0.024 + layer * 2.3)
            + 0.18 * (softField(q * vec2(1.8, 0.6) + layer * 7.0 + wind) - 0.5);
        float spread = (0.17 + layer * 0.045) * (1.0 + hit * response * 0.22);
        float body = exp(-pow(fold / spread, 2.0));
        float edge = exp(-pow((fold + spread * 0.46) / 0.047, 2.0));
        float fine = pow(0.5 + 0.5 * sin(fold * 105.0 + softField(q * 4.0) * 5.0), 10.0);
        float light = 0.5 + 0.5 * sin(q.x * 1.4 + layer * 1.8);
        color = mix(color, slate * (0.56 + light * 0.45), body * 0.64);
        color += silverBlue * edge * (0.10 + response * (low * 0.12 + hit * 0.20)) * (0.25 + light * 0.75);
        color += vec3(0.25, 0.36, 0.45) * fine * body * (0.035 + air * response * 0.085);
    }

    // Soft distant light and a quiet central area for optional song typography.
    vec2 haloPos = p - vec2(-0.48 + sin(t * 0.021) * 0.07, 0.35);
    float halo = exp(-dot(haloPos * vec2(1.0, 1.4), haloPos * vec2(1.0, 1.4)) * 2.3);
    color += vec3(0.12, 0.17, 0.205) * halo * (0.40 + response * (low * 0.12 + hit * 0.20));
    color *= 1.0 + response * (low * 0.18 + hit * 0.45);
    float vignette = 1.0 - smoothstep(0.25, 1.3, length(p * vec2(0.75, 1.0)));
    color *= 0.66 + 0.34 * vignette;
    float dust = grainHash(gl_FragCoord.xy + floor(t * 12.0) * 43.71) - 0.5;
    color += dust * 0.013;
    color = pow(max(color, vec3(0.0)), vec3(0.88));
    fragColor = vec4(color, 1.0);
}
