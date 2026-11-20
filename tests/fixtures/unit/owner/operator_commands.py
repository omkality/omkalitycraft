"""Test dependencies for operator commands."""

from omk.owner.admin import (
    load_operator_config,
)


def config(tmp_path):
    private = tmp_path / ".omk-admin"
    private.mkdir(mode=0o700)
    path = private / "operator.toml"
    path.write_text(
        'schema=1\n[auth]\norigin="http://127.0.0.1:1"\n[servers.dj2]\nroot="../server"\n'
    )
    return load_operator_config(path), path
