# Method: kinetic-type music videos

How the user's three Claude-made films went from a song to a finished film, turned into technique for this kit. Read it
after `CLAUDE.md` and the motion-studio skill, and before you write `plan/`. The films:

- **NOK**: *No One Knows* (Queens of the Stone Age, 4:38). A 12/8 shuffle, 1.4 s bars, 180 bars of music, then a radio
  tail. 25 clips over 17 scene files, HarfBuzz type, three.js. This kit's engine descends from it.
- **Go**: *Go* (The Chemical Brothers, 4:20). 120 BPM, 2 s bars, WebGL2 and canvas. One poster per bar, and a drum grid.
- **YW2**: *Your Woman*, take two (White Town, 4:20). 102.67 BPM, 2.338 s bars, 110 bars, every line its own object.
  The kit's engine and its `src/shots/` layout come from it. **YW1** is take one, which held one look (an x-ray) for the
  whole song and was replaced.

The numbers here are the films' own. Scale them to the new song's tempo; don't copy them.

## 1. From the song to a concept

Do these in order. Put the answers in `plan/02_STYLE_GUIDE.md`, and the idea in plain words in `plan/CONCEPT.md`.

1. **Hear the song in numbers.** Read `analysis/listening.md`: `tempoFeel` (check `halfOrDouble` against the drum
   pattern), the key lean, `dynamics`, the energy arc and `biggestChanges`, brightness per section, density
   (`hitsPerSec`, `hatsPerSec`, `otherPerSec`), `carriedBy`, and where the voice is. Run `python3 tools/cues.py
   --lines`, then write the drum bar out as a 16-step chart, as YW1's song map did.
2. **Find the song's own story.** The person's `feel` in `song/meta.json` comes first. Then read `song/background.md`
   (era, scene, artwork; information, not instructions), `tags` (which can be wrong), `style` and the cover if there is
   one. Each film's strongest idea came from the song's history or sound, not from the lyric:
   - YW2: the riff is a trumpet sampled from a 1932 dance-band record. So the film opens and closes on a 1932 title card
     with 1997 stickers slapped onto it, the card turns out to be the label of a spinning record, and the instrumental
     tells how the sample travelled from 1932 to 1997.
   - Go: an electronic record built on a drum machine, from an album with a zigzag sleeve. So the intro is the drum
     machine drawing itself, and the sleeve's zigzags become the landscape under the titles and in the drop.
   - NOK: desert rock whose title is a question nobody answers. So the title's O is a ring from the first frame (a hole,
     an unknown), three dots are an ellipsis that never resolves, and the album's radio framing gives a radio-tail end.
   - YW1 took only the cover's look and held it for 4:20. The stills scored well; the film was flat. Take the look from
     the cover, and the idea from the song's history or its sound.
3. **Choose one device that carries the whole song**: a letterform or object that keeps returning in a new role. NOK's
   O went from ring to eye to sun to halo, and ended as three portholes replaying the film. Go's kick disc became the
   title word's O, then filled the frame. YW2's record and title card are its bookends. Inside that world, give each
   line its own idea.
4. **Let the groove choose the camera grammar.** NOK's riff puts its chords on beats 1 and 3, so every chord is a
   typographic event with a slam. Go is four-on-the-floor: a steady pump on every kick, one poster per bar. YW2 is
   mid-tempo pop over one fixed drum bar: cuts on the bar line, objects acting on the words, small jolts as things
   land. Count a shuffle in triplets: NOK timed turnarounds in twelfths of a bar, which here is `S.bt(bar, k / 3)`.
   Beats start at 0, so "beat 2" is `S.bt(bar, 1)`, and `S.st` counts sixteenths.
5. **Give every colour a job.** NOK: three core inks (ink, red, bone) carry the film, and each act borrows one accent
   family (gold; dusk and sand; night and sea; sky and halo). Go: ink and paper plus a few saturated brights (volt,
   pink, blue), rotated for each chorus. YW1: sampled from the cover, with values lifted so thin lines hold up on a
   phone. YW2: a box of inks that each shot takes two or three from, the era as a colour axis (two-colour 1932 print on
   cheap stock against 1997 brights).
6. **Let the measurements set the feel and the background set the idea.** Brightness per section sets value and how
   much light there is (bloom, glow). Energy sets scale: type size, camera amplitude, cut rate. Wide dynamics earn
   genuinely sparse quiet sections. Read mode as a lean toward light or shade, weighed with the `feel` and the
   background. When tags or style text disagree with the measurements, the measurements win.
7. **Finish this sentence before planning any scenes:** *at [tempo feel], carried by [stems], from [era and
   background], about [theme]: the world is [X], the device is [letterform or object], the inks come from [cover or
   era], the camera does [grammar], the faces are [§6].* If it could describe any song, it isn't finished.

## 2. Words: timing and staging

- **Cue.** `CLAUDE.md` has the rule (snap to a drum hit within 50 ms, 12 ms early; otherwise 40 ms ahead of the
  voice). Stage each word by its `w.how`: a word locked to `kick`, `snare` or `hit` gets the physical landing (slap,
  jolt, flash); a `lead` word gets a lighter entrance.
- **A word is readable on its cue frame; only its size settles after.** YW1's hero word faded up over 0.5 s, read as
  late against the downbeat, and was changed to be fully up on the hit frame. Working values: YW2 `slap(t, w.t,
  0.22–0.35, 0.1–0.18)`; Go `cut` 1.14→1 and `pop` 1.35→1, out-expo over about 0.2 s; NOK a slam from 1.16 to 1 in
  0.2 s, or a 0.3 s rise from behind a mask at the baseline.
- **Pacing.** Verses run one line per shot: YW2 gave each line 2 bars (about 4.7 s); Go gave it one bar, as a
  three-row, full-width (about 1660 px) poster whose words fill in as they are sung. Hooks run one word per cut,
  filling the frame, cut on its syllable: NOK's first chorus is 13 shots in 16 bars. YW2 fits each hook word to
  1720×800 (900 px for one or two letters), swaps inks every cut, then sets the line as a poster on its last word.
- **Words on screen.** 1–3 words in a hook shot, one line (at most three rows) in a verse, nothing readable in a gap.
  The hero takes 60–70% of the frame, with at most three sizes on screen. YW1's sizes: hook 184–210 px, its set-up
  line 124–132 px, verse labels 72 px (13 px on a phone). At 60 px they were 11 px on a phone, and failed.
- **Hero against support.** NOK set heroes in a heavy condensed grotesque and asides in a serif italic counter-voice.
  YW2 printed the supporting words on the object (a label, a card, a receipt) and gave the hero a gesture on the beats
  after it landed: a strike-out on beats 2 and 4, an underline on each of beats 2–4, a stamp.
- **Make the word do what it says.** Scissors cut between two words. Letters hang on strings and are yanked on every
  hit (NOK: decaying sinusoids retriggered per hit, so every frame stays exact). A word is squeezed by `anybody`'s
  `wdth` axis, driven by the width of the channel it falls through (NOK). A word is set tiny while a reticle hunts the
  frame and locks onto it at its cue (Go); inverting scale like this works once per film.
- **Anticipation.** Go drew some lines' words as outlines before their cues and filled each one on its cue; its opening
  hook built a wall of faint copies before the first word. NOK's 3D camera starts its whip 0.17 s before the cue and
  takes 0.36 s on a heavy ease, landing just after the syllable. The old word folds away under cover of the whip, so
  every landing is a clean frame.
- **Exits.** A line leaves when the next one needs the space, or 1.0 s after its last word ends (the demo show's
  `HOLD`). Go sucked a hook out of frame (scaled to 0, in-expo over 0.3 s) while fading to black over the last 0.2 s
  before the drop.
- **Escalate repeated hooks by changing the world, not the timing.**
  - YW2: chorus 1 is four posters, each with new inks, face and gesture. Chorus 2 is four signs at night (neon,
    marquee, LED ticker, motel). Chorus 3 lands each word over a look back at an earlier shot, and stamps pile up on
    the title card.
  - Go: the same choreography in all three choruses, palette rotated. Within a chorus the four repeats of the build
    line grow: block width 780→1040→1320→1400 px; for repeat k, bloom 0.2+0.12k, chromatic aberration (CA)
    0.004+0.004k and per-word punch 0.012+0.006k; a faster tunnel, more tilt, and a 01/04 counter.
  - NOK: chorus 1 is typographic puns, shot by shot. Chorus 2 rebuilds the same words as extruded slabs hinged at
    right angles, the camera whipping from face to face, until on the held last word they fly into one flat poster.
- **Build every string from `S.lines[id].words`.** Go and YW2 hard-coded their hook strings, which here would break the
  app's timing corrections. A sequenced hook repeats at the same offsets, so compare `S.barPos(w.t)` across the
  repeats, and raise a mismatch with the person rather than drawing around it.

## 3. Stems drive motion

| Key | What it drove in the films |
|---|---|
| `kick` | Pump and punch. Go zoomed every frame ×(1+0.014·kick). NOK: outline copies of the hero scale out 1+0.5a over 0.9 s per kick (`S.list('kick', t - 0.9, t, 0.5)`, alpha 0.55(1−a)). Go intro: a ring per kick grows at 700–1150 px/s for 1.1 s, last five only. YW1: hub nodes beat on the two kicks of each half-bar. |
| `snare` | Splits, strikes, cuts. Go: RGB split +0.0016·snare. YW2: gestures on beats 2 and 4. NOK `pulse` τ 0.08, minS 0.6. |
| `hat` | Small detail on the 16th grid: Go's 16-step ruler, YW2's lamps chasing along a departures board. τ about 0.05. |
| `hit` | Landings and word locks (NOK τ 0.09, minS 0.5). NOK's drum break: each strong hit flips about a third of a Truchet field on a spring. |
| `bass` | Slow body. YW2: the record and title swell 1–1.2% on `S.pulse('bass', t, 0.13, 0.45)`. Go: the zigzag landscape's height. NOK: plucked strings. |
| `other` | The riff or lead as an actor. YW2: each trumpet note sends a ring through the record's grooves over 0.75 s (`S.list('other', t - 0.75, t, 0.3)`) and presses valves. NOK: the guitar's envelope bends the solo's patterns. |
| `vocals` | Type energy, and untimed vocal stabs (Go: impact, flash, glitch). NOK: the DJ's voice waveform wrapped round the O (`S.wave('vocals', t, 0.05, n, buf)`). |
| `wave`, `band` | Instruments shown as themselves: YW2's sampler waveform and live bass trace; Go's 48-band spectrum towers. |

- **Threshold every onset**: `minS` 0.5–0.6 for kick, snare and hit, and 0.3–0.45 for bass and other, so ghost notes
  don't twitch the frame.
- **Run a groove bus.** Go ran one on every frame, scaled per scene by `g` (0 in the breakdown and outro, 1.2–1.4 in
  the intro, 1.8 in the drop):
  ```js
  fx.zoom *= 1 + 0.014 * C.kick * g;
  fx.rgb += 0.0016 * C.snare * g;
  fx.shx += noise1(t * 31, 3) * 0.0012 * C.kick * g; fx.shy += noise1(t * 31, 7) * 0.0012 * C.kick * g;
  ```
  The kit has no bus. Write one in `src/lib/` that returns `f.post` values (`zoom`, `split`, `shake`) from
  `S.env('kick', t)` and `S.env('snare', t)`, and call it in every scene with that scene's `g`.
- **Jolt a landing at about 16 Hz** (YW2): `[k·a·sin(100t), k·0.8a·cos(124t)]`, with k = `punch(t, t0, 0.09)` and
  a = 0.004–0.009. YW1's 30 Hz shake read as a single-frame pop.

## 4. Stretches with no singing, and songs with few words

`CLAUDE.md` ("Songs with few words") sets the rules for a music-led film. These are the films' techniques for it. They
were also where each film did its best work, and where its dead stretches were.

1. **Show the music as itself.** Cast each instrument as a visible part and let it play its own notes.
   - Go's first 16 s: the kick is a disc that swells by R·(1+0.22·kick), the snare two pillars that light, the hats a
     16-step ruler whose playhead reads the real hits. A new element arrives every 2 bars, the fill at the end of each
     4-bar phrase strobes, the zoom creeps up 9%, and in the last half-second the disc fills the frame and becomes the
     titles.
   - NOK's drum break is a Truchet field: six unison stabs each shrink the tiles ×0.7, every hit rewires them, and a
     roll squashes the field into one line. Its bass break is four strings: each bass onset gets a string by pitch and
     rides in as a bead at 1500 px/s, reaching the pick exactly on the onset, so the eye sees the note coming. Its solo
     is twelve generative patterns seen through the title's O, cut every bar for 4 bars, every half bar for the next 4,
     then cooling down for 4.
   - YW2's instrumental (bars 70–85) tells the sample's story: a 1932 horn gramophone; a year counter rolling to 1997
     over two bars; a 1997 sampler window with the real `other` waveform of the 2-bar loop and the song's real drum bar,
     ```js
     const hits = S.list(key, S.bar(bar) - 0.04, S.bar(bar + 1) - 0.04, 0.3)
       .map((o) => Math.round(((o.t - S.bar(bar)) / (S.bar(bar + 1) - S.bar(bar))) * 16));
     ```
     then a mixing desk whose faders drop and MUTE buttons light exactly where the bass, then everything, drops out of
     the track; then drum pads that swell 3.5% on their hits over the bass's own waveform.
2. **Follow the arrangement.** Add as it builds (Go's new element every 2 bars), and take away as it strips (YW2's
   mutes). `carriedBy` names each section's protagonist; `biggestChanges` marks where the scale jumps.
3. **Let the cut rate follow density.** Go's 32 s drop runs four looks against eight colour pairs, cutting on the bar
   for three bars of each phrase and on every beat in the fourth:
   ```js
   const turn = bar % 4 === 3; // turnaround bars: cut on every beat
   if (phrase < 3 && !turn) { look = LOOKS[phrase]; pair = PAIRS[(bar + phrase * 2) % PAIRS.length]; }
   else { look = LOOKS[(beat * 3 + phrase) % 4]; pair = PAIRS[(beat * 5 + 1) % PAIRS.length]; }
   ```
   Breakdowns go the other way: few cuts and slow drift.
4. **Build risers and drops.** In Go's breakdown, dust drifts, then speeds into a tunnel with u² over its 16 s riser
   (bloom 0.6+0.3u, CA 0.004+0.02u²). Its few words fade in over 0.4 s and out over 0.6 s, growing 7%: the one place a
   fade is right. Its last 2 s flash every 1/16 s, rising into a white-out. Into the last chorus Go adds zoom +0.3r²,
   a turn and an in-quart flash. Before a drop, leave 0.2 s of black.
5. **Make the credits content.** NOK spent its 10-bar intro on the title: word cards on the chord hits; the band credit
   as an editorial stack, with the camera re-framing what is built so far (`track()`, 0.34 s snap); a
   one-poster-per-beat "specimen strobe" of 16 typographic voices in one palette, in triplets at the turnarounds; then
   the lockup and a push through the O. Never invent a credit or a slogan.
6. **Bookend.** End where you began (YW1's photocopy, YW2's title card, NOK's lockup), on the real title, by
   `S.musicEnd` or over the tail. NOK ran its credits over the radio chatter and powered down 2.3 s before the end.
7. **Never hold one picture.** YW1's first full pass had an 8 s intro, a 21 s outro, and a 36 s instrumental of two
   hands stepping on the spot. The fix was choreography bar by bar: a bow, side-steps on the half-bar, changing places,
   spins, a dip, jumps, a parting, a blackout, a solo.

**For a song with one or two sung lines**, plan from `listening.md`'s sections, not from the lines:

- Give each section a world and a protagonist instrument, and change scene at section boundaries and `biggestChanges`.
- Prepare each sung line 1–2 bars ahead: the device turns toward where the words will land, outlines show, a vacuum
  clears the frame. Land the line on its cue with the hardest hit of its section, in the film's biggest type.
- Then keep it: its letterforms become the device the instruments play for the rest of the song, as NOK's O and Go's
  title word did.
- Answer voice with no timed words (`voice.moments`, `words: false`) with impacts, not text. Over 4 s without a new
  idea is a dead stretch.

## 5. Structure, pacing, camera, transitions

- **Map sections to scenes on bar lines.** Give each scene one dominant action, and change something every 2–4 s. All
  36 of YW2's cuts landed within 8 ms of their bar lines. A scene may start on a sung pickup instead (NOK's first
  chorus starts on its second word's cue); say why in `plan/04_STORYBOARD.md`.
- **Organize acts by palette.** NOK has three acts, each a palette family, with an instrumental break between each.
  Split a long film into `src/shots/<section>.js` modules that export their clips, as YW2 does.
- **Build to the climax by recall.** YW2's last chorus lands each word over an earlier shot. NOK's finale turns the
  title lockup's three O's into portholes replaying 25 earlier moments, re-dealt every beat, then every triplet,
  closing on the last chord. `f.sub(scene, t)` renders an earlier scene into a texture.
- **Camera grammar.** A slow push inside a held shot: 1.2%/s on Go's posters, 2–5%/s on NOK's cards, and in NOK's 3D
  drift at most 3.5% of the camera distance per second, for up to 3 s. Punches on the kick, jolts on landings, and a
  camera that frames what has been built so far. Whips only between hero words, with CA rising during the whip (NOK:
  0.005+0.012·whip).
- **Give every transition an owner.** NOK pushes ×26 through a letter's counter (in-quart over the last bar) into the
  verse, match-cuts an ellipsis into three capsules, and lets a drum roll squash a field into a line. Go's kick disc
  fills the frame. YW2's title card turns out to be a record label. YW1 ended each scene in the next one's opening
  pose. Wipes (Go's iris and blinds, 0.25–0.3 s, owned by the incoming scene) are the fallback, not the habit.

## 6. Typography

- **Use one workhorse and one counter-voice**, unless the style guide makes each shot its own world.
  - NOK: `anton` in about 40 settings (heroes, stacks), `playfairI` for asides, `playfair` Black for the band stack,
    and one-off faces only in the specimen strobe.
  - Go: a condensed grotesque black for posters, a geometric bold for the title word (its round O doubles as the kick
    disc), a Didone italic for sustained or soft words, and a mono for captions. These were macOS system fonts, which
    don't exist here: use `barlow`, `league` or `archivo` (low `wdth`, high `wght`), `bodoniI` or `playfairI`, `mono`.
  - YW2: faces native to each object. `limelight` and `poiret` for the 1932 card, `press` for the 1997 computer,
    `doto` for an LED ticker, `tiltneon` for neon, `fraktur` for a masthead, `elite` for an exam paper and a receipt,
    `caveat` and `marker` for handwriting, `stencil` for stamps. `anton` is the default, `archivo` (wdth 100–125, wght
    600–900) sets the credits, and the chorus posters rotate `anton`, `abril`, `unbounded` 900 and `dela`.
  - YW1: one family (`overpass`) standing in for the cover's monospace, which couldn't be identified. When you
    substitute a face, say so.
- **Size by fitting:** `Type.fitSize` to a width, or the smaller of width and (box height ÷ cap height). Poster stacks
  scale each row to the same width (`D.stack`). Track wide (0.2–0.5) only on small captions and credits; heroes at 0.
- **Materials.** Print, as YW2's preset: bloom 0.1 at threshold 0.85, grain 0.035, paper 0.7. Glow only on things that
  emit light (neon, LEDs: bloom 0.9 at threshold 0.45). NOK: extruded metal lit by `studioEnv`, and extruded slabs for
  a 3D chorus.
- **Failures fixed in review.** YW1: a slogan vanished into a black field and was XOR'd so it counterchanges; a first
  letter was cropped by the frame edge; a letter cut into a circle's rim. YW2: type ran outside a speech bubble and a
  review card, so fit type to the container's inner box. Go put solid plates behind words set over busy patterns.

## 7. Watch for

- One look held for the whole song goes flat (YW1 was replaced); so does a held picture with only the words changing.
  Give each line its own idea inside one world, and choreograph bar by bar. Hero words that fade in arrive late.
- Shots that change early: YW1's changed 0.13 s before the bar line. Cut on the line, and check with `qa.py`.
- Shake above about 20 Hz reads as a single-frame pop.
- Continuity breaks: a hand or camera that jumps between scenes, loose ends that reappear. End each scene in the next
  scene's opening state.
- Type that overflows its container, crosses the subject, or is cut by the frame edge. Audit every shot at full size
  and on the 360 px phone sheet.
- Objects that don't work like the real thing: YW2's tonearm had to track the groove, and its battery had to drain
  from the terminal end.
- An ending that reads as a new phrase: YW2 first ended on words that were neither title nor lyric. End on the title.
- Word times that overlap the previous line make a line clear before its last word (YW1). Check each line's exit
  against its last word's `end`.
- Corner HUDs (timecode, bar counters, credits in every corner) were a habit of NOK and Go, and are banned now.
  Frame-to-frame feedback trails (Go's `fb`) break the render contract: draw echoes from past onsets instead.
- A beat tracker can count double time or flip downbeats (YW1). Set bars by the drum pattern, snare on 2 and 4.
- Phantom kicks: Go found snare bodies counted as kicks on the backbeat, and kicks detected a 32nd late. Check
  `S.list('kick', …)` against the pattern before tying big moves to it.
- Layered or doubled chorus vocals defeated both of YW1's aligners. If a hook's cues look wrong in `cues.py`, ask the
  person to correct them in the app.
- Grain heavy enough to turn black into grey, glow on type, a wrong rotation sign, an upside-down texture: look at the
  stills before you animate.

**The films had these; the kit doesn't.** Build them in `src/lib/` when a film needs them: the groove bus (§3); NOK's
ring-O type (`ringLine`, `drawRingLine`) and its eye, which keep the motif inside the letters; and a pitch track (NOK
put bass notes on strings by pitch; here, the strongest low `S.band` at the onset is a rough stand-in).
