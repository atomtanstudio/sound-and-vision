# Backend verification — 10 September 2026

## Actual media

| Run | Audio duration | Pipeline time | Native truncation | Output checks |
|---|---:|---:|---|---|
| City Lights baseline | 59.359 s | 22.488 s | Neither score nor semantic | 48 kHz stereo, finite/non-silent, zero detected full-scale samples |
| Homeward Light, take 1 | 36.719 s | 18.171 s | Neither | WAV, FLAC and MP3 validated |
| Homeward Light, take 2 | 54.599 s | 22.062 s | Neither | WAV, FLAC and MP3 validated |

The baseline used the official original example, full symbolic planning and default sampling. The two Homeward Light takes were submitted through the actual browser UI with original lyrics and independent random seeds. No target duration was forced. These are measured local examples, not a guarantee of similar timing or quality for other songs.

The baseline's peak PyTorch allocation was 8,423,209,984 bytes; peak reservation was 8,625,586,176 bytes. These are process allocator measurements, not whole-device peak VRAM. The GPU returned to its earlier 4735 MiB usage after the completed music jobs; later other GPU work changed that baseline.

Original artifacts remain on Legion under `data/runs/<take-id>/attempt-001/`:

- Baseline: `eabe44e7a8da4e8ca9cd8b92a94caa78`
- Take 1: `68e25698c84f4d968650cb6a40f0674e`
- Take 2: `fc549297d6fa47be85e340f45e964dfb`

Exact settings, seeds, revisions, timings, output hashes and warnings are in the three `*-delivery.json` receipts and baseline `result.json` under `evidence/`. The app plays these through authenticated relative API URLs. Generation records and WAV/FLAC/MP3 are downloadable in Track details.

## Checks performed

- Production build: TypeScript + Vite passed. One build encountered the already observed SMB `.smbdelete*` issue while emptying old output; the old directory was preserved as an ignored build archive, and a fresh standard build passed. No host settings were changed.
- Five backend tests passed: auth/validation, transactional idempotency/persistence, cancel/retry/publication gates, plan-review source preservation, and restart interruption with retained artifacts. Test data lives in isolated temporary directories; tests do not claim real inference.
- Twelve existing UI groups passed with an intentionally offline provider fixture, so regression checks did not accidentally submit GPU jobs.
- Live browser: a real generated song played and sought correctly; its player used the measured duration, all three formats were exposed, and the generated soundtrack carried into Video.
- Live connected-form validation: missing lyrics are labelled Required, the editor is focused, and no invalid GPU job is submitted.
- Live browser: two new takes were submitted, assigned durable IDs, and remained visible after browser reload.
- After an actual idle service restart, all three completed takes reopened with the same IDs. All nine audio exports returned correct byte-range responses.
- Direct API without credentials returned 401; the foreign-Origin proxy test returned 403; a non-downloadable internal spec filename returned 404. The API listens on Legion loopback only. Service token mode 0600 and root/data mode 0700 were verified. The actual credential was absent from source, docs and built assets.
- A real additional plan was generated and paused for review. Cancelling that review/waiting job worked. When other ComfyUI work appeared, the admission check deferred music generation; no external job was interrupted or unloaded.

## Evidence limits

The additional live active-sampling cancellation and exact-plan-to-audio continuation checks did **not** finish: another GPU service was active/resident and Sound/Vision correctly waited. The verification job `90aa62ded8684f5c8976967d878202e3` was cancelled rather than left queued for a later surprise render. Its original real score is retained in its attempt and copied to `evidence/review-score.abc`.

Cancellation callbacks, targeted retry and unchanged-plan loading are implemented against upstream APIs and covered at the application boundary by tests. That is not equivalent to successful live verification of every inference-stage cancellation or approved-plan recording. See `evidence/lifecycle-verification.json`. Re-run the explicit lifecycle helper when the shared GPU is available before treating these advanced paths as fully verified.

Structural audio checks do not establish subjective music quality, perfect lyric delivery or singing alignment. No transcript-based coverage or human listening verdict is asserted here.

## Feature / evidence matrix

| Capability | State |
|---|---|
| Isolated pinned YuE2 generator + listening decoder | Installed and real-generation verified |
| Lyrics/style → one take | Verified with real output |
| Lyrics/style → two independent takes through UI | Verified with real outputs |
| Stage/progress and durable library | Implemented; observed in real jobs and after restart |
| Actual-duration playback/seek | Live browser verified |
| WAV/FLAC/MP3 export | Real file validation and HTTP range delivery verified |
| Metadata rename/project/favorite | Implemented and boundary tested; not a full multi-user library |
| Idempotent submissions / queued cancel / retry record preservation | Backend tests passed; queue/review cancellation observed live |
| Symbolic planning + pause for review | Real plan generated and retained |
| Active inference cancellation / edited or exact-plan continuation to audio | Implemented; remaining live verification blocked by shared GPU work |
| External GPU contention handling | Real wait observed; no atomic lease shared with unrelated apps |
| OpenAI sign-in/writing / automatic cover execution | Not connected in this phase |
| SQLite metadata | Live and persistent |
| D1 deployment | Schema-compatible preparation only; not deployed |
| Imported audio / video rendering / forced alignment / singing synchronization | Not implemented in this phase |

## Reproduction

See [OPERATIONS.md](OPERATIONS.md). `scripts/verify-live-music.mjs` deliberately submits two real songs. `deploy/verify_runtime.py --generate` deliberately creates/retries a retained workflow-check take. Do not run them as generic health checks.

The runtime pinning, requests, deliveries, backend JUnit report, live-browser receipt, restart/download receipt, lifecycle limitation, dependency metadata, and captured actual library are all under this directory and `evidence/`.

## OpenAI and reference milestone — 10 September 2026

| Path | Live result |
|---|---|
| Isolated device login | User signed in; account persisted across service restarts; 6 writing models and native image capability discovered |
| Lyric drafting | Original structured lyric proposal succeeded using the account default, GPT-6-Astra |
| Song ideas in browser | Three choices; review, apply and undo verified |
| Reference transcription | Original 59.4 s MP3 → melody ABC, 5.22 s end-to-end; 3,534,086,144 B peak Torch allocation; no warnings |
| Reference-to-song | New 59.7987 s, 48 kHz stereo take in 23.7917 s; external ABC used (0 score-generation tokens); no truncation warnings |
| Native account covers | Two validated 1254×1254 PNGs attached to baseline and reference-generated take |
| Agentic score edit | Harmony proposal passed exact Vocal/Ins melody, timing, meter and tempo comparison |
| One/two cover scheduling | Tested one cover job per take, no duplicate scheduling on idempotent resubmission |
| Browser reference workflow | Actual file upload, reviewed score application, melody mode, reference ID and reload persistence verified |
| Genre browsing | Genre filter finds the reference take; genre sorting implemented |
| Backend regression | 11 tests passed |
| Existing browser regression | 12 check groups passed |
| Assistance browser checks | Account, ideas, reference persistence, genre filtering, image display and score-edit handoff passed |
| Production build | TypeScript and Vite build passed; old SMB output directory archived before rebuilding |

The initial image attempts failed because the standalone Codex release omitted the native tool host; the official full package resolved this without weakening sandbox settings. The initial harmony proposal used unsupported `C6/9` notation and was rejected. The prompt now includes the verified native grammar and allowed chord qualities; the next live proposal passed. Original inputs were retained in both cases.

Evidence: `assistance-verification-result.json`, `final-assistance-result.json`, `reference-cover-delivery.json`, `reference-models.lock.json`, `assistance-tests.xml`, `assistance-browser.json`, and `assistance-browser.png` in `evidence/`. The browser receipt uses existing completed requests when invoked with `--resume`; it does not create duplicate account/GPU work.

These checks establish working connections, structural validity, persistence and browser behavior. They do not establish subjective song quality, exact audible adherence to every transcribed note, perfect lyric singing, or waveform-preserving edits. Earlier active-sampling cancellation/plan-continuation limitations above remain separate. No official demo recordings were imported.
