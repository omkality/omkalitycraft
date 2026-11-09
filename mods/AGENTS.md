# OmkalityCraft mod sources

- Publish owned implementation sources here; do not import the old private Git history.
- Keep native security reproducers, lab probes, raw validation, worlds and accounts
  in the private workspace. Do not copy them into this directory or public issues.
- Keep Core generic for its Forge version. Pack-specific composition belongs in packs/;
  common interfaces and optional integrations must remain separate from pack fixes.
- Run the source boundary check and pinned Docker build from the repository root:
  `python scripts/check_mod_sources.py` and `python scripts/check_forge_mods.py`.
- Java sources and resources in the initial import must reproduce the accepted JARs.
  Future behavior changes require component versioning and relevant native tests before
  updating versions.json hashes. Never make a failing hash check update itself.
- No dependency JARs, Minecraft implementations, ABI stubs or test classes in runtime JARs.
- Keep component changelogs and user/owner documentation in Russian; commit subjects in English.
- Component tags mark source versions. Root GitHub Releases remain launcher-only.
