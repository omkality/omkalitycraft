"""Local release preparation. Publishing is never an unauthenticated API route."""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from launcher.releases import ReleaseError, safe_path, sha256_file, sign_release


def signing_key(path: Path, public_keys_path: Path) -> Ed25519PrivateKey:
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ReleaseError("Неподдерживаемый ключ подписи.")
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        data = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key_id = hashlib.sha256(public).hexdigest()[:16]
    keys = json.loads(public_keys_path.read_text()) if public_keys_path.exists() else {}
    keys[key_id] = base64.b64encode(public).decode()
    public_keys_path.parent.mkdir(parents=True, exist_ok=True)
    public_keys_path.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    return key


def build_release(
    files_root: Path,
    *,
    pack_id: str,
    version: str,
    minecraft: str,
    platform: str,
    launch: dict[str, Any],
    key: Ed25519PrivateKey,
) -> dict[str, Any]:
    files = []
    for path in sorted(files_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(files_root).as_posix()
        safe_path(relative)
        if not path.resolve().is_relative_to(files_root.resolve()):
            raise ReleaseError(
                "В исходниках сборки обнаружена внешняя символическая ссылка."
            )
        files.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "executable": relative == launch["java"]
                or (platform != "windows-x64" and os.access(path, os.X_OK)),
            }
        )
    return sign_release(
        {
            "schema": 1,
            "pack_id": pack_id,
            "version": version,
            "minecraft": minecraft,
            "loader": "forge",
            "platform": platform,
            "files": files,
            "launch": launch,
        },
        key,
    )
