"""Reviewed DJ2 dimension layout and the files removed from a reset candidate."""

import re

from omk.shared.fs import regular

RESOURCE = -18000
STORAGE = {
    4: "Dim-Aether",
    50: "Abyssal_Wasteland",
    51: "The_Dreadlands",
    52: "Omothol",
    53: "The_Dark_Realm",
    420: "Eden",
    421: "WildWood",
    422: "Apalachia",
    423: "Skythern",
    424: "Mortum",
    425: "Iceika",
    426: "Arcana",
    427: "Vethea",
}
MAIN_FILES = frozenset(
    {
        "forcedchunks.dat",
        "multipart.dat",
        "ruins.txt",
        "RuinsPositionsFile.txt",
        "data/Mineshaft.dat",
        "data/Mansion.dat",
        "data/Monument.dat",
        "data/Stronghold.dat",
        "data/Temple.dat",
        "data/Village.dat",
        "data/villages.dat",
    }
)


def _check_named_provider(world, dimension):
    if dimension == 4:
        path, key = "aether_legacy.cfg", "aether_dimension_id"
    elif dimension in range(50, 54):
        name = STORAGE[dimension].replace("_", " ")
        if dimension == 50:
            name = "The " + name
        path = "abyssalcraft.cfg"
        key = name if dimension == 52 else f'"{name}"'
    elif dimension in range(420, 428):
        name = STORAGE[dimension]
        path, key = "DivineRPG/divinerpg.cfg", name[0].lower() + name[1:] + "Id"
    else:
        return
    root = world.parent
    config = root / "config" / path
    if not regular(config, root) or config.stat().st_size > 2 * 1024**2:
        raise ValueError("Missing reviewed configuration for named dimension")
    values = re.findall(
        r"(?m)^\s*I:" + re.escape(key) + r"=(-?\d+)[ \t]*$",
        config.read_text(encoding="utf-8"),
    )
    if values != [str(dimension)]:
        raise ValueError("Named dimension ID differs from the saved-folder profile")


def layout(dimension: int) -> dict:
    """Resolve a catalog ID to its reviewed save layout and evacuation world."""
    if type(dimension) is not int or not -(2**31) <= dimension < 2**31:
        raise ValueError("Invalid Forge dimension ID")
    if dimension == RESOURCE:
        raise ValueError("Use the dedicated resource reset workflow")
    return {
        "folder": STORAGE.get(dimension, f"DIM{dimension}") if dimension else None,
        "landing_dimension": 0 if dimension else RESOURCE,
    }


def verify_layout(world, dimension, target, files):
    """Require the real saved directory and a protected retained landing dimension."""
    if target != layout(dimension):
        raise ValueError("Selected dimension layout changed")
    folder = target["folder"]
    if folder is not None:
        path = world / folder
        if path.resolve() != path or not path.is_dir():
            raise ValueError("No regular saved directory for the selected dimension")
        if not any(name.startswith(f"{world.name}/{folder}/") for name in files):
            raise ValueError("The selected dimension has no saved files")
    # Unmapped dynamic Forge providers have to use the JED save convention.
    # Known named folders and generic folders must never both claim the same ID.
    if dimension in STORAGE and (world / f"DIM{dimension}").exists():
        raise ValueError("Ambiguous save folders for the selected dimension")
    _check_named_provider(world, dimension)
    if not folder and not any(
        name.startswith(world.name + "/region/") for name in files
    ):
        raise ValueError("The Overworld has no saved terrain")


def omitted(name: str, world: str, dimension: int, reset: dict | None) -> bool:
    """Identify only the selected world's terrain/data in the candidate inventory."""
    relative = name.removeprefix(world + "/")
    if relative == name:
        return False
    if reset is None:
        return relative.startswith(f"DIM{dimension}/") or relative == (
            "omk-resource-world.properties"
        )
    folder = reset["folder"]
    if folder is not None:
        return relative.startswith(folder + "/")
    return (
        relative.startswith("region/")
        or relative in MAIN_FILES
        or re.fullmatch(r"data/(?:villages|Village)_?0\.dat", relative) is not None
    )
