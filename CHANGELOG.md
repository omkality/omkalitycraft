# Changelog

## 0.3.0.dev5 — real DJ2 command checks and moderator policy

- Add reproducible full Forge teleport, cooldown, movement/damage, TPA, back and restart scenarios.
- Add a moderator rank with only ban/pardon/banlist/kick/mute/unmute, without OP or gameplay advantages.
- Reproduce unsafe stock RTP destinations and disable that command in the initial server profile.
- Characterize the stock FTB mute bypass and verify the separate private Core adapter with guarded lab scenarios.
- Keep command fixtures bounded, isolated and synchronized with actual console completion.
- Preserve stock cooldown restart and within-block movement limitations in the command reference.

## 0.3.0.dev4 — operator tools and quiet client crash reports

- Remove all diagnostic/export controls from the player launcher.
- Capture bounded crash summaries automatically; queue offline reports and upload only with a game session.
- Add an authenticated upload-only inbox with UUID checks, rate/size/count/age limits and no public read API.
- Provide private local operator commands for server diagnostics, report retrieval and Drasl invitations.
- Keep operator keys, exports and report storage outside player bundles, CDN and Git.
- Test real Drasl/Granian/CLI boundaries in a disposable lab; game commands remain a separate milestone.

## 0.3.0.dev3 — bounded local diagnostics

- Rotate game/launcher logs; drain bounded stdout even after a disk write failure.
- Export allowlisted, redacted diagnostic ZIPs from Help or the CLI, with size/retention limits.
- Preserve crash causes, JVM reports, launch metadata and exit codes without account files or worlds.
- Bound Java 1.12.2 logging and disposable auth container logs.
- Pin Java 8 Log4j 2.25.5 for explicit staging/labs; replace legacy 2.8.1/2.15.0 in tested copies.
- Keep production monitoring, other mod log files and GTNH runtime validation separate.

## 0.3.0.dev2 — pack integrity and server checks

- Show only Minecraft versions in the skin-model selector.
- Raise per-pack heap ceilings to 16 GiB while keeping 6 GiB defaults and machine headroom.
- Repair deleted Java/mod/config/font/library files and same-size corruption without resetting personal maps.
- Avoid rewriting unchanged options; verify JourneyMap preferences survive repair and upgrades.
- Silently remove extra files from managed mod folders without following directory links.
- Verify mod hashes before process creation; keep identity authentication with Drasl.
- Add loopback-only protocol players for real server tests; private Core integration stays outside this repository.


## 0.3.0.dev1 — player settings and Forge login checks

- Add per-pack RAM sliders, portable preferences, machine-aware limits and low-memory warnings.
- Pass selected memory to Java; reject release JVM options that override the player heap limit.
- Seed the required Russian font, first-run language and compatible servers from signed defaults.
- Preserve personal options, custom servers and unknown NBT fields; back up changed files.
- Restore archived square JourneyMap/no-grid defaults once without overwriting player changes.
- Fix default-skin side hair, clarify skin models and unprepared packs, and add creator social links.
- Verify real DJ2 login/UUID and reject another nickname, invalid tokens and revoked sessions.
- Track remaining in-game validation explicitly; window capture failed, so visual game checks remain open.


## 0.3.0.dev0 — portable installation, pack UI and launcher updates

- Install signed platform releases, resume interrupted downloads and repair damaged managed files.
- Preserve player files and retain signed ownership history across interrupted pack upgrades.
- Launch bundled Java and Forge with authlib-injector and a renewed game session.
- Add Rubik Medium, pack artwork/links/credits, visible download states and an animated skin preview.
- Decode and normalize bounded PNG uploads; explain legacy formats and Steve/Alex models.
- Remove session-management clutter from the player UI; retain account revocation in the backend.
- Add TUF launcher updates, isolated version directories and health-checked fallback.
- Build portable distributions and smoke-test actual packaged startup on three operating systems.
- Verify a real DJ2 client/server login and Windows executable updates in isolated local labs.

Public deployment, GTNH and game distributions for other platforms remain separate work.

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
