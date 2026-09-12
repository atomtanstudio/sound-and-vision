# Music studio UI — 10 September 2026

## Scope and layout

One working sample interface replaces the four-concept showcase. Main rail: Home, Music, Video. Music pairs a dedicated creation panel with a searchable library. Simple is the default. Advanced progressively discloses writing help, composition, and generation settings. The main rail expands to 264 px with a one-line wordmark or collapses to 72 px icons; its desktop preference persists. At 1000 px or narrower, the expanded rail overlays the workspace, with Escape/outside-click dismissal and contained keyboard focus. The creation panel scrolls as one continuous form including its title, mode tabs, fields, project choice and Create button; there is no independent inner scroll region or pinned creation footer. A single audio element backs the persistent player. Below 761 px, creation and results become explicit tabs; the rail and player stay available. Light/Dark are upper-right, Light first, with system preference initially and an explicit persisted override.

Suno was inspected directly in the user's signed-in internal-browser session on 10 September, using Simple, Advanced and Grid. No songs were generated, edited, published or downloaded there. Its rail / form / results relationship informed the information architecture. Sound/Vision uses original code, artwork, typography, surfaces and a much smaller navigation set. Reference screenshots in `reference/` are research materials, not shipped product assets.

## Verified YuE2 mapping

Primary sources: [generation guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md) and [repository](https://github.com/multimodal-art-projection/YuE), checked at commit `92a73cc7652fcc1f937855e4b765e0a0edd7ff2e`. A protocol snapshot is preserved in `reference/yue2-protocol.py`.

| UI | YuE2 input / intended orchestration |
|---|---|
| Style | `style`; genre, instruments, language, tempo and vocal character are prompt requests, not guaranteed parameter controls |
| Lyrics | `lyrics` with section tags such as `[Verse]`, `[Chorus]` |
| Melody & chords / Melody only / No score plan | `cot: full / melody / off` |
| Optional ABC | `abc`, included only when score planning is enabled; Vocal / Ins voices |
| Review score first | App workflow around plan → semantic generation → synthesis → decode |
| Seed | Integer in [0, 2^63); JSON carries text to avoid JS number precision loss; adapter parses to Python integer |
| Guidance | `cfg_scale` in [0,20], otherwise mode default (1.0 planned, 1.01 off) |
| Music sampling | temperature 1, top-p .95, top-k 100, repetition penalty 1.2, penalty window 50, min/max tokens 200/9000 |
| Score sampling | temperature .7, top-p .9, top-k 30, repetition penalty 1.005, penalty window 100, min/max tokens 32/4096 |
| Synthesis steps | `ode_steps`, default 32; midpoint method stays fixed |
| 1 / 2 takes | One / two independent generation calls, with a separate cover job for each |

With an explicit seed, the second take increments it, wrapping within the documented 63-bit range. A blank seed is a request for the future server adapter to select and record an independent seed for each take. Generation settings are validated client-side in this preview and must be revalidated by the server.

No unsupported Suno controls (weirdness, proprietary voice personas, stems, audio continuation) are presented as YuE2 features. ABC editing regenerates the recording. A description-only request is saved as `needs-writing`: YuE2 itself is not documented as a lyric-writing model. Integration must draft lyrics with an available authorized writing provider, or request user lyrics, before generation. Do not silently send work to an unavailable provider.

## OpenAI and covers

The [official GPT Image 2.5 Flare model page](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare) was checked for the requested model. Flare is the proposed cover default. Each take has its own cover prompt and status so image failure can be retried independently of successful audio. Cover prompts draw on the title, description/style and lyrics, and identify the take separately.

The preview does not implement authentication or call an API. A signed-in ChatGPT account, account-backed Codex tooling, and OpenAI API credentials are different integration surfaces. Account capability and model availability must be verified in the actual integration; do not promise that every user's subscription provides a general-purpose API credential. Writing tasks currently store intent only.

Original sample covers were generated using the native image tool in this task. The tool had no model-selection parameter, so these assets are not evidence that an integrated GPT Image 2.5 pipeline works.

## D1-compatible persistence

[Cloudflare D1 documentation](https://developers.cloudflare.com/d1/) confirms SQLite SQL semantics. `db/0001_music.sql` prepares projects, generation requests, takes and asset records using SQLite-compatible constraints and indexes. Local SQLite verification applies the schema, inserts a two-take request with two cover jobs, rejects a third take, and checks foreign keys. D1 itself has not been deployed or exercised.

Audio, covers and videos belong in durable media storage (local filesystem initially; R2 is a potential hosted adapter), with only storage keys and metadata in D1. Heavy inference remains on the model host. Workers handle metadata/auth/job orchestration; no long GPU generation is assumed to run inside a Worker request. Browser storage in this preview is temporary UI persistence, not the future database implementation.

## Fixtures and preservation

Two original synthetic instrumental samples remain 240 seconds, 24 kHz stereo WAV plus MP3. They provide real playback/download behavior while generation is disconnected. Soft Focus and Low Tide are draft examples with reference covers and no audio.

The former four-concept source and review artifacts are archived, not bundled. Original model services and source media were not modified. Vite initially could not empty the old `dist/assets` on the SMB-mounted workspace because `.smbdelete*` handles remained. The old build directory was renamed to the ignored `.build-archive-20260910`, and a fresh standard build completed successfully. No host or filesystem settings were changed.

## References

- [Suno official creation walkthrough](https://suno.com/hub/how-to-make-a-song)
- [Suno workspaces](https://help.suno.com/en/articles/4326849)
- Direct inspection of the user's signed-in Suno Create page in the internal browser; private content was not copied into the product.

## Navigation refinement

The former default project label Loose tracks now displays as Unsorted everywhere, including filters and search. The saved bucket value is retained internally so existing local drafts remain in the same project. Save to project explicitly identifies its purpose. Project creation rejects a name already represented by a displayed label. These are workspace organization features, not YuE2 inputs.
