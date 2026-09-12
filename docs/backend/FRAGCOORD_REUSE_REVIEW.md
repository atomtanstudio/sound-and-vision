# FragCoord reuse review — 2026-09-10

Goal: visualizer code that can be bundled in an Apache-2.0 open-source app with
straightforward redistribution terms. The gallery and editor are useful for
inspiration and shader authoring; public visibility of source alone is not an
explicit grant to redistribute it.

Reviewed live candidates:

| Candidate | Source | Observed terms | Decision |
| --- | --- | --- | --- |
| Ferrofluid Dance — noztol | https://fragcoord.xyz/s/fjdn32rf | Public editable source, About panel describes an audio visualizer; no explicit reuse license was visible in the inspected About/source header/details. | Not bundled. |
| Disc — Xor | https://fragcoord.xyz/s/dzxkjt3k | Public editable source; no explicit reuse license visible in the inspected interface/source header. | Not bundled. |

The editor's documentation (https://fragcoord.xyz/docs) describes custom shader
and audio uniforms. It was not treated as a blanket license for community
creations. This review does not assert that no permissively licensed shaders
exist on FragCoord; it records that permission was not established for the
specific candidates inspected. No marketplace assets were bought or copied.

For this delivery, all eight shaders are original project code under Apache-2.0.
The app uses its own WebGL renderer, not an embedded external editor. It does
not depend on a FragCoord account or a hosted gallery URL. No third-party shader
source was included. Existing font licenses remain separately preserved.

Potential future imports require the exact source, author, license text and any
texture/audio dependency licenses to be saved alongside the imported shader.
MIT, BSD, Apache-2.0 or CC0 can usually fit this approach when their actual
conditions are retained. This is the selection rule for this project.
