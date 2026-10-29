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
- Run the relevant tests and Ruff. CI covers CDN, transport, profiles and a disposable Drasl smoke test.
