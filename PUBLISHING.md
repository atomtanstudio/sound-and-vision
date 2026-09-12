# Publication preparation

The local repository uses `main`. Private credentials, model weights, generated productions and operational receipts are excluded from Git. The application source and user data have separate backup paths.

The proposed public destination is `atomtanstudio/sound-vision`. It was not present in the configured GitHub account during preparation. No remote repository has been created and nothing has been pushed.

Before publication, review the installation guide and model-license notices. The application remains a self-hosted release candidate: music video is Coming soon, and the current packaged music admission threshold still targets a 24 GB GPU. A verified 16 GB mode and larger local writing-model benchmarks are separate work.

The security-reviewed dependency/configuration changes have been tested locally. They have not been deployed to the existing Linux music service as part of this pass. Keep the existing installation backup and upgrade/recheck it while idle before representing this revision as a fresh GPU-host installation test.

After the owner confirms the public destination, the publication operation is:

```sh
gh repo create atomtanstudio/sound-vision --public --source=. --remote=origin --push
```

This command publishes the committed history. Do not run it against an unaudited checkout. Use `scripts/package-selfhost.py` to produce a separately scanned source ZIP; do not upload the entire working folder or a raw filesystem archive.

Enable GitHub private vulnerability reporting after creating the repository so the security policy has a private reporting channel.

Git commits use the configured account's no-reply address. The private audit report and raw scan/test logs remain outside the repository.
