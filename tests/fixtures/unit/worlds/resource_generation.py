"""Test dependencies for resource generation."""

import json

from omk.worlds.resource_generation import PROFILE


def source_fixture(root):
    profile = json.loads(PROFILE.read_text())
    root.mkdir(exist_ok=True)
    for relative in profile["cofh_files"]:
        populate = {
            "ordinary": {"dimension": {"restriction": "blacklist", "value": [-1, 1]}},
            "story": {"dimension": {"restriction": "whitelist", "value": [17]}},
        }
        if relative.endswith("01_thermalfoundation_ores.json"):
            for name in ["oil_ore", "amber", "aquamarine"]:
                populate[name] = {
                    "dimension": {"restriction": "whitelist", "value": [0, 7]},
                    "generator": {"cluster-size": 8, "material": "minecraft:stone"},
                    "cluster-count": 12,
                }
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"populate": populate}))
    for item in profile["forge_files"]:
        tree = {}
        for rule in item["rules"]:
            node = tree
            for part in rule["path"][:-1]:
                node = node.setdefault(part, {})
            node[rule["path"][-1]] = (
                rule["kind"]
                + ':"'
                + rule["path"][-1]
                + '" <\r\n    '
                + rule["reference"]
                + "\r\n>\r\n"
            )
            for flag in rule.get("flags", []):
                node = tree
                for part in flag["path"][:-1]:
                    node = node.setdefault(part, {})
                node[flag["path"][-1]] = (
                    "B:" + flag["path"][-1] + "=" + flag["value"] + "\r\n"
                )

        def render(node):
            return "".join(
                k + " {\r\n" + render(v) + "}\r\n" if isinstance(v, dict) else v
                for k, v in node.items()
            )

        path = root / item["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("~CONFIG_VERSION: 0.3\r\n" + render(tree)).encode())
    (root / "undergroundbiomes.cfg").write_text(
        "general {\n S:IncludedDimensions=0,7\n}\n"
    )
    return root
