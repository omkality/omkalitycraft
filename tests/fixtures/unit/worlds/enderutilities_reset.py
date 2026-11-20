"""Test dependencies for enderutilities reset."""

from launcher.nbt import Tag


def target(dimension):
    return Tag(
        10,
        {
            "posX": Tag(3, 640),
            "posY": Tag(3, 200),
            "posZ": Tag(3, 64),
            "Dim": Tag(3, dimension),
            "BlockFace": Tag(1, 1),
            "dPosX": Tag(6, 640.5),
            "dPosY": Tag(6, 200.0),
            "dPosZ": Tag(6, 64.5),
            "DimName": Tag(8, "fixture"),
            "BlockName": Tag(8, "minecraft:stone"),
            "BlockMeta": Tag(1, 0),
            "ItemMeta": Tag(2, 0),
            "Yaw": Tag(5, 23.0),
            "Pitch": Tag(5, 7.0),
        },
    )


def crystal(dimension, slot=0, damage=0):
    return {
        "id": Tag(8, "enderutilities:linkcrystal"),
        "Count": Tag(3, 1),
        "Damage": Tag(2, damage),
        "Slot": Tag(1, slot),
        "tag": Tag(
            10,
            {
                "Target": target(dimension),
                "Owner": Tag(10, {"custom": Tag(8, "keep")}),
                "custom": Tag(8, "keep"),
            },
        ),
    }


def porter(slot=1):
    return {
        "id": Tag(8, "enderutilities:enderporter"),
        "Count": Tag(1, 1),
        "Damage": Tag(2, 1),
        "Slot": Tag(1, slot),
        "tag": Tag(
            10,
            {
                "Selected_linkcrystal": Tag(1, 0),
                "custom": Tag(8, "keep"),
                "Items": Tag(
                    9,
                    (
                        10,
                        [
                            Tag(
                                10,
                                {
                                    "Slot": Tag(1, 0),
                                    "id": Tag(8, "enderutilities:endercapacitor"),
                                    "Count": Tag(1, 1),
                                    "Damage": Tag(2, 2),
                                    "tag": Tag(
                                        10, {"EnderChargeAmount": Tag(3, 75000)}
                                    ),
                                },
                            ),
                            Tag(10, crystal(-18000, 1)),
                            Tag(10, crystal(0, 2)),
                        ],
                    ),
                ),
            },
        ),
    }


def player(*items):
    return {
        "Dimension": Tag(3, 0),
        "Inventory": Tag(9, (10, [Tag(10, x) for x in items])),
        "XpLevel": Tag(3, 12),
        "ForgeCaps": Tag(10, {"unknown": Tag(8, "keep")}),
    }
