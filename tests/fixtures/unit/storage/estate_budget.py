"""Test dependencies for estate budget."""

import pytest

GIB = 1024**3


@pytest.fixture
def report():
    def resource(name, role, category, apparent, allocated=None):
        return {
            "id": name,
            "role": role,
            "categories": {
                category: {
                    "apparent_bytes": apparent,
                    "allocated_bytes": apparent if allocated is None else allocated,
                }
            },
        }

    return {
        "resources": [
            resource("dj2", "source", "active_world", 20 * GIB),
            resource("other", "source", "active_world", 10 * GIB),
            resource("old", "source", "retained_world_generations", 4 * GIB),
            resource("backups", "store", "store", 20 * GIB),
            resource("auth", "auth", "auth", GIB),
        ],
        "filesystems": [
            {
                "resources": ["dj2", "other", "old", "backups", "auth"],
                "total_bytes": 200 * GIB,
                "available_bytes": 100 * GIB,
            }
        ],
    }
