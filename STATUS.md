# Sound/Vision status

Updated 10 September 2026. The current interface uses the graphite/coral and soft-white/clay themes.

## Current backend milestone

YuE2 is installed on Legion in an isolated Python environment, pinned to verified source and model revisions. The existing Music interface submits real jobs through a private authenticated connection. One baseline song and two app-submitted takes completed successfully, were reopened after service restart, and have validated WAV/FLAC/MP3 outputs. The actual durations are 59.36 s, 36.72 s and 54.60 s; none reported native truncation.

Implemented: persistent request/take/job/artifact records, one/two versions, server validation, idempotent submissions, actual stage reporting, cancellation, targeted retry, plan-review/continuation controls, generated playback with real duration, metadata edits, exports and selected soundtrack handoff. Documentation and exact evidence are under `docs/backend/`; official references are under `docs/upstream/yue2/`.

Sound/Vision owns only its own service/processes. Existing ComfyUI/H3 queues are observed and preserved. Admission can wait for a busy GPU; this is not an atomic scheduler shared by all external apps. Full multi-user/public hosting remains a separate phase.

## Account and reference milestone

The user signed into Sound/Vision's isolated OpenAI account store. Live lyrics, three song ideas, and two native image covers succeeded. A harmony-edit proposal passed exact melody and timing checks. SheetSage2 transcribed a 59.4-second original recording in 5.22 seconds; YuE2 rendered its melody into a new 59.80-second, 48 kHz stereo song in 23.79 seconds, with no truncation warnings. Browser checks passed for account state, ideas review/apply/undo, reference upload/application/reload, and genre filtering. See `docs/backend/ASSISTANCE.md` and evidence files.

## Remaining application scope

D1 deployment and finished-video rendering, audio-reactive visualizers, directed video generation, singing synchronization, and public release hardening remain unfinished. The video editor generates background images and H3 clips and aligns lyrics to vocals; finished-video export remains unimplemented. There is no claim that this milestone completes the full project.

## Library and video editor

The library supports drag/checkbox/Shift selection, bulk project moves, ZIP downloads, recoverable Trash, and persistent project folders. The video editor offers Kinetic lyrics, Visualizer and Music video paths; kinetic settings include 16:9/9:16, equal-time image slideshows, short repeating H3 clip plans, local image/video imports, deterministic preview driven by the original song, lyric styling, audio-derived, editable word timing, per-song browser drafts, undo/redo, and JSON plan export. OpenAI image generation, H3 scenes/graphics/typography and CPU vocal alignment are connected. Automatic timestamps carry uncertainty flags; no proportional timing fallback remains. Final MP4 rendering is deferred. See `docs/backend/VIDEO_EDITOR.md`.

The current database is SQLite with D1-compatible migrations. OpenAI sign-in, song ideas, lyrics, bounded score edits, account-backed covers, and SheetSage2 reference transcription are implemented. Lyric proposals require review/apply before music generation. Reference and cover artifacts are durable on Legion. Official demo recordings were not imported because reuse permission was not established; no external demo links were added.

See `docs/backend/VERIFICATION.md` for measured versus unverified behavior and exact reproduction commands.

## Remaining live verification

The actual plan-review pause and queued/review cancellation were observed. Live cancellation during sampling and approved-plan continuation to audio remain unverified because other GPU work was active/resident. The extra verification job was cancelled and its score retained. These limits are recorded in the evidence matrix; no additional Sound/Vision GPU work was left queued.
