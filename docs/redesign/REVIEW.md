# Design review receipt

10 September 2026. Scope: one clean music-creation UI, using Suno's layout as a baseline and YuE2's documented controls.

An independent read-only critic reviewed actual screenshots. The critic did not write the product or conduct the implementer's browser tests. Reference coverage included official Suno Simple/Advanced screenshots and the implementer's direct inspection of the user's signed-in Create page.

## Candidate 1 — needs revision

The critic found the approach substantially calmer and visually distinct, with a clear rail and usable results width at 1047 px. Two material issues:

1. Advanced lyrics consumed the visible form, hiding writing/composition/sampling options without a continuation cue.
2. Mobile library titles, metadata, filters and action targets were too small.

A persistent selected/playing indication was also recommended.

## Candidate 2 — mobile pass, final Advanced check

Reduced the initial Advanced lyrics area, added an overflow-aware scroll button, enlarged mobile titles/metadata/filters and action targets, and switched to one cover column at narrow widths. Selected/Playing state now remains visible on the active cover.

The first refreshed Advanced capture occurred before the ResizeObserver rendered the scroll hint. The critic correctly flagged that the screenshot did not prove the intended behavior. Runtime geometry confirmed overflow and the button in the accessibility tree. The capture now explicitly waits for this rendered control.

## Final verdict

**PASS — visual design milestone.** The final Advanced capture exposes Writing assistant and More options below. The critic judged the reviewed desktop, medium, mobile, light and dark views approachable, restrained, clearly organized, and reasonably competitive with the Suno reference for clarity and finish.

This is a bounded qualitative review, not an objective claim of superiority over every Suno workflow, accessibility audit, or model-output assessment. User acceptance is still pending.

## Verification

- `npm run build` passed TypeScript and production bundling.
- `scripts/verify-studio.mjs`: 11 check groups passed, Chromium 152.0.7977.8, zero uncaught errors. The receipt is `evidence/verification.json`.
- Initial/system theme, persisted theme and keyboard radios; sample playback, alternate takes, seek, pause behavior; library discovery; two-take validation/export including exact 63-bit seeds and distinct cover requests; one-take/reload persistence; Home/project creation; Video handoff; account dialog; responsive layouts in both themes at 320, 390, 820, 1047, 1440 and 1920 px.
- `db/0001_music.sql` applied in SQLite 3.53.4; two takes/two covers inserted, invalid third take rejected, foreign keys valid. Receipt: `evidence/schema-verification.json`. This is not a live D1 test.
- In-app browser used for direct live inspection. Isolated Playwright Chromium used for repeatable fixed-size captures because the internal browser's viewport override previously produced unreliable captures.

Screenshots in `evidence/`: Simple desktop/medium/mobile in both themes; mobile library; desktop Advanced/list/Home. `scripts/capture-studio.mjs` reproduces them from a clean browser context.

## User-directed navigation refinement

After the visual milestone, the user requested a wider, collapsible rail and a continuous creation panel. The rail now has a one-line wordmark and the standard panel open/close control, retains icons while collapsed, persists the desktop choice, and overlays the workspace on compact screens. The creator is one scroll container, including its action area; the previous overflow hint and independent pinned footer were removed. Unsorted replaces the displayed default-folder name, with Save to project identifying the control.

The implementing agent visually inspected the new expanded, collapsed, desktop and mobile captures. Twelve browser groups passed, including rail keyboard/persistence behavior, draft preservation, a single creator scroll path, compact drawer dismissal/focus isolation, renamed-project search and duplicate-name handling. This refinement was not submitted for another independent critic verdict.
