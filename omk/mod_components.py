"""Explicit private server-component inputs for disposable laboratories."""

from pathlib import Path


def add_pack_inputs(parser):
    parser.add_argument("--pack-fix", type=Path)
    parser.add_argument("--server-profile", type=Path)
