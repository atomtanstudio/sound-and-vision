/** Preserved song-film style directions. SPDX-License-Identifier: Apache-2.0
 * These are a roadmap, NOT extra selectable renderer presets. IDs are stable.
 * Source: standalone/illustrated-song-film/VISUALIZER-STYLE-CATALOG.md.
 */
export type VisualizerDirection = {
  id: string;
  name: string;
  status: "standalone-study" | "archived-study" | "concept";
  surface: string;
  response: string;
  suits: string;
};
export const songReactiveDirections: readonly VisualizerDirection[] = [
  {
    id: "crt-vu",
    name: "Segmented CRT spectrum and VU meters",
    status: "standalone-study",
    surface: "Rectangular glass or equipment",
    response: "Frequency bands, stereo energy, bass lamp",
    suits: "Electronic, radio, retro dance",
  },
  {
    id: "ribbon-field",
    name: "Luminous ribbon field",
    status: "standalone-study",
    surface: "Curved glass or atmospheric image",
    response: "Smoothed spectral contour, waveform, restrained energy",
    suits: "Dreampop, ambient, ballads",
  },
  {
    id: "eclipse-tachometer",
    name: "Eclipse tachometer",
    status: "standalone-study",
    surface: "Sun, wheel, dial or iris",
    response: "Radial frequency blades, bass pulse, drum flashes",
    suits: "Rock, driving rhythms, desert imagery",
  },
  {
    id: "etched-glass",
    name: "Etched-glass resonance contours",
    status: "archived-study",
    surface: "Dark glass or architectural space",
    response: "Nested spectral contours, bass pressure, transient glints",
    suits: "Trip-hop, art-pop, intimate electronic music",
  },
  {
    id: "acoustic-strings",
    name: "Acoustic string resonance",
    status: "archived-study",
    surface: "Exposed piano strings and soundboard",
    response: "Frequency-dependent glints and vibration echoes",
    suits: "Piano-led art-pop; requires a new validated mapping",
  },
  {
    id: "analog-needles",
    name: "Analog needle pair",
    status: "concept",
    surface: "Two physical meters",
    response: "Left/right RMS, peak hold and inertia",
    suits: "Blues, jazz, live recording",
  },
  {
    id: "speaker-cone",
    name: "Speaker-cone displacement",
    status: "concept",
    surface: "Visible woofer or membrane",
    response: "Low-frequency displacement and transient recoil",
    suits: "Bass-forward music, hip-hop, dub",
  },
  {
    id: "topographic",
    name: "Topographic contour field",
    status: "concept",
    surface: "Terrain, map, water or paper",
    response: "Spectral bands become breathing contours",
    suits: "Cinematic, folk, ambient, experimental",
  },
  {
    id: "prism",
    name: "Prism or stained-glass cells",
    status: "concept",
    surface: "Window or faceted object",
    response: "Separate low/mid/high lighting and color shifts",
    suits: "Orchestral, psychedelic, luminous pop",
  },
  {
    id: "constellation",
    name: "Particle constellation",
    status: "concept",
    surface: "Night sky, dust or open space",
    response: "Onsets release particles; energy sets density",
    suits: "Dreamy electronic, spacious tracks",
  },
  {
    id: "film-sprockets",
    name: "Film-sprocket pulses",
    status: "concept",
    surface: "Projector, film strip or photographic scene",
    response: "Drum-driven frame-edge flashes and gate motion",
    suits: "Garage rock, punk, archival mood",
  },
  {
    id: "ink-bloom",
    name: "Ink-in-water bloom",
    status: "concept",
    surface: "Liquid, glass or paper",
    response: "Bass pushes bloom; high frequencies break edges",
    suits: "Slow, organic, immersive songs",
  },
  {
    id: "neon-sign",
    name: "Neon sign flicker",
    status: "concept",
    surface: "Physical sign and empty letters",
    response: "Per-band lamp intensity and restrained transient flicker",
    suits: "City-pop, synth, nocturnal songs",
  },
  {
    id: "mechanical-shutters",
    name: "Mechanical shutter grid",
    status: "concept",
    surface: "Slats, vents, louvers or architectural frame",
    response: "Drums open selected cells; sustained sound holds them",
    suits: "Industrial, post-punk, hard electronic",
  },
  {
    id: "lissajous",
    name: "Oscilloscope Lissajous",
    status: "concept",
    surface: "Circular or rectangular scope",
    response: "True left/right phase trace with persistence",
    suits: "Instrumental, experimental, electronic",
  },
  {
    id: "vinyl-halo",
    name: "Vinyl-groove halo",
    status: "concept",
    surface: "Record, turntable or circular label",
    response: "Bass groove ripples and transient stylus flicker",
    suits: "Soul, disco, sample-based music",
  },
];
