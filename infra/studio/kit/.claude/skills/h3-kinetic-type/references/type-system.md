# Type system for H3 prompts

A condensed English rewrite of MiniMax's typography library (`h3-visual-design/references/typography-system-library.md`
and the `mv` workflow's `typography-packaging.md`). H3 can't look up a font, a style name or a code like "E1": everything
below has to be written into the prompt as visible properties (skeleton, width, weight, terminals, counters, tracking,
case, material, color, size, place, motion).

## Roles

Two kinds of hierarchy, kept apart:

**Type cast** (the whole song, never swapped between shots):

| Role | Job | Rule |
|---|---|---|
| Display A | The hero word or phrase, the largest and most complete | One skeleton for the whole song |
| Display B | A second phrase, a different line of the lyric | Contrasts with A on at least two axes: weight, width, straight/curved, serif/sans, solid/outline, printed/handwritten |
| Utility | Small, stable text (a short label, a credit, a section name) | Only when there is real text for it; otherwise leave it out. On H3 at ~1024 px, prefer to draw it in code |
| Marks | Graphic rhythm without new words: frames, rules, dots, halftone, arrows, scratches, grain, or outline/cropped repeats of a word already on screen | Never invented letters, numbers, codes or fake UI |

Shots shorter than ~6 s can use Display A plus Utility only. Fusing two scripts into one glyph block is never allowed.

**Layers of one text event** (one word appearing once):

- Layer A, hero base: the complete word at its largest readable size.
- Layer B, style echo: the same word again as the style's echo (offset overprint, outline copy, projection, CRT ghost,
  sticker edge). A different phrase is a new event, not Layer B.
- Layer C, action/foreground: fragments of the same word, utility text or marks travelling with the performer, the camera
  or the foreground.
- Layer D, occlusion/recovery (only when needed): someone passes in front, or a counter becomes a doorway, and the word
  comes back complete afterwards.

Write each layer with its share of the frame, depth (front/mid/back), the second it appears, how long it stays readable,
its one change, and where it goes.

## Scale ladder

| Level | Share of frame width | Use |
|---|---|---|
| Full-frame hero | 75–130% (may crop past the edges once it has been read whole) | One takeover per shot at most, in the first 20–40% of a long shot |
| Hero | 45–120% | The normal hero size |
| Mid | 18–55% | Display B, a spatial title on a wall |
| Small | 6–18% | Utility, labels; code-drawn when exact |

At most three sizes in a frame (motion-studio's rule too). After a hard hit, leave 0.35–1.0 s of complete reading.

## Latin skeletons (pick by the song's mood)

1. **Extra-condensed impact grotesk**: width 55–72%, weight 850–950, straight cut terminals, tight tracking, clear rectangular
   counters, ALL CAPS. Pressed in from a frame edge in 0.12–0.24 s, readable 0.55–1.0 s, squashed to 82% height for two
   frames, back, hard cut. Black/warm white plus red, acid green or electric blue. Impact, rap, dark styles.
2. **Wide geometric sans**: round O, open C/G, weight 650–820. Tracking opens on one baseline, settles in 0.35 s, one light
   sweep, exits at normal tracking. Cold white on navy with cyan, or cream with mint and ink. Tech, clean futures.
3. **Neutral neo-grotesk**: weight 550–800, normal width, open counters. Slides in 0.05–0.12 s before the stressed syllable,
   holds while sung, its plate grows 6–10% once. Spoken lines, calm captions.
4. **High-contrast editorial serif**: hairline horizontals, heavy verticals, sharp serifs. Thin strokes draw, thick strokes
   fill, hold 0.8 s, one 112% vertical stretch, wiped off by light. Paper white/ink with wine, ultramarine or warm metal.
5. **Slab serif block**: even heavy strokes, square feet, weight 750–900. Lines slide in whole, snap to one grid, 2–3 frame
   shake, hold, leave by the reverse path. Industrial, collage.
6. **Monospaced technical**: medium weight, slightly wide tracking, only real labels. A thin line grows from a real object
   edge, the whole label appears at its end, one scan, line and label retract together.
7. **Rounded soft grotesk**: rounded terminals, wide body, weight 700–850. Arcs in at 86% scale, 106%, settles at 100%,
   leaves by the same arc. Cream, cocoa, mint, apricot, coral. Friendly, cute.
8. **Modular stencil sans**: geometric modules with 6–12% safe gaps, weight 700–900. Short words only.
9. **Chunky playful display**: very heavy, uneven widths, rounded corners with a few sharp ones. Lands on its baseline, the
   biggest letter stretches to 115% wide for 0.18 s, returns, a rounded frame takes over.
10. **Marker or brush hand**: uneven stroke, visible start and end of each stroke, slanted 2–8°. Only for a short Display B
    or marks: written in one direction, held 0.7–1.0 s, the stroke runs on into an underline or frame. Never long lines.

## CJK skeletons (Chinese; the same logic holds for Japanese and Korean)

Keep radicals whole, stroke crossings clear and the square center of gravity. Compress horizontally by 12–15% at most. Reveal
a whole character or word, never stroke-by-stroke flicker.

- Ultra-bold square black (2–4 characters, 55–120% of the frame): pressed in whole, read, sliced into 3–5 strips once, restored in 2–4 frames.
- Geometric rounded black (2–6 characters): groups pop in and form the word within 0.4 s, one rebound for the whole word.
- Modern Song/Ming serif (2–6 characters, vertical or staggered): thin strokes first, then thick, hold 0.8 s, wiped by paper or glass.
- Narrow black (2–8 characters, vertical columns): revealed by a scan line a whole character at a time, one contour pulse.
- Heavy brush: emotional hero or Display B only, slant at most 8°, dry-brush texture never breaks a radical.
- Humanist black: captions, one meaning-unit at a time, one or two lines.

## Mixed scripts

Choose a main language and an editorial language and give them different roles. Main language at 100% height, the other at
22–45%; a later state may promote the second to 55–85% while the main becomes Utility. Separate baselines, one shared
alignment edge. The two languages say different things; no line-by-line translation. If a word is Chinese on screen, don't
put an English synonym in the same event: the model swaps scripts.

## Palettes (MiniMax's, each color has a job)

| Name | Background | Hero | Accent | Support | Fits |
|---|---|---|---|---|---|
| Ink Signal | `#050505` | `#F4F2EC` | `#FF2B2B` | `#9A9A9A` | Cool art |
| Blood Zine | `#050607` | `#F4F1EA` | `#E82018` | `#77706B` | Dark-pop glitch |
| Acid Night | `#07090D` | `#F6F5EE` | `#C7FF2E` | `#8D96A3` | Tech, art |
| Electric Lab | `#071726` | `#EAF6FF` | `#22D3EE` | `#6F91A6` | Tech particle |
| Cobalt Paper | `#F2EBDD` | `#101010` | `#2457D6` | `#6D665B` | Poster collage |
| Brick Print | `#F7F5EF` | `#111111` | `#D94A3A` | `#81796F` | Editorial poster |
| Mint Cream | `#FFF6E8` | `#173F36` | `#78DCC6` | `#FFAA73` | Fresh cute |
| Coral Milk | `#F7FBFA` | `#3A2C2A` | `#FF7F96` | `#FFD86B` | Fresh cute |
| White Gallery | `#F4F4F0` | `#151515` | `#275DFF` | `#777777` | Minimal |

When the cover or footage already has a strong color, sample the accent from it and keep the rest neutral. A color script
keeps the same 3–5 colors and writes 2–3 states: (1) base; (2) the accent takes the background and the hero reverses;
(3) back to base with one accent frame or underline. Change color by a block taking over, a page turning, light wiping in or
a hero takeover, never by a random filter.

## Graphic kit (2–4 per song, reused everywhere)

Thick frame; partial corner frame; 2–5 short marks; paper strips; 2–4 panels or columns; color blocks; rings; dot grids and
halftone; transparent or frosted plates; a thin grid plate; a baseline or underline; arrows; content doodles. For each:
where it starts (a real edge, a seam, a highlight, a beat), what text it carries, where it settles, how it leaves or becomes
the next state's wall.

## Space

**Binding modes** (one per text event, kept until the word leaves):

| Mode | What it means |
|---|---|
| World-locked | On a wall, floor, glass, screen or stage; keeps perspective, parallax, light and real occlusion as the camera moves |
| Lens-locked | Fixed to the frame while the world moves behind; only for utility, interface or one full-frame takeover |
| Subject-bound | On its own plane following a performer's contour, a prop or a path; never stuck to the face or body |
| Transition carrier | A counter, stroke, panel or 3D letter fills the lens for an instant and becomes the next shot's entrance |

**Relations to write:** in front of / behind the subject; who covers whom and for how long; attached to floor, wall, glass,
paper or frame with one vanishing direction; along a contour at a safe distance; mirrored in a reflection; across two planes
sharing one vanishing point (a type corridor the camera travels through); a counter or frame as a portal.

**Spatial proof:** a text event counts as spatial only with at least three visible proofs, one of them an occlusion by a
person or foreground object, and one of: perspective foreshortening, parallax, visible side thickness, contact shadow,
reflection/refraction from the same source, a focus change across depth. "Feels 3D" is not a proof.

**Path of a spatial word:** DISCOVER (the camera, a move, a light or a mask reveals where it comes from) → ATTACH (to a surface
or its own plane) → TRACK (keeps one vanishing point as the camera moves) → OCCLUDE (only after one clean read) → TRANSFER
(hands direction or shape to the next subject or shot) → SETTLE (comes to rest, re-forms or exits cleanly).

## Motion mechanisms (choose 2–4 per song, 1–2 per shot; never all at once)

1. **Full-frame takeover**: a word grows from ~30% to ~110% width in ~0.25 s, holds complete ~0.55 s, a real silhouette passes in front, it settles smaller in the background.
2. **Depth exchange**: subject in front, word behind; the word crosses into the foreground through a carrier or negative space; ends with both readable.
3. **Scale ladder**: one word at a time, small → hero → cropped hero by hard cuts, each held ≥0.35 s, no echo copies left behind.
4. **Split-stack assembly**: a phrase in 2–3 meaning-lines, from different sides onto one grid; once complete it moves as one block.
5. **Contour wrap**: a word on its own flat plane beside the subject, a baseline following no more than a quarter of the outline, letters face the camera.
6. **Counter-rotation**: the subject turns 90°, the word block only 6° the other way, then locks back to 0°.
7. **Material pass**: a light, airflow or paper edge crosses a solid word once, changing only the passed area (outline, ink, glass, particles); the word is whole and solid again before it leaves.
8. **Typographic portal**: a letter's counter grows to fill the frame while the word stays readable for the first half; the camera passes through; the same word doesn't reappear right after.
9. **Baseline from a trail**: a moving light or ink trail straightens into a baseline, the word grows up from it, holds, collapses back into it.
10. **Annotation**: a line grows from a real object to a label position, then the label appears; they leave in reverse order.
11. **Type corridor**: the hero across floor and back wall sharing one vanishing point; the camera travels between its strokes and reveals it whole on the far wall.
12. **Multi-panel poster**: 2–4 panels (subject, hero, second line, texture) snap to one grid in 0.25–0.45 s, hold, one panel expands to become the next state.
13. **Repetition field**: one word repeated in a 2×3 or 3×4 grid as outlines, one solid copy as the reading focus; a wipe leaves the solid copy for the next state.
14. **Glyph to graphic**: the complete word first, then one stroke, counter or outline enlarges into a frame, divider or mask, keeping enough of the word to stay recognizable; the word returns in a new size or color.
15. **Kinetic letter field**: one solid readable word, its spare letters scattered through depth along the performer's or camera's path, gathering back into the word or leaving.
16. **Window choreography**: words and picture in panels or windows that cascade, expand and take over full frame; one main window always holds the reading.
17. **Shape-mask reveal**: a circle, a silhouette or a real counter becomes the window to the next picture, then expands to complete the cut.
18. **Volumetric title**: a short word as a real object (chrome, inflatable, glass, soft plastic) lit by the scene's light, occluded and touched; it turns or squashes only after a clean read.
19. **Continuous letterform morph**: one outline stays traceable as it becomes an object, a shape or the next word.

## Motion verbs

- **Enter**: press in from an edge; slide and snap to a grid; scale up from small; mask reveal behind a bar, card or window;
  scan reveal (a line wipes and leaves the word behind it); write-on; thin strokes then fill; particles gather into the
  shape; typewriter (typing, prompts, code only); slot or flip-board replace; ride a path or arc; fly in on the Z axis
  (rarely, and readable).
- **Respond** (once, after the read): squash to ~82% height for two frames; stretch to ~112%; pulse 106–112%; three-strip
  slice with the middle strip offset ≤4% of a letter for 2–3 frames; registration offset 3–6 px for 2–3 frames; one outline
  pulse; one light sweep; accent color takeover.
- **Exit**: reverse mask; shrink into an anchor point that becomes the next object; slide out with motion blur in the next
  shot's direction; hard cut; slice apart; tear like paper; particles back to their source; fly past the lens; break into
  unreadable fragments (the only legal leftover after a lyric's window).

Every event: `cue → enters → complete and still (readable hold) → one response → depth or layout change → settles or exits`.
A state: `cue → carrier enters → type locks to the grid → hero readable → one focal response → an element becomes the next
state`. An effect: `source → path → contact → destination`; nothing appears from empty air.

## Camera and type together

| Camera or action | Type response |
|---|---|
| Push-in, crash zoom | Tracking tightens or weight/size grows, settling exactly when the word is complete; one beat only |
| Pull-back, reveal | From a cropped stroke out to the whole title, then its place in the space |
| Dolly zoom | Subject size holds while letter width, spacing or background type depth stretches |
| Whip pan | Brief smear or slices along the whip, the word re-forms whole in the next shot, same direction |
| Rack focus | Soft translucent type becomes sharp solid, or hands the reading back to the person |
| Orbit, camera roll | Flat type keeps its real orientation, 3D type shows its side; ends at a readable angle |
| Hit, step, instrument contact | One compression, expansion, crack, glow or color takeover from the contact point, then rebound or exit |
| Handheld, frame skip | Limited shake inherited by the type, steady again for the readable hold |

## Cues from the music

One cue per main text event, chosen from: downbeat, snare, 808/bass hit, instrument hit, lyric hook, texture swell, breath,
gesture contact. Hi-hat roll → micro shake, a skipped frame, a small reassembly. Snare → hard cut, word punch-in. 808 or bass
→ low compression, stretch, flash. Sung keyword → the word's reveal. Swell → material or letterform morph. Breath or silence →
the readable hold and the clean-up. Never make every word jump on every beat.

## Choosing the words (lyric videos)

The words are the locked lyrics, so the craft is choosing which ones go big: the title, the repeated hook, a strong noun, the
first words of a section, the line on the energy peak. One main word or short phrase per shot; 2–4 new readable words per
12–15 s; reuse established words so the hook escalates (new space, scale, material, occlusion or exit; same type cast). A
short word reads better than a long line; a long line is split by meaning, never squeezed.
