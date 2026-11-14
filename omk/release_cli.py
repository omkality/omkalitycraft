"""Explicit, local release preparation; no live deployment side effects."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from launcher.install import current_platform
from launcher.version import VERSION
from omk.backup_store import _sync_directory
from omk.fs import resolved
from omk.publish import build_release, signing_key
from omk.release_store import ReleaseStore, ReleaseStorePolicy
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
    launcher.add_argument(
        "--github-asset-url",
        help="Versioned public launcher ZIP URL; signed in TUF with CDN fallback",
    )
    pack = actions.add_parser("pack", help="Sign a prepared modpack files directory")
    pack.add_argument("--files", type=Path, required=True)
    pack.add_argument("--launch-profile", type=Path, required=True)
    pack.add_argument("--private-key", type=Path, required=True)
    pack.add_argument("--public-keys", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--pack-id", required=True)
    pack.add_argument("--minecraft", required=True)
    pack.add_argument(
        "--snapshot-root",
        type=Path,
        default=os.environ.get("OMK_RELEASE_SNAPSHOT_ROOT"),
        help="Retain verified client files in a dedicated local release store",
    )
    pack.add_argument(
        "--minimum-launcher-version",
        default=VERSION,
        help="Signed schema-2 minimum launcher requirement",
    )
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
            github_asset_url=getattr(args, "github_asset_url", None),
        )
        return {"ok": True, "trusted_root": str(root), "deployed": False}
    if args.private_key.resolve().is_relative_to(args.files.resolve()):
        raise ValueError("Private signing key must be outside modpack files")
    snapshot_root = getattr(args, "snapshot_root", None)
    if snapshot_root is not None:
        _check_snapshot_paths(args, snapshot_root)
    key = signing_key(args.private_key, args.public_keys)
    envelope = build_release(
        args.files,
        pack_id=args.pack_id,
        version=args.version,
        minecraft=args.minecraft,
        platform=args.platform,
        launch=json.loads(args.launch_profile.read_text(encoding="utf-8")),
        key=key,
        minimum_launcher_version=getattr(args, "minimum_launcher_version", None),
    )
    snapshot = _snapshot(args, envelope, snapshot_root)
    _write_manifest(args.output, envelope)
    result = {
        "ok": True,
        "manifest": str(args.output),
        "files": len(envelope["manifest"]["files"]),
        "deployed": False,
    }
    if snapshot is not None:
        result["snapshot"] = str(snapshot.directory)
    return result


def _check_snapshot_paths(args, root):
    store, files = resolved(root), resolved(args.files)
    if store.is_relative_to(files) or files.is_relative_to(store):
        raise ValueError("Snapshot store and client files must be separate")
    for path in [args.private_key, args.public_keys, args.output]:
        if resolved(path).is_relative_to(store):
            raise ValueError(
                "Release outputs and signing keys must be outside snapshots"
            )


def _snapshot(args, envelope, root):
    if root is None:
        return None
    policy = ReleaseStorePolicy.environment()
    keys = json.loads(args.public_keys.read_bytes())
    if root.exists():
        store = ReleaseStore(root, policy, keys)
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        store = ReleaseStore.create(root, policy, keys)
    return store.publish(args.files, envelope)


def _write_manifest(output: Path, envelope: dict) -> None:
    if output.is_symlink() or output.is_junction():
        raise ValueError("Linked manifest output")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=".omk-manifest-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(envelope, ensure_ascii=False).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        _sync_directory(output.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
