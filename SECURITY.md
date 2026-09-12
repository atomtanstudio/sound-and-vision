# Security and private installations

Sound/Vision is a single-owner self-hosted application. The browser launcher binds to loopback and proxies authenticated requests to the music backend. It is not designed to be exposed directly as a public multi-user service.

Keep `service.token`, `service.env`, `providers.json`, `.env.local`, `.secrets/`, model/runtime folders and the OpenAI account directory private. The Git ignore rules exclude these locations, generated productions and operational delivery artifacts. Back them up separately; a source checkout does not contain your music library or login state.

## Data sent to providers

Choosing OpenAI sends requested writing/image inputs to the configured account runtime. Choosing local models sends those inputs to the selected private-network text and ComfyUI servers. Local mode has no automatic OpenAI fallback. Changing text-server address or backend type does not reuse the previous server's saved API key. Custom ComfyUI workflows execute their installed nodes; import workflows you trust.

Dependency/model installers contact their documented package or model repositories. Local operation does not mean that initial installation works without downloading dependencies and models.

## Reporting a vulnerability

Use the repository's private vulnerability-reporting channel when enabled. If it is unavailable, ask the maintainer for a private contact without posting sensitive details. Include the affected version, prerequisites and a minimal description. Do not include real service tokens, account credentials, private songs or a public working exploit in an issue.

## Release checks

Run `npm run build`, `npm run test:security`, `npm run test:video` and the backend tests in an isolated environment. Run dependency checks against the exact candidate requirements/lockfile, and use a local redacted secrets scanner on both Git history and the release archive before publication. File hashes in `RELEASE_FILES.json` are integrity metadata, not API keys.

The September 2026 source review fixed provider-key carryover, tightened loopback browser/file protections and updated FastAPI/Starlette. Secret scanning and defensive code/regression checks are not a guarantee against every vulnerability; third-party model servers, plugins and future changes need their own review. A production dependency update should be deployed when the music service is idle and rechecked on the target host.
