"""Test dependencies for game runner."""

from pathlib import Path

from launcher.releases import Release
from launcher.session import Session


def fixture(root: Path):
    folder = root / "instances/test"
    folder.mkdir(parents=True)
    release = Release(
        "test",
        "1.0",
        "1.12.2",
        "windows-x64",
        (),
        {
            "java": "runtime/bin/java",
            "agent": "agent.jar",
            "assets": "assets",
            "natives": "natives",
            "classpath": ["forge.jar"],
            "main_class": "net.minecraft.launchwrapper.Launch",
            "game_args": [
                "--username",
                "{username}",
                "--uuid",
                "{uuid}",
                "--accessToken",
                "{access_token}",
            ],
        },
        "test",
        {},
    )
    session = Session(
        "https://auth.example.com",
        "test_player",
        "12345678-1234-1234-1234-123456789abc",
        "test_player",
        "test-game-token",
        "test-client-token",
    )
    return folder, release, session
