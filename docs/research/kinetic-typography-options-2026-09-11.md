# Sound / Vision: kinetic typography options

Researched 11 September 2026. Scope: 30 existing tools and resources, 18 proposed visual styles, and an integration recommendation. This is research, not an installed feature or a performance benchmark. Capabilities and licensing below come from the linked project/vendor sources; suggested applications and effort are engineering judgments. The application findings come from the current workspace source, not a new audit of the deployed Legion service.

## What Sound / Vision currently uses

There are three distinct systems:

- **Background generation:** MiniMax H3 through H3LIX. It can generate scenes, graphics and short decorative lettering, which is baked into the resulting clip. See `backend/video.py:408` and `src/video/timeline.ts:246`.
- **Synchronized lyric preview:** React-rendered words with time-calculated CSS transforms. `src/video/kinetics.ts:2` implements the entrances; `src/video/VideoWorkspace.tsx:1456` renders the words. The draft offers Bold, Soft and Editorial fonts; Auto, Pop, Slam, Rise, Highlight, Reveal and Calm motion; and Center or Lower placement (`src/video/timeline.ts:41`). Auto is a selector, not another distinct visual language.
- **Scripted full-film export:** FFmpeg/libass draws individually timed words with three alternating entrance patterns (`scripts/video/render-kinetic-film.py:179`). This renderer is separate from the browser preview. A new preview effect will not automatically appear in the exported film.

The separate audio visualizer uses **raw WebGL2**, verified in `src/video/visualizers/VisualizerCanvas.tsx:72`. Three.js is not listed in the current package dependencies. The existing system is therefore not using H3 to generate every synchronized lyric, nor is the lyric layer currently a Three.js composition.

The useful foundation is already present: canonical lyrics, editable acoustic word timing, the original audio master, and measured musical structure. New styles should reuse these.

## The Rolling Stones reference

[Official lyric video: Sympathy for the Devil](https://www.youtube.com/watch?v=GgnClrx8N2k). The commissioned studio, Yes Please Productions, says its Beggars Banquet lyric-video series drew on the original graffiti-covered bathroom-wall sleeve: [production credits and brief](https://creativepool.com/yesplease/projects/the-rolling-stones-sympathy-for-the-devil-official-lyric-video-for-abkco). I confirmed the official video identity and inspected its opening wall/title frame in the browser; I did not perform a complete frame-by-frame viewing.

The transferable idea in your description is **a persistent writing surface that the camera explores**. Words can accumulate, cross out earlier marks, spread into unused areas and pull the camera along. That offers much more variety than replacing one centered line with another.

An original version is feasible with authored vector lettering and a shared camera transform. For believable writing, ordinary font outlines are insufficient by themselves: drawing an outline traces the boundary of a letter rather than a pen's writing path. Use actual stroke-font data, authored pen paths, or an animated stroke mask over the filled lettering. Vara's special font format and Leon Sans's exposed drawing paths are useful starting points.

A generated blank wall or paper texture can supply atmosphere. Put the lettering and surface into the same controlled 2D/3D scene so they share perspective. An independently animated H3 wall would introduce tracking and deformation problems; it is a harder first implementation. We need not reproduce the Stones' wall, palette, markings or lettering.

## The styles worth offering

These are proposed Sound / Vision styles, not claims that every tool below already contains a finished lyric-video preset. Effort is relative to the current code: **S** = mostly layout/timing work; **M** = new scene or asset system; **L** = substantial simulation, rendering or generation work. A shared export path is additional work across the collection.

| Style | Suitable music | Type, placement and action | Likely ingredients | Effort |
|---|---|---|---|---|
| 1. Quiet editorial | Mellow, acoustic, intimate | Carefully set serif/sans phrases, generous space, gentle line changes and emphasis | Existing renderer; Anime.js or Motion Canvas | S |
| 2. Notebook / unsent letter | Folk, confessional, bittersweet | Handwriting grows across paper; annotations and cross-outs; slow page movement | Vara/Vivus, SVG masks, licensed stroke lettering | M |
| 3. Floating fragments | Ambient, dream pop | Small phrases enter from different depths and drift on restrained paths | Anime.js; optional Three.js | M |
| 4. Typewriter / terminal | Sparse indie, narrative, mechanical | Monospaced text types, revises and advances; deliberate cursor and carriage motion | DOM/SVG, Anime.js | S |
| 5. Neon after hours | Downtempo, synth, nocturnal | Thin drawn lettering, restrained glow, fading trails on a dark scene | Leon Sans, PixiJS filters | M |
| 6. Writing on the wall | Raw rock, ominous, obsessive | Marker/scrawl accumulates across a large surface; camera follows new phrases | SVG stroke masks, layout planner, 2.5D camera | M–L |
| 7. Cut-paper zine | Garage, punk, scrappy indie | Mixed letter sizes and cutout scraps stamp, tear and shuffle into asymmetrical compositions | PixiJS or DOM/SVG; original paper masks | M |
| 8. Wandering word map | Storytelling, rap, spoken word | Words build a spatial map; camera pans, turns and zooms between them | Custom camera/layout; TypeMonkey as a reference/tool | M |
| 9. Ribbon / marquee | Disco, funk, electronic | Lyrics travel around loops, bands, flags or cylinders | Three.js/p5.js; Space Type Generator inspiration | M |
| 10. Elastic cartoon | Playful pop, funk | Letters squash, stretch, spring and answer one another | Anime.js, Leon Sans, authored Lottie assets | M |
| 11. Breathing type | Soul, jazz, organic electronic | Font weight/slant/expression changes with musical energy while phrases hold position | Variable fonts; Anime.js or Coldtype | S–M |
| 12. Poster slam | Aggressive rock, hip-hop | Condensed oversized words arrive from different edges; hard cuts and stacked layouts | DOM/SVG or Motion Canvas | M |
| 13. Collision pile | Chaotic, frantic, comic | Words tumble, collide, hang from constraints and accumulate; current phrase stays readable | Matter.js plus PixiJS | L |
| 14. Broken transmission | Industrial, glitch, abrasive electronic | Text shears into horizontal slices; RGB separation, scanline breakup and abrupt relocations | PixiJS filters or custom shaders | M |
| 15. Liquid / heat haze | Psychedelic, feverish, surreal | Letterforms ripple, stretch and liquefy, then resolve for reading | Blotter reference; PixiJS/custom shader implementation | M–L |
| 16. Particle assembly | Explosive electronic, dramatic drops | Words assemble from dust or sparks, hold for the vocal, then scatter | Three.js or PixiJS particles and glyph masks | L |
| 17. Typographic tunnel | Relentless, maniacal, hypnotic | Camera moves through repeated text planes/rings; focal lyric changes with the vocal | Three.js + Troika | L |
| 18. Living word | Surreal, theatrical, selected hooks | A letter behaves like the word's meaning; a short authored or generated transformation | Dynamic Typography research; Blender/Coldtype alternative | L |

These should have independent controls for **composition, lettering, entrances/exits, camera movement, persistence, texture and energy**. A chaos setting alone will not make a centered caption behave like a sprawling wall.

## 30 existing tools and resources

### Rendering and timing foundations

These produce or orchestrate video; they do not automatically supply all 18 visual styles.

| # | Tool and primary source | Contribution | Integration and terms |
|---|---|---|---|
| 1 | [HyperFrames](https://github.com/heygen-com/hyperframes) | HTML/CSS/media plus seekable animation, captured frame by frame to MP4; supports multiple animation adapters | Apache-2.0 core. Strong candidate for a common browser/export composition. Its dependencies and chosen animation libraries retain their own terms. Must validate long songs, local media and frame seeking in our environment. |
| 2 | [Motion Canvas](https://motioncanvas.io/) · [source](https://github.com/motion-canvas/motion-canvas) | TypeScript scene animation with an editor for syncing visuals to audio | MIT. Strong open-source alternative for text/layout/camera choreography. Its JSX scene graph is not a drop-in React DOM component; requires an adapter to our song/cue data and export workflow. |
| 3 | [Remotion](https://www.remotion.dev/) · [licensing](https://www.remotion.dev/docs/license/pricing) | React composition, preview/player and programmatic video rendering | Strong React fit. Source-available under its own license. Current pricing lists free use for individuals/companies up to three people; larger organizations/collaborations have paid conditions. Automated-product pricing is distinct from manual creator seats. |

**Selection:** first evaluate HyperFrames with native time-driven rendering or Anime.js. Keep Motion Canvas as the MIT alternative if its authoring model is preferable. Remotion is credible if React reuse outweighs its licensing structure. Do not introduce all three.

### Reusable animation, type and graphics components

These are building blocks. Except where stated, they need our own lyric layout, audio-clock integration and video export.

| # | Tool / source / demonstrations | What it makes possible | Main limitation or adoption note |
|---|---|---|---|
| 4 | [Anime.js text tools](https://animejs.com/documentation/text/) · [MIT source](https://github.com/juliangarnier/anime) | Word/character splitting, staggered animation, coordinated DOM/SVG/object timelines | Good general animation ingredient. Layout and song synchronization remain ours. Drive animation from the composition time, not an independent playback loop. |
| 5 | [Motion](https://motion.dev/) | React/JavaScript animation, springs, transforms and layout transitions | MIT core. Useful for restrained presets and the editor; video rendering needs deterministic time control. Optional paid products do not follow automatically from the core license. |
| 6 | [GSAP text tools](https://gsap.com/text/) · [current license](https://gsap.com/community/standard-license/) | Split text, coordinated timelines, elaborate SVG drawing/morphing and camera-like transforms | No-charge custom license, not MIT. It restricts certain competing visual animation builders; its FAQ permits various niche tools. Whether a future visual editor falls inside that restriction is a product-specific question, not a blanket prohibition on Sound / Vision. Anime.js avoids this particular dependency decision. |
| 7 | [PixiJS text](https://pixijs.com/8.x/guides/components/scene-objects/text) · [filters and demos](https://github.com/pixijs/filters) · [core license](https://github.com/pixijs/pixijs) | Accelerated 2D text, sprites, masks, particles, glitch, CRT, bloom and displacement treatments | MIT core. Useful for collage and distressed text. Effects are not lyric layouts; pin compatible renderer/filter versions and check selected dependencies. |
| 8 | [Three.js + Troika text](https://protectwise.github.io/troika/troika-three-text/) · [Troika source](https://github.com/protectwise/troika) | Sharp spatial text, perspective, curved arrangements and scene lighting | Three.js/Troika are MIT. A strong route for tunnels, word maps and text attached to surfaces. Troika's text geometry is not automatically solid extruded lettering; choose other geometry for true solid letters. Font licensing remains separate. |
| 9 | [Matter.js](https://brm.io/matter-js/) · [source](https://github.com/liabru/matter-js) | Rigid-body collisions, constraints, gravity and tumbling word/letter bodies | MIT. Pair with a renderer. A physics engine does not supply glyph design or music timing. Bake fixed-step simulation or replay from deterministic checkpoints so seeks and exports agree. |
| 10 | [p5.js](https://github.com/processing/p5.js) | Creative coding for patterns, text fields, waves, generative layouts and custom animation | LGPL-2.1 library. Useful experimentation environment, not a ready synchronized-lyrics engine. Individual sketches/fonts have separate licenses. |
| 11 | [Coldtype](https://github.com/coldtype/coldtype) · [examples/docs](https://coldtype.xyz/) | Python typography, variable-font manipulation and animation; Blender integration | Apache-2.0. Particularly well matched to unusual letterforms. Upstream explicitly calls the API alpha-quality. Better as an isolated asset/render worker initially than a second interactive browser editor. |
| 12 | [Vara](https://github.com/akzhy/Vara) · [demos](https://vara.akzhy.com/) | Text drawing from specially prepared font paths; handwritten passages with stroke timing | MIT library. Uses custom JSON font data rather than arbitrary installed fonts. Natural handwriting coverage and exact-seek control need an adapter. Check each included/custom font separately. |
| 13 | [Vivus](https://github.com/maxwellito/vivus) | SVG stroke-drawing animation, sequencing and explicit drawing progress | MIT. Good for brush paths, signatures and scribbles. It animates paths supplied to it; it does not invent realistic pen paths for an arbitrary font. |
| 14 | [Leon Sans](https://github.com/cmiscm/leonsans) · [demo](https://leon-kim.com/) | A code-defined geometric font with drawing paths, wave effects, points and variable weight | MIT. Especially useful for neon writing and elastic geometric type. It is a particular typeface, not an engine that transforms every font. |
| 15 | [Paper.js](https://paperjs.org/) · [source/license](https://github.com/paperjs/paper.js/) + [OpenType.js](https://github.com/opentypejs/opentype.js) | Read font outlines, manipulate vector curves and build custom masks, deformation and path layouts | Both MIT. Strong lower-level route for original effects. Font shaping, connections and outline-to-stroke conversion still require care; font files have separate terms. |
| 16 | [Blotter.js demos](https://blotter.js.org/) · [source](https://github.com/bradley/blotter) | Configurable GLSL text effects including channel separation; expressive distortion on individual words | Visually valuable reference. Source is published, but exact license text was not successfully retrieved in this pass. Its documented animation loop uses requestAnimationFrame; export needs explicit time control. Evaluate dependency age and compatibility before adopting it wholesale. |
| 17 | [Lottie / Bodymovin](https://github.com/airbnb/lottie-web) · [runtime license](https://github.com/airbnb/lottie-web/blob/master/LICENSE.md) | Reusable vector animations from authored templates, including letters, accents and transitions | MIT web player; imported animations and authoring tools have separate terms. A transport/player for authored motion, not automatic lyric layout. Validate supported effects and dynamic text before selecting a template. |
| 18 | [Rive text runtime](https://rive.app/docs/runtimes/text) · [runtime source](https://github.com/rive-app/rive-runtime) | Authored interactive vector animation with runtime text updates | MIT low-level runtime; editor/service terms are separate. Good for parameterized art-directed assets. Interactive state-machine playback must be reconciled with deterministic video time. |

### Existing visual libraries to explore first

| # | Resource | What to look at | Reuse status |
|---|---|---|---|
| 19 | [Space Type Generator](https://spacetypegenerator.com/) · [creator](https://www.kielm.com/about) | Cylinder, Field, Stripes, Coil, Flag, Cascade, Ribbon, Layers, Danger, Clutter, Construct, Snap, Flash, Pow, Crash, Vessel, Shine and more | Exceptionally relevant style playground; the creator describes it as open source. I verified the cylinder interface visually. A blanket license for the current whole collection was not established. A [published adaptation of its procedural font](https://github.com/golanlevin/p5-single-line-font-resources/blob/main/README.md) reports CC BY-NC-SA 4.0 for that font. Do not assume all its code/fonts are commercially reusable. Use as inspiration pending per-component clearance. |
| 20 | [Moving Letters](https://tobiasahlin.com/moving-letters/) | Ready examples of staggered lettering, line reveals, scale, tracking and geometric word motion | The page explicitly licenses the letter-animation code under MIT, while retaining separate rights in the site design. Good small effects to adapt to the existing acoustic cues. |
| 21 | [Codrops Kinetic Type Page Transition](https://github.com/codrops/KineticTypePageTransition) | Repeated background letters moving into the foreground and transforming the composition | MIT example code. A page-transition concept, not a lyric renderer. Adapt its spatial choreography; check dependencies and asset licenses separately. |

### Desktop authoring and separately rendered assets

| # | Tool | What it adds | Practical fit |
|---|---|---|---|
| 22 | [Blender text/geometry-node improvements](https://developer.blender.org/docs/release_notes/5.1/geometry_nodes/) | Per-character/word geometry, 3D lettering, materials, camera movement and procedural scenes | Open-source desktop/render-worker route. Best for a smaller number of premium 3D templates. More work to provide a matching interactive browser preview; do not promise runtime speed without a representative render. |
| 23 | [Cavalry](https://cavalry.studio/en/) · [CLI documentation](https://cavalry.studio/docs/applications/cavalry-cli/) | Procedural text animation, duplication, falloffs, dynamics, data-driven sequences and Lottie export | Current site advertises free individual use through Canva on Mac/Windows. Published CLI docs still label rendering Enterprise-only and use older tier names. Treat automated rendering entitlement as unresolved across this transition; do not budget a free unattended Linux service from the desktop offer. |
| 24 | [Glaxnimate](https://glaxnimate.org/) | Open-source vector animation editor with tweening, Python extensibility and Lottie/animated SVG export | Good for making original write-on masks, drawn accents and reusable vector sequences. It does not automatically plan a full song's lyric choreography. |
| 25 | [After Effects + TypeMonkey](https://aescripts.com/typemonkey/) | Generates text arrangements, varied transitions and a camera that follows successive words | Closest turnkey reference for sprawling spatial kinetic type. Paid proprietary AE add-on; not an embeddable open-source library. Default even word spacing is unsuitable for accurate sung lyrics: use our measured timings or marker synchronization. |
| 26 | [Animography](https://animography.net/collections) · [Webster example](https://animography.net/products/webster) | Animated typefaces: letters constructed from strokes, dots, shapes and other designed motion | Excellent way to explore genuinely different letter behavior. Primarily After Effects assets; licenses vary by typeface. Render usable assets or author equivalent original motion rather than assuming a purchase permits redistribution inside our app. |
| 27 | [TypePlay](https://aescripts.com/typeplay/) | Wave-driven After Effects text/property animation, direction controls and preset management | Paid proprietary AE tool. Useful for rubbery or rhythmic typography and external render experiments; not a browser library. |
| 28 | [TouchDesigner Text TOP](https://derivative.ca/UserGuide/Text_TOP) | Text textures inside a procedural visual system, with typography feeding filters and other operators | Proprietary external-tool route for a VJ-style setup. Worth exploring for extreme audio-reactive visual systems; commercial/output terms and automation would need a separate selection check. Higher maintenance than a browser preset for this app. |

### Experimental AI typography

| # | Research project | Verified capability | Why it is not the first full-song renderer |
|---|---|---|---|
| 29 | [KineTy](https://seonmip.github.io/kinety/) · [official code](https://github.com/SeonmiP/KineTy) | ECCV 2024 diffusion research specifically for kinetic text, with text-content and motion conditioning. Upstream reports inference testing on a 3090 Ti as well as A100. | Promising for short designed inserts. Exact license/checkpoint availability was not established here. No evidence in this pass of full-song acoustic alignment, arbitrary-length lyrics or reliable frame seeking. Do not infer Legion compatibility from the 3090 Ti result. |
| 30 | [Dynamic Typography / Animate Your Word](https://github.com/zliucz/animate-your-word) · [demo](https://animate-your-word.github.io/demo/) | Deforms and animates a selected letter within a word to express a prompt; exports SVG frames and rendered animation | Apache-2.0 code, with separate model/dependency terms. Upstream says 20+ frames need at least 24 GB VRAM and its default 24-frame configuration uses about 28 GB. Better for occasional surreal words than hundreds of synchronized lyrics; no local benchmark performed. |

## Font choices deserve their own system

Treat lettering as a separate input to the style rather than keeping only Bold/Soft/Editorial:

- **Soft editorial:** the project's existing Newsreader is a starting point; [Fraunces](https://github.com/undercasetype/Fraunces) is another expressive variable serif to investigate.
- **Handwritten:** [Caveat specimen](https://fonts.google.com/specimen/Caveat) for visual direction; authored stroke assets or Vara for actual write-on behavior. A handwritten-looking font does not automatically contain writing-stroke order.
- **Variable living type:** [Recursive](https://github.com/arrowtype/recursive) exposes changes in expression, weight and slant; its repository identifies OFL-1.1 licensing. Choose axes deliberately so the layout remains controlled.
- **Geometric drawn type:** Leon Sans for controllable paths, waves and weight.
- **Aggressive/damaged display type:** [Rubik Glitch specimen](https://fonts.google.com/specimen/Rubik+Glitch) is a useful visual reference; rough brush, condensed grotesque and custom cutout alphabets supply other distinct directions.

Specimen links are visual candidates, not a completed font-asset clearance. Record the license and glyph coverage of each actual font file when vendoring it. Preserve original lyric case and punctuation unless the user deliberately chooses a casing treatment.

## Recommended implementation direction

**Build one style system with a small number of rendering ingredients.** The user chooses a visual language; the app selects the implementation needed to realize it.

1. **Keep the existing canonical words, acoustic timestamps, edits and original audio.** Word onsets follow the vocal. Beats/energy can drive camera cuts, impacts and environmental motion; they must not replace vocal timing.
2. **Create a persistent composition description.** Store style ID/version, font assets, palette, scene layout, camera path, word lifetimes, per-section energy and a random seed. Style changes should not require redoing lyric alignment or regenerating a satisfactory background.
3. **Use the same composition in preview and export.** Prototype a browser capture path first. Complex new styles should not be independently reimplemented in ASS while hoping the two renderers agree. Keep the existing FFmpeg/libass path for its supported output during evaluation.
4. **Start with 2D/SVG and add specialized rendering only when a style needs it.** Native transforms/Anime.js can cover most editorial, poster and camera-map styles. Add stroke masks for writing; PixiJS for texture/filter work; Three.js for spatial scenes; Matter.js only for collision-based styles.
5. **Offer controlled variation.** Give users a whole-song style and optional verse/chorus/bridge overrides, plus a visible energy control. Suggested matches can use the song's description and measured section dynamics, but users should be able to override them. Unrelated random changes every line will not create a coherent visual identity.
6. **Make expressive styles readable at the sung moment.** Extreme motion can precede/follow the main read interval or affect previous text and surroundings. Current words need an intentional focal point. Provide lower-motion versions without abandoning each style's typography and composition.

The first six pilot styles should be **Quiet editorial, Writing on the wall, Cut-paper zine, Wandering word map, Broken transmission/Liquid, and Collision pile**. They test different layout and rendering needs. Comparing them on the same approved 20–30-second song excerpt would be more informative than producing full-length videos before the styles are chosen.

Before adopting a renderer, verify those pilots at 1080p/24 fps with forward playback, arbitrary seek, repeated rendering, font loading and exact audio duration. Test 16:9 and 9:16 separately. For simulation or shader effects, ensure a requested frame does not depend on the browser having played all earlier frames at wall-clock speed. These are proposed acceptance checks, not tests already run.

## Decision

There is no need to switch the whole pipeline to another video-generation model to achieve the requested range. Most of the useful variety comes from **typography, scene layout, persistence and choreography**. Keep H3 available for atmospheric backgrounds or selected inserts; use a controlled text composition for editable, precisely timed lyrics.

The most useful first browsing stops are **Space Type Generator** for spatial variety, **Vara** for handwriting, **Blotter** for distortion, **Moving Letters** for restrained motion, **TypeMonkey** for moving-camera text, and **Animography** for letterforms with their own animation.

Research completion: inspected the workspace implementation; identified and sourced 30 tools/resources; mapped 18 proposed styles; recorded integration and licensing distinctions. No production code, provider settings or dependencies were changed, and no paid generation or software purchase was made.
