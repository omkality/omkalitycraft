# OmkalityCraft development

Read `docs/DEVELOPMENT.md` and `CHANGELOG.md` before changing the architecture.

- Development is on `dev`; use focused commits and task branches with PRs into `dev`.
  `master` is for tested milestones. No force pushes or automatic production deployments.
- Keep the launcher simple: invitation, nickname, issued password once, remembered revocable session.
  Authentication belongs to Drasl + authlib-injector. Do not restore Telegram or custom password security.
- Target Windows, Linux and macOS. Keep portable session files in the launcher's data directory;
  never assume Windows-only paths, Java executables or UI behavior in shared code.
- Session files may contain game bearer tokens, never account passwords or Drasl management tokens.
  Do not claim that portable files are encrypted or protected from the user's own processes.
- Python owns launcher/API/operations; version-specific Forge integration uses adapters and Java as needed.
  Use FTB/ServerUtilities for claims and available commands. Keep pack logic outside GUI code.
- Never commit `.env`, session tokens, keys, account databases, worlds, modpack payloads or OmkalityCore.
  OmkalityCore is outside this public repository by the user's explicit choice.
- Use temporary test data and isolated lab containers. No tests against existing player data.
  Do not delete/wipe worlds, reset schemas or flush live services.
- Do not claim a profile, security control or mod works before the relevant real test passes.
  Distinguish transport/API checks from Minecraft client/server checks.
- Pin external runtime artifacts and images by version/hash. Keep dependency changes in `uv.lock`.
- Keep launcher/API in this monorepo. Put all player/runtime/update data below the portable root.
- Launcher updates use TUF and separate version folders with health-checked handoff; never overwrite
  the running executable or extract an update over userdata/instances. Private signing keys stay offline.
- Run the relevant tests and Ruff. CI covers CDN, transport, profiles and a disposable Drasl smoke test.
- Keep CHANGELOG.md and owner/player documentation in Russian; commit subjects and AGENTS.md remain English.
- Public GitHub Releases are player launcher distributions, not source-only development checkpoints. Attach only tested portable launcher bundles and their release integrity/license material; never upload the backend, repository source bundles, server data or modpack payloads. Git history/tags track development checkpoints independently. Do not publish loopback previews as player releases.
- After launcher UI changes, show the actual UI state as a PNG and provide a link to the tested local executable bundle for review. Never substitute a GitHub screenshot for launcher visual validation.
- Use a new screenshot filename for every shared UI revision; never overwrite a PNG after linking it in chat, because the app may cache it.
- Prefer validated environment overrides with documented defaults for deployment policy; do not require source edits for operational limits. Keep security/trust keys and release integrity outside arbitrary player overrides.
- Run crash/bug/duplication labs locally in isolated Linux Docker volumes matching the intended server runtime; do not load the public server for development tests. Budget backups, logs, worlds, staging and free disk reserve together before deployment.
