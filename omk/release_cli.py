"""Explicit, local release preparation; no live deployment side effects."""

import argparse
import json
from pathlib import Path

from launcher.install import current_platform
from omk.publish import build_release, signing_key
from omk.updates import publish_update


def add_release_commands(subparsers) -> None:
    release = subparsers.add_parser("release", help="Prepare signed releases locally")
    actions = release.add_subparsers(dest="release_type", required=True)
    launcher = actions.add_parser(
        "launcher", help="Sign a portable launcher ZIP with TUF"
    )
    launcher.add_argument("--repository", type=Path, required=True)
    launcher.add_argument("--keys-dir", type=Path, required=True)
    launcher.add_argument("--archive", type=Path, required=True)
    launcher.add_argument("--entrypoint", required=True)
    pack = actions.add_parser("pack", help="Sign a prepared modpack files directory")
    pack.add_argument("--files", type=Path, required=True)
    pack.add_argument("--launch-profile", type=Path, required=True)
    pack.add_argument("--private-key", type=Path, required=True)
    pack.add_argument("--public-keys", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--pack-id", required=True)
    pack.add_argument("--minecraft", required=True)
    for command in [launcher, pack]:
        command.add_argument("--version", required=True)
        command.add_argument("--platform", default=current_platform())


def prepare_release(args: argparse.Namespace) -> dict:
    if args.release_type == "launcher":
        root = publish_update(
            args.repository,
            args.keys_dir,
            args.archive,
            args.version,
            args.entrypoint,
            platform=args.platform,
        )
        return {"ok": True, "trusted_root": str(root), "deployed": False}
    if args.private_key.resolve().is_relative_to(args.files.resolve()):
        raise ValueError("Private signing key must be outside modpack files")
    key = signing_key(args.private_key, args.public_keys)
    envelope = build_release(
        args.files,
        pack_id=args.pack_id,
        version=args.version,
        minecraft=args.minecraft,
        platform=args.platform,
        launch=json.loads(args.launch_profile.read_text(encoding="utf-8")),
        key=key,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    return {
        "ok": True,
        "manifest": str(args.output),
        "files": len(envelope["manifest"]["files"]),
        "deployed": False,
    }
