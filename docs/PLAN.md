# Sound / Vision: the rebuild plan

Draft 1, 2026-10-08. Built from a survey of `soundvision.old` (Sep 23–29), `soundandvision.old` (Sep 30–Oct 7), the Rapture
film, the VRGDG skill, Legion's ComfyUI setup as it stands today, and fresh research on Suno, Suno Studio and the
music-video tools.

**The goal:** the best place to go from an idea to a finished song and a finished music video. It should be easier
than Suno for a first-timer and deeper than Suno Studio where it matters to us: lyric timing, stems, lip-sync and the
edit. Suno makes no real videos at all. Its "video" is a still cover with the song under it, and Hooks are your own
footage. So every video feature here is ground Suno doesn't hold.

---

## 1. Principles (learned the hard way across the two old versions)

1. **Easy by default, deep on demand.** Use one workspace that opens up, not two separate apps. The old Simple/Studio
   switch made you think a running film was lost. Start with three questions at most; everything else gets a sensible
   default that you can see.
2. **The app makes the work.** Every film comes out of the app's own pipeline, so anyone can repeat it. Nothing is made
   by hand behind the scenes.
3. **Claude directs, with free rein.** Give it hard limits only: don't touch the song's audio, take words only from the
   timing files, and produce the listed deliverables. No taste rules. The one-line desktop prompt beat the 140k-character
   rulebook.
4. **Never type lyrics into code or messages.** Lines are referenced by id and loaded at render time. Anthropic's API
   blocks output that reproduces lyrics, and songs may be covers.
5. **One GPU, one scheduler.** Every GPU job goes through one queue: songs, stems, H3, renders, and Claude's own
   requests. The old film runs bypassed the queue and collided with other jobs.
6. **Jobs survive everything.** Restarts, deploys and closed tabs don't lose a job. You can always see the stage it's
   at, the reason it's waiting, and a retry that reuses the finished stages.
7. **Show what the model was actually sent.** Suno rewrites your prompt where you can't see it. We show the style text
   and the settings sent to the engine.
8. **Never take a model away and never cap exports.** Each project remembers the exact model and influence it was made
   with. WAV, stems and MIDI are always free to export.
9. **Original casts.** Video characters are invented, never the real performers.

---

## 2. What we keep

**Visually:** only the wordmark. Its spec is in `soundandvision.old/scripts/make_wordmark.py` and in
`web/src/components/TopBar.tsx`:
- **Type:** Inter 800, tracking −0.025em.
- **Slash:** six bars, each 2.75 tall on a 3.4 pitch, clipped to `M6.4 0H12L5.6 20H0z` in a 12×20 box.
- **Bar colours, top to bottom:** `#4ade80` green, `#e8e1cf` cream, `#f5c542` amber, `#4d8dff` blue, `#ff4d94` pink,
  `#2dd4d8` cyan.
- **Light mode:** the cream bar disappears on a light background, so it needs a deeper tone there (around `#bfae86`).
  The ink colour flips too.
- **The six bars become the app's colour system.** Each one is a lane colour: Song, Lyrics, Picture, Video, Graphics,
  Sound. The logo doubles as the legend for the timeline.
- **Files:** a 3000 px PNG and the slash favicon carry over as files.

**Code worth carrying over.** This is logic, not screens.

| From | Keep | Why |
|---|---|---|
| `soundandvision.old/server/workers/` | `analysis_rhythm.py` (beats, downbeats, sections; pure numpy), `analysis_align.py` (wav2vec2 CTC, anchored on LRC or Whisper), `yue2_plan_guard.py`, `loop_worker.py` (seam closing and cut detection), the worker JSON-lines protocol | Measured and proven |
| `soundandvision.old/server/sv/` | `lrc.py`, `media.py`, `branding.py`, `transcription.py` (SheetSage covers), `accounts.py` (ChatGPT/Grok device-code sign-in), `assist.py` prompts and schemas, `studio.Session` and `summarize`, `albums.h3_graph` | Clean, with no UI ties |
| `soundandvision.old/server/studio/` | Dockerfile, `studio.sh`, the kit (engine, `render.mjs`, `getfont.mjs`, `import_song.py`, `h3plate.py`), `free/CLAUDE.md` | The Claude film studio works today |
| `soundandvision.old/web/src/` | `lib/timing.ts` (word-timing model), `lib/edit.ts` (trim/roll/ripple), `lib/layout.ts` (beat and bar math), `render/motion.ts` (springs), `render/lyrics.ts` (line balancing), `render/album.ts` and `titlelook.ts`, the undo/autosave/rebase design in `state/store.ts`, the onset detector and tap-to-time state machine, `models/songModels.ts` as data | Pure functions, well tested in use |
| `soundvision.old` | keychain device pairing in the Mac launcher, influences with subjects and exact weights, `clipcheck` (lip-follow, ArcFace identity), the green-screen keyer, `artwork.ts` (glow taken from the cover), your director brief (`music-video-director/brief.md`), the "cold read" story check, the honesty and provenance rules | Better than the newer version in these areas |
| Skills | `vrgdg-h3-film` (with `CHANGES-LOCAL.md`), `motion-studio`, `h3-kinetic-type`, `MOTION_DESIGN_PLAYBOOK.md`, the NOK engine | Reference material for Claude, not rules |
| Rapture | `make_plan.py` and `mg/src/show.js` (recoverable from the session transcript and from Legion's `films/rapture/`) | The reference for a hybrid video |

**Rewrite rather than port:**
- The `jobs.py` god-module.
- The single `app.py` routes file.
- The JSON-file document store.
- The two duplicated timelines.
- The DOM-per-word lyric editor, which re-rendered about 16 times a second.
- CPU HTDemucs, which takes minutes per song.
- The music runners that work outside ComfyUI.

---

## 3. Architecture

```
 Mac browser (or a Mac launcher holding the pairing in the keychain)
        │  HTTPS + one WebSocket for live job and timeline events
        ▼
 ┌────────────────────────── Legion (RTX 5090, 32 GB) ───────────────────────────┐
 │  sv-app (FastAPI)                                                             │
 │   ├─ Projects / Library     SQLite (WAL) + a media folder per project          │
 │   ├─ Scheduler              the one GPU queue; frees other ComfyUIs' VRAM       │
 │   ├─ Workflow registry      JSON API graphs + parameter bindings per capability │
 │   ├─ Providers              Claude · ChatGPT · Grok · local (Ollama / llama.cpp)│
 │   ├─ MCP engine             client for your MCP servers; server for Claude      │
 │   └─ Directors              Claude Director (preferred) · Guided Director        │
 │        │               │                   │                                  │
 │        ▼               ▼                   ▼                                  │
 │  sv-comfy (ComfyUI)  sv-analysis (GPU)    sv-studio (Claude Code + kit)        │
 │  YuE2 · Music 3 ·    stems (RoFormer) ·   Chromium on GPU, three.js, ffmpeg,  │
 │  ACE-Step 1.5 · H3 · alignment · Whisper ·skills; talks to sv-app over MCP     │
 │  VRGDG · images      beats/sections                                           │
 │                         the models folder (shared, nothing duplicated)        │
 └───────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 One ComfyUI for Sound / Vision (the consolidation)

**Today:** four ComfyUI containers share the GPU and hold about 23 GB of VRAM while idle.
- `ai-comfy-lab` :8189 (0.34)
- `ai-comfy-hunyuan` :8190 (0.39), which is the only one with the native music nodes
- `ai-comfy-h3-fused-turbo` :8194 (0.34)
- `ai-comfy-vrgdg` :8199 (0.34), which holds the VRGDG pack

**Proposed:** a new profile, `sv-comfy`, using the existing pattern of one ComfyUI profile per purpose.
- **Base:** ComfyUI 0.39 or later, the same image family as :8190.
- **Custom nodes:** `comfyui-vrgamedevgirl`, `ComfyUI-KJNodes`, `ComfyUI-VideoHelperSuite`, plus any H3 extras the routes
  need.
- **Models:** mounted from the shared models folder, so nothing is copied.
- **Port:** its own, for example :8210.

What's already on disk and what's missing:

| Capability | Native node | Model on disk | Missing |
|---|---|---|---|
| YuE2 (song, melody mode, cover via SheetSage ABC) | `YuE2GenerateMusic`, `YuE2GenerateABC`, `SheetSage2AudioToABC` | `yue2_3b_bf16.safetensors` | Check that the LoRAs load (§7, spike 2) |
| MiniMax Music 3 | `MiniMaxMusic3TextEncode`, `EmptyMiniMaxMusic3LatentAudio` | DiT (fp16/int8), text encoder, DAV VAE | none |
| ACE-Step 1.5 | `TextEncodeAceStepAudio1.5` (bpm, key, time signature, language), `EmptyAceStep1.5LatentAudio`, `ReferenceTimbreAudio` | XL turbo DiT, Qwen 0.6B and 1.7B, VAE (downloaded 2026-10-08, about 15 GB) | none |
| H3 video, song-locked lip-sync | `MiniMaxH3ImageToVideo`, `…ReferenceToVideo`, `…AddGuide`, `MiniMaxH3NativeAudioLock`, VRGDG builder routes | all present | none |
| Other lip-sync models (later) | `WanInfiniteTalkToVideo`, `WanSoundImageToVideo`, `WanHuMoImageToVideo` | not present | Models and a wav2vec audio encoder, only if H3 falls short |

**Two gaps in ComfyUI, both now closed** (Phase 0, 2026-10-08):
- **ACE-Step section edits.** ComfyUI's ACE-Step 1.5 nodes cover text-to-music plus "Set Reference Audio", which turns
  on the model's cover mode. There's no repaint node.
  - Our own node, `sv_nodes/SVAudioRangeMask`, puts an audio-shaped mask on the latent. ComfyUI's
    `SetLatentNoiseMask` only makes image-shaped ones.
  - The app then splices the new stretch into the original with equal-power crossfades, so everything outside the range
    stays bit-exact.
  - Measured: a 12 s replace on a 60 s song takes 14 s.
- **Stem separation.** There's no node for it. It goes in `sv-analysis` instead (§3.4).

**The old containers keep running** until `sv-comfy` is proven. The scheduler can ask the other instances to free their
memory (`POST /free`, no restart) before a big job.

### 3.2 The workflow registry (ComfyUI through its API, never its UI)

- **One file per capability:** each one, such as `song.yue2`, `song.ace15`, `song.music3`, `song.ace15.repaint`,
  `video.h3.loop`, `video.h3.scene_sung`, `video.h3.scene_story` or `image.zimage`, is an API-format JSON graph plus a
  small binding manifest that maps `{style, lyrics, seconds, seed, influences[]…}` onto node inputs.
- **Progress and results:** the client uses ComfyUI's WebSocket (`/ws?clientId=`) for live progress and node-by-node
  previews, `/prompt` to submit, `/history` for results, `/upload/*` for inputs, `/interrupt` and `/queue` to cancel,
  and `/free` for memory. The old app polled.
- **Influences:** these are LoRA loader nodes inserted at bind time, so one graph serves any number of them.
- **Self-check:** at startup the app checks `/object_info` against each graph and switches off any capability whose
  nodes or models are missing, saying why in plain words.

### 3.3 The scheduler

- **Lanes:**
  - **GPU, one at a time:** ComfyUI jobs, analysis, Chromium renders.
  - **Network:** LLM calls, MCP image calls, uploads.
  - **CPU:** ffmpeg assembly.
- **Admission:** a job starts only when enough VRAM is free (measured, not assumed). Before a big job the scheduler
  frees idle models on our ComfyUI, and on the others if you allow it.
- **Durable:** jobs are kept in SQLite. They resume after a restart, retry once on a crash, and requeue on out-of-memory.
  Every job carries its stage, progress, an ETA based on past runs, and a plain-language reason when it's waiting.
- **Claude can't jump the queue.** Its GPU requests (an H3 scene, a render) arrive through the app's MCP tools and
  queue like everything else, so they show up on your timeline as they happen.

### 3.4 `sv-analysis`, one GPU worker for listening

This replaces three borrowed environments: CPU HTDemucs, alignment inside YuE2's venv, and Whisper inside MaxMusic's.

**Stems:**
- **Vocals:** Mel-Band RoFormer, the best for vocals and so the best for timing.
- **Instruments:** BS-RoFormer 6-stem or htdemucs_6s, giving vocals, drums, bass, guitar, piano and other.
- **How:** `python-audio-separator` on the GPU, which takes seconds instead of minutes.
- **Optional:** splitting lead vocals from backing vocals.
- **Native stems:** if a model hands back separate vocal and backing tracks, keep those instead of splitting.

**Words:**
- **Known lyrics:** wav2vec2 CTC forced alignment on the vocal stem. The lyrics are always known for songs we generate,
  which is our edge over CapCut's 40–60% on sung vocals.
- **Anchoring:** on the LRC when there is one, otherwise on where faster-whisper large-v3 heard the line.
- **Confidence:** every word gets a score, so the timeline can show you where to look.

**Song map:** the ported `analysis_rhythm.py` (beats, downbeats, bars, sections, phrases, drum hits), plus key and
tempo. We'll A/B it against `beat_this` for downbeats.

**Measurement:** the same pass checks that a take honoured the BPM and key we asked for, and flags drift.

### 3.5 Providers (LLMs)

| Provider | Sign-in | Main job |
|---|---|---|
| **Claude** | Your own Claude Code login in `sv-studio` (signed in once in a terminal; the app never sees the token), or an Anthropic API key | Directing every video kind; it can also write lyrics |
| **ChatGPT** | Device code through OpenAI's Codex (ported `accounts.py`), or an API key | Lyrics, titles, prompts |
| **Grok** | Device code through xAI's CLI (ported), or an API key | Lyrics, titles; Grok Imagine pictures |
| **Local** | Ollama or llama.cpp on Legion | Offline writing |

- **Settings:** a **Connections** page holds all four providers. Under them, **Who does what** lets each task pick its
  own provider and model, with a cost hint beside each choice. Defaults, from your note of 2026-10-08:

  | Task | Default | Why |
  |---|---|---|
  | Directing videos (all three kinds; treatment, plan, code, review) | Claude Opus 5.5 (Fable 5.5 when out) | the best creative and code work |
  | Lyrics, titles, rewrites, rhymes | Grok | good and much cheaper to run |
  | Cover-art prompts, motion text for loops | Grok (or ChatGPT) | short, cheap tasks |
  | Song background lookup (facts only) | ChatGPT with web search, or Claude Sonnet | needs search |
  | Small chores (labelling MCP tools, captions, hashtags) | local model, else Grok | near free |

  A task falls back down its list when its first choice isn't connected, and the screen says so.
- **Local model size:** `qwen3.5:4b` is too small. It ignored outlines and leaked "YuE2" into a lyric. We should offer a
  bigger local model, with the scheduler sharing VRAM fairly.
- **Claude and other people:** Anthropic's terms allow someone to sign in to the unmodified Claude Code with their own
  subscription. They don't allow an app to run other people's requests through one person's Pro or Max login. If anyone
  besides you uses the app, their Claude has to be their own (their own sign-in or their own API key). See decision 3.

### 3.6 The MCP engine

**MCP client.** In Settings → Connections → MCP servers you can:
- add a server by URL (HTTP, with OAuth handled by the app) or by command (stdio);
- test it and list its tools;
- see each tool sorted into **Makes images**, **Makes video**, **Makes 3D**, **Makes audio** or **Other**, read from its
  schema and description, with you able to correct the label;
- pick defaults, such as "Cover art: my image server · Character sheets: ChatGPT".

The app's own steps call these through a capability adapter. Each tool's input schema is mapped once and cached.

**Paid tools.** A per-server setting asks before spending, and shows the price per call when the tool reports one (for
example $0.29 per GPT Image 2.5 picture).

**Inside Claude's runs.** The same servers are passed to Claude with `--mcp-config`, so it can make its own references.

**What the Phase 0 tests showed:**
- **Hosted MCP servers** follow the standard MCP sign-in: protected-resource metadata, dynamic client registration and
  PKCE. So **Connect** is one generic flow: you sign in once in the browser, and the app keeps the token.
- **Connectors on your Claude account** already show as connected in Claude Code in `sv-studio`, so Claude Director runs
  can use them as is.
- **Labelling tools** by keyword is too crude (Blender's `generate_3d` came out as "Makes images"). The writer LLM labels
  each tool once, and you can correct it.
- **Servers that run on your Mac** (stdio ones like Blender, which talk to apps on the Mac) can't be started by the app on
  Legion. The Mac launcher hosts them and relays them to the app over the paired connection. HTTP servers connect from
  Legion directly.

**MCP server.** The app exposes itself to Claude as `sv`, with these tools:
- `song_map`, `lyric_lines` (ids and times only), `stems`
- `render_h3_scene`, `render_loop`, `make_image` (routed to your MCPs), `assemble`
- `timeline_put` (places Claude's scenes and cues on your timeline)
- `show_preview`, `ask_user`

This is how Claude's work appears live on the same timeline you edit, and how its GPU use stays in the one queue.

### 3.7 Directors

**Claude Director**, preferred whenever Claude is connected:
- Claude Code in `sv-studio`, using Opus 5.5 by default, Fable 5.1 now and Fable 5.5 when it's released. You can choose
  the effort level.
- It has the kit, the skills as reference, the `sv` MCP, and your MCP servers.
- It runs with free rein and hard limits, can show its plan first, takes your notes and carries on, and keeps a review
  loop with contact sheets.

**Guided Director**, the fallback for any LLM:
- A fixed pipeline per kind.
- The planning steps are JSON-schema prompts (treatment, shot list, motion text) that ChatGPT, Grok or a local model
  can answer.
- Assembly is deterministic.
- Its ceiling is lower, but it always works.

The video screen shows **"Directed by: Claude (Opus 5.5 · High) ▾"** and falls back with a plain note when Claude isn't
connected.

---

## 4. The experience

### 4.1 Structure

- **Home:** two front doors at top left, **Make a song** and **Make a video for a song I have**. Below them, recent
  projects as large cover tiles and the jobs running now.
- **Project:** one workspace with three steps across the top, **Song · Video · Share**. Moving between steps never stops
  a job.
- **Library:** projects in folders, Influences, Cast (reusable characters), Covers, and Trash.
- **Settings:** Connections (LLMs, MCP), Models, Branding (logos), Appearance, Legion (GPU, queue).

### 4.2 The workspace

```
┌ Sound/Vision   Afterglow ▾          Song ─── Video ─── Share            ☾   ⚙ ┐
├───────────────┬─────────────────────────────────────────┬──────────────────────┤
│ Make panel    │  Stage                                  │  Director / Inspector│
│ (asks the     │  cover · video monitor · lyric sheet    │  Claude's plan, its  │
│  fewest       │  glow taken from the cover art          │  questions and stills│
│  questions)   │                                         │  your notes; or the  │
│               │                                         │  selected clip       │
├───────────────┴─────────────────────────────────────────┴──────────────────────┤
│ ▔▔ drag up for the full timeline ▔▔                                            │
│ bars │ sections │ Song ≈≈≈ │ Vocals ≈≈ │ Stems ▸ │ Lyrics ▭▭ │ Video ▣▣ │ Type ◆ │
└────────────────────────────────────────────────────────────────────────────────┘
```

- **Guided** is the default. The timeline is a slim strip showing the ruler, the song and the lyrics. Drag it up, or
  press `T`, to get every lane plus the inspector. That's Studio, in place, with no separate app.
- **One command bar (⌘K)** takes plain-language requests such as "make the second chorus darker" or "move the title to
  the drop". The writer or director turns each one into concrete, undoable operations.

### 4.3 Song

**Make panel:**
- What's it about? (one line)
- Sung or Instrumental
- Sound: style chips plus **+ Influence**
- Length
- **Make the song**

**Lyrics:**
- Lyrics are written for you by your chosen writer.
- They live on a lyric sheet with section tags. Select a word for rhymes, or a line for alternatives.
- A cliché filter catches words like "neon" and "echoes".
- Syllable fit is checked against the section's length.
- You can paste your own lyrics, or upload your own song with an optional LRC.

**Model:**
- **YuE2 is the default.** You said it's the best overall. MiniMax Music 3 and ACE-Step 1.5 are one click away.
- The app only steps off YuE2 when you pick another model, or for a job only another model can do, such as ACE-Step's
  bar-range edits. It says so when it does.
- Choosing a model shows *its* options, rendered from a per-model manifest with plain labels and More for the rest:
  - **YuE2:** melody or full plan, cover a recording (SheetSage melody, or melody and chords), creativity (temperature),
    seed.
  - **ACE-Step 1.5:** BPM, key, time signature, language, timbre reference; plus section edits.
  - **MiniMax Music 3:** caption, length, guidance.

**Takes:**
- Each generation gives 2 takes as **take lanes** under the song.
- You can A/B them at the same playback position, see a settings diff, and pick **Use this one**.
- Analysis runs by itself when a take is picked: stems, word timing and the song map.

**Section edits, where we beat Suno:**
- Select bars on the song lane, then **Replace this part**, **Extend**, or **Change these words** (ACE-Step repaint on
  that bar range).
- New versions land as take lanes for that range. Crossfaded comping, and nothing is lost.
- This fixes Suno's top complaint, that "a small edit gives a different song".

### 4.4 A song you already have (a real song, or your own recording)

Most people will make their own music here, but any existing song can become any of the three videos.

1. **Drop in the song.** We read the file's title, artist, key and BPM tags. You can also add a synced lyrics file
   (.lrc) or paste the words.
2. **Find the words** if you have none. Whisper hears them, and you correct them on the lyric sheet.
3. **Background lookup.** For a released song, a quick web lookup collects facts about it (era, genre, what it's about,
   how it was received). Claude uses those as facts only, not as design ideas.
4. **The usual analysis.** Stems, word timing anchored on the LRC or on what was heard, and the song map.
5. **Straight to Video.** Same three kinds, same timeline, same Share.

The rules for a song that isn't yours:
- The words come only from what you supply or what Whisper hears, and are never typed by Claude (lines by id).
- The cast is always original characters, never the real artist's likeness.
- The album art is your own picture or one made in the app. The official cover is used only if you upload it.
- The song's audio goes out bit-exact. Share reminds you that posting someone else's song is subject to the platform's
  music rights. Shorts over 1 minute with a copyright claim get blocked.

This replaces the old app's "Use my own song", where the step was hidden inside Song.

### 4.5 Influences (LoRAs, never called LoRAs)

- **What they are:** each influence is an **Artist**, **Genre** or **Style** card with a name, what it's good for, the
  models it works with, a 20-second sample, and a recommended strength.
- **The song only shows what you've added**, as chips with a strength control that starts at the recommended value.
  That fixes the old slider that jumped to 50% on the first press. **+ Influence** opens a searchable library sheet with
  previews.
- **Adding your own:**
  1. Library → Influences → **Add your own**.
  2. Drop in a `.safetensors` file, or paste a Hugging Face link and the server downloads it.
  3. The app reads the tensor names to tell which model it's for, reads rank and alpha, and reads any trigger words
     from the metadata.
  4. You give it a name and pick Artist, Genre or Style.
  5. **Try it** makes a 20-second sample.
  6. **Save** puts it in `<models>/comfyui/loras/soundandvision/<model>/` with a sidecar JSON.
- **Safety:** only `.safetensors` (pickle files are refused), a size limit, and a recorded hash.
- **To bring in:** DreamPop, Old-school hip hop, Blancmange, Industrial, and the Instrumental influence (used
  automatically for instrumentals).

### 4.6 The timeline (the power tool)

**One engine for everything** (song, lyrics, video). The two duplicate timelines go away.
- **Lanes:**
  - **Ruler:** bars and beats, with sections coloured.
  - **Song:** a min/max waveform pyramid made on the server, so zooming is instant.
  - **Vocals:** with a confidence heat strip.
  - **Stems ▸:** drums, bass, guitar, keys, other, with solo and mute.
  - **Lyrics:** lines and words drawn on the vocal waveform.
  - **Video:** scenes, shots and loops with filmstrips.
  - **Graphics/Type:** cues.
  - **Markers.**
- **Rendering:** on canvas, at device pixel ratio. The DOM is used only for text fields and menus. Drags never
  re-render React.
- **Transport:** built on an AudioContext, so the stems play sample-locked and solo/mute is instant.
  - Scrubbing plays the sound under the cursor.
  - J/K/L shuttle; `,` and `.` step by frame or by 20 ms.
  - Rendered video scrubs frame-accurately through WebCodecs on light proxies.
- **Snapping:** to beats, downbeats, sections, word edges, vocal onsets, clip edges and the playhead. ⌥ turns it off and
  ⇧ gives fine movement.
- **Lyric timing:**
  - Auto-aligned first. Low-confidence words glow so you know where to look.
  - Drag or trim words, hold **T** to tap words in as they're sung, nudge with ⌥←/→, set with `[` `]`, and P to listen.
  - You can re-align one line, and every edit can be undone.
  - The keyboard map from the old editor carries over.
- **Lip-sync and shots:**
  - A sung shot shows the lines it carries.
  - Cuts snap to the gaps between lines.
  - Each shot has a lip-follow badge. Re-roll, reword or swap any shot without touching the others.
- **Undo, autosave and multi-window merge:** the old store's design, ported.

### 4.7 Look and feel

- **Themes:** dark is the default, light is fully supported, and both are built from tokens. The theme is set before
  the first paint, so there's no flash.
- **The theme toggle, built new in code:**
  - The sun rolls across the pill and becomes the moon.
  - Little stars twinkle into the night side, and the clouds fade on the day side.
  - It springs into place and respects reduced motion.
  - No starry version exists in threecade or any other project, including git history; the nearest is promptsilo's pill
    with a quarter turn. So this is a fresh build.
- **The cover lights the room:** two colours are taken from the artwork and drive a soft glow behind the stage.
- **Motion:** spring physics everywhere, using the same springs the films use, so the app feels like the videos it
  makes.
- **Type:** Inter for the interface (the wordmark's family) and a mono face for timecodes. The display face gets chosen
  with real comps, since fonts were a past complaint.

---

## 5. The three kinds of music video

You choose one in plain words. Each kind has its own timeline lanes, and Claude directs whenever it's connected.

### 5.1 Living Album Cover (the simplest)

**Inputs:**
- **Cover:** made in the app (through an image MCP, Grok Imagine or Z-Image), or your own picture.
- **Made to move:** on by default. It asks for a still moment, nobody walking or turned away, and things that can move
  in place, such as mist, water, light or hair.
- **Segments:** 1, 2, 3 or 4.
- **Length per segment:** 1–15 s, default 8 s.
- **Feel:** calm or lively.
- **Title layer:** title, an artist line only when an artist is given, and the label logo.
- **Shape:** 1:1, 9:16 or 16:9.

**How it's made:**
- Every segment is a separate H3 loop, with the cover pinned as both its first and last frame, so each one is seamless
  on its own.
- Segments are **not** joined to each other. They take turns across the song with a soft dissolve at section changes,
  and you can reorder them on the loops lane.
- Segments 2–4 are thematic siblings. Claude (or the writer) gives each a related motion idea, or makes a sibling cover
  in the same world and palette.

**Honest limits:**
- H3 tends to cut to a new shot in single clips over about 8 s, so longer segments are joined from 6 s pieces that
  are each pinned at both ends. This is already proven.
- A cut detector and a motion meter retry up to 3 seeds per piece.
- Cost: about 1 minute per 6 s piece at 1024 px.

**Render:** one ffmpeg pass (about 25 s for a 3-minute song), with the title layer drawn by the same canvas code the
monitor uses.

This kind needs no Claude at all. Claude makes it better.

### 5.2 Kinetic Typography (Claude at full stretch)

- **Model:** Opus 5.5 by default, Fable 5.5 when released, with your choice of effort.
- **Inputs:** your request (optional), "How should it feel?" (optional), and **Show me the plan first** (on by default).

**What Claude gets:**
- The song: master, stems, word timing, song map, and a listening report.
- The kit: a three.js and HarfBuzz type engine, GLSL, Puppeteer on the GPU, any Google Font, and springs.
- Your MCP image tools for textures.
- Optional H3 plates: the **Picture by H3, type by Claude** hybrid.

**References, for inspiration rather than rules:** No One Knows, Go, Your Woman, the motion-studio skill and the
playbook.

**Hard limits only:**
- The song stays bit-exact.
- Every word is drawn on its sung frame, from the timing files.
- No lyrics are typed anywhere.
- The deliverables are produced.

**Review loop:** contact sheet, a 360 px phone sheet and frame strips, then it fixes what it sees.

**Deliverables:**
- A 16:9 master.
- **Re-laid-out**, not cropped, 9:16 and 1:1 versions.
- A poster and a contact sheet.
- A share-size encode.

**Without Claude:** the Guided Director offers a small set of good template styles (the ported renderers), labelled
honestly as templates.

### 5.3 Music Video, three ways

All three use the VRGDG pipeline in `sv-comfy`: song-locked H3 2-pass turbo, scenes on bar lines, and first frames from
your image MCPs.

| Sub-kind | What it is | Lip-sync | Distinct checks |
|---|---|---|---|
| **Performance** | A band or singer (original characters) across 2–5 settings; every shot is sung or played | Every sung shot (medium close-up or closer, 2 s or more, cut in the gaps between lines) | Lip-follow, face identity against the cast sheet |
| **Story** | A story, or pure image, shaped by the lyrics and mood; may have no people at all | None | **Cold read**: a fresh model sees only the frames and says what happens |
| **Hybrid** | A story world with sung moments plus a motion-graphics layer; Rapture is the reference | Sung shots only | All of the above |

**Flow:**
1. Treatment and look.
2. Cast sheets.
3. The plan on bars.
4. First frames.
5. **Pilot of 3 scenes.** You see them and say go.
6. Full render, scene by scene, landing on your timeline as each finishes.
7. QA and automatic re-rolls. A shot gets rewritten, never the voice text, and after 3 failures it asks you.
8. Assembly with the song put back from the WAV.
9. The graphics pass.

**Honest time:** about 5.5 minutes per scene. A 3.5-minute song is 30–40 scenes, so roughly 3–4.5 hours, and the app
says so before you start.

**Rapture's measured lessons are built in:**
- A "setting" sentence in first-frame mode makes H3 open on a wide establishing shot.
- Text stacked over a shot sits beside the face, never on it.
- Subtitles must be 66 px or larger to read on phones.
- The lip-follow measure under-reads fast rap, so check those shots by eye before re-rolling.

---

## 6. Share (on the roadmap, after everything above works)

**Packages per destination**, built from the platforms' own specs:
- **YouTube (full video):**
  - The 16:9 master, encoded to YouTube's recommended settings.
  - A **thumbnail at 3840×2160** that Claude designs from the strongest frame plus title type, judged at phone size.
  - A title of 100 characters at most, with the hook in the first 70.
  - A description of 5000 bytes at most, with artist and song notes, credits, and **chapters made from the song's
    sections**.
  - Up to 3 hashtags.
  - The AI-content flag (`containsSyntheticMedia`).
- **Shorts, Reels and TikTok:**
  - 1080×1920 hook cuts of 15, 30 or 60 s, picked from chorus energy and the lyrics.
  - Type placed inside each platform's safe zone.
  - A cover frame.
  - Each platform's rules: Instagram allows 5 hashtags at most; TikTok gets 3–5 specific ones; the AI flags `is_aigc` and
    `is_ai_generated`.
- **Direct posting, later and in this order:**
  1. **YouTube Data API:** the simplest. Uploads now cost 1 unit from their own quota bucket, with 100 a day.
  2. **Instagram Graph API:** needs a Business or Creator account and a Meta app.
  3. **TikTok Content Posting API:** posts stay private until the app passes TikTok's audit, and it has strict rules for
     the posting screen.

---

## 7. The roadmap

Each phase ends with something you can open and use.

**Phase 0: Legion consolidation and spikes.** Needs your OK (decision 1). Nothing old is switched off.
1. Build `sv-comfy` and add the ACE-Step 1.5 files.
   - **Done when:** a script makes a song with each of YuE2, Music 3 and ACE-Step 1.5 through the API, with time and VRAM
     recorded, and you approve the sound.
2. **Influences in ComfyUI.**
   - **Done when:** an AI-Toolkit YuE2 influence sounds the same through ComfyUI's LoRA loader as through the old merge.
     If it doesn't, write a converter.
3. **ACE-Step repaint through ComfyUI** (by masking the latent).
   - **Done when:** an 8-bar replace works. If it doesn't, keep the old container for edits only.
4. **`sv-analysis`.**
   - **Done when:** RoFormer stems run on the GPU in seconds, and the word-timing error measured against the Rapture and
     Afterglow LRCs is no worse than HTDemucs.
5. **VRGDG in `sv-comfy`.**
   - **Done when:** one Rapture scene re-renders identically to :8199.
6. **MCP.**
   - **Done when:** a Python client lists and calls tools on Blender and a hosted image server, and Claude Code in `sv-studio` calls a
     stub `sv` MCP and reaches your image connectors.

**Phase 1: Skeleton.**
- New repo (git), the FastAPI routers, SQLite, the scheduler with ComfyUI WebSocket progress, and the workflow registry.
- The web shell: tokens for both themes, the wordmark component, the sun/moon toggle, the workspace layout, and
  Connections (LLM providers and MCP servers).

**Phase 2: Song.**
- The Make panel, model manifests, the writer, takes with A/B comparison, the Influences library and Add your own, the
  analysis pipeline, and uploading your own song with an LRC.

**Where things stand (2026-10-09, morning).** Phases 0 and 1 are done. Phase 2 is mostly done: the Home prompt (two
takes at once), the song page for YuE2, ACE-Step 1.5 and MiniMax Music 3, the writer (Haiku 5.5), Match a sound, takes,
"Use this one" with stems and word timing, the Influences library with Add your own, song covers (ChatGPT, an MCP
server, or Krea 2 on the GPU, with the title and logos set by the app), and the **Influence Engine** (research, gather from
your music or audio you add, MOSS captions, FL YuE2 training, previews, try on a song, keep). Still to come in Phase 2:
uploading your own song with an LRC, and A/B comparison of takes.

**Phase 3: The timeline.**
- The unified engine, all lanes, scrubbing and transport, the lyric-timing editor with confidence, stems, and section
  edits with take lanes.

**Phase 4: Living Album Cover**, end to end, in all shapes.

**Phase 5: Kinetic Typography**, with the Claude Director: `sv-studio` with the `sv` MCP, plan first, notes, review loop,
and the hybrid H3 plate option.

**Phase 6: Music Video** (Performance, Story, Hybrid): the VRGDG pipeline driven through `sv`, the pilot, live scenes on
the timeline, QA and re-rolls, and the graphics pass.

**Phase 7: Share**: packages first, then direct posting.

**Throughout:** the Guided Director fallback for every kind, and a "cold eyes" design review at the end of each phase.
That's a fresh reviewer scoring screenshots against Suno, as the critic gate did in the first version.

**The old live app stays untouched.** `soundandvision.service` on :7640 and the test server on :7650 keep running. The new
app gets its own port and data folder until it replaces them.

---

## 8. Against Suno, point by point

| Suno (Oct 2026) | Sound / Vision |
|---|---|
| Old models retired with v6; downloads capped at 20/60 a month | Your models stay; exports are unlimited |
| Studio is Premier-only and scored 6/10 | The full timeline for everyone, one drag away |
| A small edit gives a different song | Bar-range edits become versions you can A/B and comp |
| Prompts rewritten where you can't see them | The text sent to the engine is always shown |
| Stems: 12 categories on Pro, about 100 on Premier | Six stems plus clean vocals, free, and they drive the video |
| No word-level lyric timing | Forced alignment from the known lyrics, with confidence and tap-to-fix |
| No real video (a still cover; Hooks use your own footage) | Three kinds of generated video, with lip-sync |
| Time signature ignored by generation | BPM, key and time signature go to the model and get measured |
| Tracks ship as-is | Social packages with thumbnails, chapters, safe-zone type and hook cuts |

**Not chasing:** Suno Studio 2.0's piano roll, synths and plugins. We win on song to video, not as a DAW.

---

## 9. Risks

- **One GPU.** H3, the music models and Chromium all compete for it. The scheduler is the answer, but long music videos
  will still take hours.
- **ComfyUI gaps.** ACE-Step edits, and LoRA formats for YuE2. Phase 0 settles both before any UI depends on them.
- **Third-party nodes.** The VRGDG pack is changed locally. Its `CHANGES-LOCAL.md` has to be re-applied on every update,
  and the version is pinned.
- **Licences.**
  - YuE2 weights are CC BY-NC with an individual-creator permission.
  - MiniMax H3's community licence excludes the US, EU, UK and Korea.
  - These need a look before anyone else uses the app or anything is sold.
- **Claude for other users.** See §3.5 and decision 3.
- **Lyrics through Claude's API.** The rule against typing lyrics is enforced in the kit and the prompts, and a blocked
  reply shows a plain message.

---

## 10. Decisions needed from you

1. **Legion:** may I build `sv-comfy` (a new container, shared models) and download ACE-Step 1.5 (about 10 GB) and the
   RoFormer stem models (about 1–2 GB)? 487 GB is free.
2. **GPU sharing:** may Sound / Vision ask the other ComfyUI instances to free memory before its jobs? This is
   `POST /free`, not a restart.
3. **Who uses it:** just you (on your network), or other people with their own accounts? This decides sign-in, and how
   Claude is connected for them.
