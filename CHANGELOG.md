# Changelog

## 0.2.0.dev1 — portable launcher accounts

- Add Qt registration, issued-password acknowledgement, login and automatic session restore.
- Save only game-scoped tokens in the launcher's own data folder, without OS keyring dependencies.
- Upload classic/slim skins, change passwords and revoke all sessions after password confirmation.
- Keep network requests off the UI thread and preserve issued passwords across request failures.
- Block simultaneous windows using the same session file; write sessions atomically.
- Exclude private runtime files from manifests/staging and deny their direct CDN download.
- Exercise real widgets against disposable Drasl; verify genuine token expiry separately.
- Test account/UI code on Windows, Linux and macOS in CI.

Game installation, real Forge login and standalone platform distributions remain next steps.

## 0.2.0.dev0 — development foundation

- Start a `dev` branch for small, reviewable development steps.
- Keep CDN/manifest serving independently runnable; fix settings paths after the API directory move.
- Retire the abandoned Telegram/custom-auth prototype from the current source tree.
- Add the `omk` CLI, separate DJ2/GTNH profiles and an isolated Drasl 4.0.0 integration lab.
- Check invitations, skin access, game identity, join verification, refresh and session revocation.
- Add automated checks; keep credentials, worlds, client payloads and OmkalityCore outside Git.

This is not a playable launcher release. GUI registration, OS credential storage and real Forge
authentication remain to be implemented and tested.

## 0.1.0

Existing repository milestone retained in Git history.
