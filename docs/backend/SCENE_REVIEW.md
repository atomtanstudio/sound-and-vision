# Scene review and individual retries

## Character sheets and Singularity first pass (September 12, 2026)

New directed and song-led music-video projects now prepare a full cast registry
and a front/left/right/full-body sheet for every character before scene rendering.
Existing projects expose **Prepare character sheets**; it keeps their existing
takes and cuts, and applies the new setup to future renders. Each scene carries
its own cast IDs, character references and designated vocalist. The original song
remains the playback/export soundtrack.

New and upgraded projects use the installed Singularity v1.3 checkpoint with the
eight-step first generation stage from the two H3 Face Refine workflows. Later
face-refinement passes remain off. Quiet scenes have no audio conditioning; singing
uses the isolated vocal with sample-level gating during measured rests. Instrumental
band members remain silent while the assigned vocalist sings.

See [implementation, checks and installation receipt](../../deliveries/character-continuity-20260912/README.md).
The earlier fused-Turbo and full-mix-lock descriptions below document the retained
legacy paths; they do not describe the new profile. Visual quality is left for
the user's testing; this update submitted no model-generation work.

Choose **Video → Music video → Review scenes** as soon as one scene is ready.
The button becomes **Review & export** when all scenes are ready,
or open `/video?film=<project-id>` for a retained project.

## Delete and restore a video project

**Delete project** moves the current directed-video project to **Trash**. The active
selector becomes clear for another project. Expand Trash and choose **Restore** to
bring it back, including every take, note and export. The underlying song is managed
separately by Music Trash; deleting a video project never deletes the song.

`DELETE /api/films/{id}` and `POST /api/films/{id}/restore` take the current revision.
Deletion records `deletedAt` in the existing manifest and is reversible; this is not
a disk-space purge. Active jobs must finish or be cancelled first. Trashed projects
are excluded from normal listing, rendering and media access. They remain visible
through `GET /api/films?include_deleted=true`, used by the restore UI. Retaining the
tombstone prevents discovery of the original film plan from recreating the project
after deletion or restart.

## Review workflow

1. Play the full film. The scene strip indicates the playing scene.
2. Select a scene. Use **Play scene** for its exact song excerpt or **Play across
   the cut** to watch the chosen take with up to two seconds of each neighbor.
3. Choose an issue and describe the correction. Scene continuity records who is
   present, object counts, ownership and the required beginning/end state.
4. Choose a completed **Take**, leave **Smart repair** selected, describe the
   problem in ordinary words, and choose **Render repair**. It inspects sampled
   frames and chooses how to repair the scene. A finished candidate is automatically
   previewed and remembered per scene; accepting it into the film remains explicit.
   Generative repairs use the existing H3LIX four-step fused Turbo profile.
   **Adjust timing** instead shifts existing video frames against the untouched song
   without OpenAI or H3 generation. Positive frames delay the video; negative frames
   advance it. Up to one second is allowed. The first/last frame is held to preserve
   duration. Use this only for a consistent offset, not incorrect mouth shapes or
   variable drift; inspect the held boundary in **Play across the cut**.
5. Compare takes in the dropdown. **Use this take** selects a completed candidate
   and queues an updated full-film export if all scenes have rendered. During partial
   review it saves the selection without attempting a premature export. All other scenes and the original
   soundtrack retain their exact frame positions. The old export remains available
   while the new cut is built. To restore a scene, select Original and use it.

**Mark scene reviewed** records the user's review of the currently selected take.
If another export is already running when a selection changes, finish that export
and use **Build updated film** for the latest selection. Export inputs are immutable
snapshots, so a later edit cannot change a render already in progress.

## Smart repair

The connected account receives a chronological contact sheet of the actual source,
the user's note, measured cut candidates, scene action, vocal windows and neighboring
continuity notes. It returns a validated plan with intent, evidence, scope, a specific
source frame, camera-cut policy, speech policy, method and explanation. The plan is
visible while working and remains attached to the take. It overrides obsolete scene
instructions: a request to remove a montage must not preserve its original cuts.

The planner can choose:

- **Rebuild from a frame**: anchor one coherent source view and generate a full
  scene or bounded interval. An unwanted montage is excluded from motion references.
- **Reuse a continuous section**: keep an existing quiet shot and slow it to fit the
  full scene. The section must last at least half the scene and two seconds, must
  contain no measured interior cut, and is limited to silent scenes. Source action
  is retained; motion interpolation smooths playback. This skips H3 and the GPU lock.
  The source interval and playback speed are shown. Inspect interpolation artifacts
  and all mouth motion; slowing footage cannot repair speech-like action within it.
- **Source video edit**: retain source motion and shot order for an appearance or
  detail change. This remains generative, without a temporal edit mask.

The original song is always used for playback/export. A silent-character plan clears
all generation audio conditioning, including where the song contains a singer.
The worker cannot retime a singing performance through the continuous-section path.
Invalid ranges, unseen anchors and material unresolved contradictions stop before H3.
There is one candidate per request, with no automatic retry loop or acceptance.

Afterward the model receives source and candidate frame sheets, intent and fresh cut
measurements. Its review appears beside the take. A remaining measured interior cut
overrides an optimistic model verdict for a single-shot request; suspected mouthing
is flagged, and an unassessable face remains uncertain. These are sampled images,
not continuous video inspection or certified lip sync. Full playback is necessary.
Review failure retains the candidate with an explicit uncertain status.

`backend/film_intelligence.py` contains planning and review. `input.json` stays
immutable; `planned-input.json`, `smart-plan.json`, inspection sheets and
`checks.json.aiReview` retain the decision and evidence. Recovery reuses the saved
plan and provider run. Contact sheets are scoped local images passed to the existing
account runtime; arbitrary filesystem attachments and model tools are disabled.

## Manual source editing, continuity and timing

Every request retains the entire film plan, accepted neighboring take paths, all
scene continuity notes, global continuity, the user's correction, and the original
scene's exact start/end frames. The connected OpenAI account compiles that context
into a short brief containing only the selected scene's cast, location, start/end
states, one simple action and object constraints. This uses the existing account
connection with tools disabled. If unavailable, saved scene-specific notes are
used and the compiler fallback is retained in the job record.

Repairs snapshot `baseTakeId` (the previewed take; defaults to the accepted take
for API clients), its trusted source path and the repair method. In source-edit mode, H3 receives that
actual video with its audio disabled, plus the original identity images and focused
scene brief. The prompt uses the official `video editing` task contract and identifies
the source as `<Video 1>`. The video supplies framing, camera motion and staging;
the explicit correction overrides the faulty part. This is source-conditioned
generation, not a masked pixel edit or a guarantee that everything else is unchanged.
The worker records the source hash and submitted asset kinds in provider intent.
The source video is encoded as a 512×288, 24 fps motion reference; original identity
stills retain their detail, and output stays native H3 resolution then 1920×1080
for the film. Sampling a full-resolution 10.67-second reference exceeded the 5090's
memory in the live check. Inspection of the installed node confirmed that reference
spatial tokens are retained through sampling. The proxy reduces those tokens while
keeping every source frame and its pace. Its end is padded with the final frame to
H3's 5-mod-17 temporal boundary, avoiding silent truncation of the source's end.
The proxy is a guidance asset, not the final export or a substitute for the master.
The whole storyboard is deliberately **not** pasted into the H3 render prompt:
live testing showed that it can cause H3 to generate a montage inside one clip.
Neighboring end/start frames remain available for boundary review rather than
being uploaded as unrelated scene locations. The full context is preserved in
`input.json`; `context-brief.json` and `prompt.txt` show its scoped interpretation.

When an existing separated-vocal file is available, performance retries use that
isolated voice for H3 conditioning, preserving its original timing. Silent story
scenes receive **no audio conditioning**, including when the master contains vocals.
Performance scenes with no aligned words also receive no audio conditioning.
Preview and export always use the original full song;
the vocal stem never replaces the delivered soundtrack.

In the earlier Small Repairs example, the first singing scene begins at 18.916667 s, while its first aligned word begins
at 19.703 s. Its 0.786-second opening rest and subsequent vocal windows are included
in retry instructions. Words crossing scene boundaries retain clipped acoustic
timestamps. No beat-based lyric timing is invented. These are model instructions,
not a guarantee of exact generated mouth motion. Low-confidence acoustic words
remain flagged in the inspector.

Small Repairs' continuity notes distinguish the repairman, his older brother and
the young customer. They specify two stationary kitchen mugs, and that the single
customer-owned bicycle leaves with its owner and does not reappear later. Original
scenes are not silently altered to fit those notes; affected scenes are flagged
for review and individual replacement.

## Checks and limitations

Each generated candidate must decode completely, cover its exact frame count,
and preserve the original audio-window mapping before becoming available.
Frame-change analysis flags possible internal cuts (`scene > 0.24` in FFmpeg).
These are review flags, not proof of an error or a successful semantic review.
The app does not claim automatic detection of every changing face, duplicated
object or lip-sync mismatch. Human review remains necessary before selecting a
take. A technically valid render is never automatically approved or retried.

The previous retry path generated a new scene from stills and ignored the previewed
video. Four user retries retained on September 10 used that path. New requests use
`repairVersion: 2`; recovery of older submitted requests preserves their saved inputs
and never silently changes or resubmits a provider run. A timing repair is deterministic
and retains the source frames (with encoding), but does not measure or certify sync.

The across-cuts preview re-encodes only the relevant neighboring pieces and the
chosen scene, then uses one uninterrupted original-song excerpt. Full exports
use the existing exact-frame compositor and verifier, with the original master
audio muxed once. Earlier takes, H3 outputs, prompts and exports remain intact.

This first review/import path supports completed 24 fps, 1920×1080 directed films
with retained scene clips. It does not create an initial storyboard or silently
convert unsupported portrait projects. The separate visualizer editor is unchanged.

## Persistence, concurrency and recovery

- `backend/film_review.py`: authenticated API, versioned manifests and job queue.
- `backend/film_worker.py`: focused prompt, H3 request/recovery, scene checks,
  previews and full export.
- `src/video/FilmReview.tsx`: review player, scenes, comparisons and correction UI.
- `data/film-reviews/<film-id>/manifest.json`: current selections and take history.
- `data/film-reviews/<film-id>/jobs/<request-id>/`: immutable inputs, compiler
  output, prompt, provider intent, output, logs and checks.
- `data/film-reviews/<film-id>/context/`: cached across-cut previews keyed by
  the actual selected sources, so changing a neighbor invalidates the preview.

The existing single-process API serializes manifest edits with an in-process lock
and atomic file replacement. Mutations require the current revision. Request IDs
are idempotent, and one scene cannot have two active retries. GPU work shares the
music manager's lock and checks H3's existing queue. No global interruption is used.
Scene work now runs through an explicit global FIFO dispatcher with durable enqueue
times; exports have their own dispatcher. In-flight work resumes before queued work
after a restart. The same ordering powers `queuePosition`: zero means active, one
means next, then two and onward, across films. Cards retain the accepted thumbnail,
dim it, and show Rendering/Waiting/Next/Queued. Rendering pulses slowly and respects
reduced-motion preferences. The queue bar supports selecting another scene or
removing a waiting job. Cancellation preserves its record and cannot interrupt an
already-started provider request. A failed job can only recover when its scene has
no other active job. Timing jobs use the same scene queue but skip OpenAI and GPU locks.
New takes retain a continuity-context hash; unrelated job progress does not create
a stale-context warning, while changed notes or other selected takes do.

When H3LIX's installed prompt parser is available, the exact compiled prompt and
reference counts are validated locally before provider intent/submission. Set
`SOUND_VISION_H3_VALIDATOR` for a different parser location; the provider's own
validation still applies when the local parser is unavailable.

Provider intent is saved before submission. An uncertain submission is never
automatically replayed; **Recover existing run** checks its retained H3 run. Known
request rejections retain their error and require a new explicit retry after the
input/adapter is corrected. On API restart, active requests resume from their
existing job folders. No failed or superseded take is automatically deleted.

Install the existing Manrope font at `assets/fonts/SV-Manrope.ttf`; the compositor
and full export verifier use `.venv-alignment/bin/python`. H3 URL defaults to the
existing loopback service at port 7310; `SOUND_VISION_H3_URL` and
`SOUND_VISION_H3_LIBRARY` provide deployment overrides. Back up `data/film-reviews`
with the original `data/films` and song masters.

## Creating a project from a library song

`Make video → Music video` opens `DirectedVideoWorkspace` with the exact selected
take. Previously this branch opened only the finished-film reviewer and could
show “No video projects” even though the song had arrived correctly.

The creation screen supplies title, optional artist, direction, story/performance
choice and approximate scene length. `Create storyboard` posts to `POST /api/films`
with an idempotent `requestId` and a `takeId`; clients never provide an audio path.
The server requires an existing completed, untrashed song and probes its actual
audio duration. Setup drafts are saved separately for each song.

Preparation is a durable non-GPU film job in `backend/film_creation.py`. It:

1. Measures beats on CPU using the existing analyzer.
2. Divides the song into contiguous 24 fps windows, with no gap or overlap and no
   generated clip longer than 15 seconds. Interior cuts snap to nearby measured
   beats where the duration bounds permit; `cutOnMeasuredBeat` records whether
   each boundary was snapped. End coverage rounds up to the next video frame.
3. For performance/mixed projects, separates vocals and aligns actual sung words
   with the existing alignment runner and the editor's language. Empty vocal
   windows become silent story scenes. The shared vocal cache remains reusable.
4. Uses the connected OpenAI account for a structured storyboard and one generated
   identity/style reference. Model output cannot change the server-owned timings.
5. Saves the plan, shared reference, scene actions and continuity before rendering.

`POST /api/films/{film}/scenes/{index}/generate` creates a first take through the
existing global FIFO. Initial generation uses an image reference, plus the aligned
audio excerpt only for a singing scene. It does not require a previous scene video.
The renderer uses H3LIX's native four-step Turbo workflow, validates the prompt,
persists provider intent before its POST, and normalizes the result to 1080p/24 fps.
The first completed take is selected automatically; subsequent repairs retain the
existing review/accept behavior. The original song supplies every preview and export.

The UI can render one scene or queue the remaining scenes, shows queue positions,
and resumes polling after reload. Finished scenes can be played individually.
Once all scenes have a selected completed take, `Review & export` opens the existing
repair and full-film export tools. The server also rejects incomplete exports.
Draft projects use the same Trash/restore rules as imported projects. Active
preparation, scene and export jobs block deletion.

Preparation artifacts are checkpointed. Restart recovery reuses a saved storyboard
and reference and cannot replace existing generated takes. An interrupted image
submission is deliberately not replayed: the error explains that a new project is
needed to explicitly request another reference. H3 recoveries retain the existing
provider run ID. Do not delete project folders to recover a failed operation.

Current output is landscape 16:9. The creation screen does not claim perfect lip
sync or automatic visual continuity verification; singing, identities and objects
still require review. Beat detection can fail on material without a measurable
pulse; this is reported instead of fabricating a beat map. This workflow does not
automatically render a full movie when a song is handed off or a storyboard is created.

## Verification

### Bounded motion replacement and remembered previews

`frame-regenerate` is a separate repair method for incorrect motion or contaminated
shot order. `repairStartFrame` and `repairEndFrame` are relative to the selected
source scene and must describe at least two seconds inside it. The server extracts
that range's opening frame, generates only the replacement interval through the
existing four-step native H3 path, and stitches it between the original prefix and
suffix. The bad source motion is not sent as a video reference. The input snapshot
retains the full plan and original take for provenance and continuity review.

Audio timing is rebased to the selected source interval, and singing is conditioned
only on its actual aligned vocal words. The original master remains the soundtrack.
Frames outside the selected range retain identical decoded pixels in the lossless
saved candidate. Browser previews use a compatible H.264 encode; final export uses
the existing delivery encode. Both replacement joins still require visual review.

The whole-take source-edit alternative remains generative. It now describes
detected source cuts with ordered `[Shot N] At MM:SS.mmm` markers and no longer
simultaneously demands one uninterrupted shot. Neither prompt syntax validation
nor a video reference imposes a pixel or temporal edit mask. Use a bounded
replacement when surrounding footage must stay unchanged.

Preview choices are saved under `sv-film-previews-v1:<film-id>`, separately per
scene. The latest completed take becomes the preview when it finishes. A manual
choice of an older take survives polling, scene navigation and browser reload,
until another take completes. Scene selection opens the remembered scene preview.
`Use this take` still explicitly commits that candidate to the full film.

`backend/test_film_ranges.py` checks range validation, immutable source snapshots,
vocal-time rebasing, actual lossless outside-frame equality, and browser-compatible
preview output. `scripts/test-film-previews.mjs` covers automatic completed-take
selection, manual comparison persistence and failed-take handling.

The scene-review tests cover idempotent retries, stale/concurrent edits, immutable
context snapshots, original restoration, exact boundary-word timing, preservation
of other scenes, no duplicate provider submission after an uncertain response,
and actual encoded across-cut previews with the correct absolute audio window.

Run the existing service environment's pytest against `backend/test_film_review.py`,
`backend/test_video.py` and `backend/test_api.py`; run `npm run test:video` and the
TypeScript/Vite build locally. Browser and live-render evidence is retained in
`deliveries/two-films-20260910/scene-review/`.

The initial scene-review check finished with 21 backend tests, 11 video tests, a production build,
a verified 4,870-frame full-film export and working candidate-in-context playback.
The original scene selections remain in place. The global music-player footer is
hidden in scene-review mode and its audio is paused on entry, so the film has one
visible playback control and the timeline has room to stay visible.

The repair/queue regression tests additionally cover source-take selection, malformed
repair parameters, exact submitted video bytes, silent/performance audio routing,
FIFO across films, cancellation and restart, and positive/negative shifts of decoded
test frames. Source-edit prompt validation passes against the installed H3 parser.
Its short-description warning is expected: the official guide explicitly allows
video-editing descriptions to scale with the edit instead of the generation word range.

Authoritative reference: [MiniMax H3 full-reference prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md),
sections 2.3, 3 and 4. Installed capability verified in H3LIX `server/graphs.mjs`:
`LoadVideo → GetVideoComponents → ref_videos.ref_video_0`; source audio is only
attached when `includeSoundtrack` is true, which this repair path explicitly disables.

## Vocal gating (September 11, 2026)

`backend/film_voice.py` supplies one contract for creation, current source-edit
prompts, reference duration and mouth review. Narrative scenes and performance
windows with no aligned words have no audio asset or speaker ID. Positive closed
lip, resting jaw and nasal breathing instructions replace repeated singing-related
negations in creation prompts. Global singer direction cannot override a silent
window in storyboard planning. Performance prompts alternate measured vocal windows
and rests, including the rounded generation tail, and retain authored word order
when adjacent alignment spans overlap. Invalid local times stop submission.

The isolated vocal stem, when available, is clipped at the exact scene end before
zero-padding to H3's whole-second duration. It cannot contain the following scene's
vocal onset. The original full mix still supplies playback and export audio.

All initial renders and non-smart repairs now receive a bounded visual review
against those windows; smart repairs retain their source/candidate review. Additional
frames sample rests. Suspected mouthing is flagged; unassessable faces stay uncertain.
This adds one connected-account visual review per completed candidate, after releasing
the GPU lock. It never retries automatically or selects a repair into the film.
Initial takes remain selected as before, with a visible warning when flagged.
Missing neighbors are skipped in context playback; missing scenes disable full export.

H3 is generative. These prompts and audio references guide facial motion; the
installed node exposes no hard mouth-motion mask. Full playback remains necessary.
See `deliveries/vocal-gating-20260911/README.md` for the inspected case and receipt.
