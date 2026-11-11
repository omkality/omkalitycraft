"""Non-secret per-attempt write fence shared read-only with a Docker helper."""

import json
import os
import tempfile

from omk.admin import AdminError, _private_path
from omk.backup_store import _sync_directory


def directory(config, operation):
    base = _private_path(config.private, "world-cutover-control")
    base.mkdir(mode=0o700, exist_ok=True)
    path = _private_path(config.private, "world-cutover-control/" + operation)
    if not path.exists():
        if len(list(base.iterdir())) >= 1000:
            raise AdminError("Archive old world cutover control directories")
        path.mkdir(mode=0o755)
    # Mount the per-operation directory: atomic replacement of a single mounted
    # inode would leave a stale fence visible inside a container.
    path.chmod(0o755)
    return path


def publish(config, operation, stage, lease):
    root = directory(config, operation)
    value = {"schema": 1, "operation": operation, "stage": stage, "write_lease": lease}
    descriptor, name = tempfile.mkstemp(prefix=".lease-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # This contains no credentials. Other-UID container root with every
        # capability dropped must be able to read it on a native Linux host.
        os.chmod(name, 0o644)
        os.replace(name, root / "lease.json")
        _sync_directory(root)
    finally:
        if os.path.exists(name):
            os.unlink(name)
