"""Test dependencies for monitoring config."""

import pytest


@pytest.fixture
def config():
    return {
        "schema": 2,
        "host": "owner-host",
        "services": {
            "dj2": {
                "cgroup": "omk-dj2",
                "target": "dj2:19565",
                "release": "candidate-1",
                "dimension_aliases": {"-11": "2"},
            }
        },
    }
