# H3LIX adapter

The canonical applied source is in the sibling H3LIX repository's `server/` directory. This folder retains the small adapter, its tests, a graph/job patch, and hashes of the pre-change files for reproduction. Check `baseline.json` before applying `h3lix.patch`; do not overwrite later H3LIX changes with an older full source snapshot.

The request opt-in is `audioDrive: "vrgdg-source"`. It requires Reference to Video, exactly one character image and one audio clip, the current fused model, and a scene fitting 362 H3 frames. The adapter pins four steps and rejects incompatible models or additional post-production. An unavailable ComfyUI node causes a clear failure before submission.

The additional `audioDrive: "vrgdg-vocal"` opt-in requires Singularity first pass, one continuous recorded vocal, one or more character/storyboard images, and at most one source video for an edit. It preserves eight steps and all visual references, routes the audio-driven joint latent into the sampler, and passes the recorded vocal through the canonical video mux. `integrations/h3-singularity-first-pass/vocal-lock.patch` records the graph and job changes required alongside this adapter. The standard lab runtime must have the same unmodified VRGDG node installed; availability is checked before submission. Ordinary requests with no audio-drive flag retain their prior behavior.

Install the unmodified neighboring `vrgdg-audio-drive/` package as a separately mounted ComfyUI custom node. The H3LIX Turbo compose recipe now mounts it read-only at `/opt/ComfyUI-fused/custom_nodes/vrgdg_audio_drive`. Source and deployment must both be present; the graph patch alone cannot supply the node.

See `docs/backend/AUDIO_DRIVE.md` for tested behavior, limits and deployment receipts.
