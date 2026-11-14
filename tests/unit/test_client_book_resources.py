import json
import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "mods/forge-1.12.2/client"
verify = runpy.run_path(str(CLIENT / "verify_targets.py"))["verify_book_resources"]


def test_book_pack_declares_modern_language_format():
    assert verify(CLIENT / "resources") == 4


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "legacy",
        "helper_package",
        "optional",
        "global",
        "locale",
        "pagination",
        "duplicate",
        "crlf",
        "space",
        "frozen_number",
        "false_free_cost",
    ],
)
def test_book_pack_rejects_missing_or_incompatible_locale_resources(tmp_path, fault):
    resource = tmp_path / "resources"
    shutil.copytree(CLIENT / "resources", resource)
    if fault == "missing":
        (resource / "pack.mcmeta").unlink()
    elif fault == "legacy":
        (resource / "pack.mcmeta").write_text(json.dumps({"pack": {"pack_format": 2}}))
    elif fault == "crlf":
        path = resource / "mixins.omkalityclient.books.json"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    elif fault in {"helper_package", "optional", "global"}:
        path = resource / "mixins.omkalityclient.books.json"
        data = json.loads(path.read_bytes())
        if fault == "helper_package":
            data["package"] = "net.omkality.client.books"
        elif fault == "optional":
            data["required"] = False
        else:
            data["mixins"] = ["PatchouliEditionMixin"]
        path.write_text(json.dumps(data))
    else:
        path = resource / "assets/omkalityclient/lang/ru_ru.lang"
        data = path.read_text(encoding="utf-8")
        if fault == "duplicate":
            data += "omkalityclient.books.locale=ru_ru\n"
        else:
            before, after = {
                "locale": ("locale=ru_ru", "locale=en_us"),
                "pagination": ("Оглавление\\n\\n", "Оглавление"),
                "space": ("starting=Запуск:", "starting=Запуск: "),
                "frozen_number": ("running=Расход:", "running=Расход: 50"),
                "false_free_cost": ("missing_cost=Не задано", "missing_cost=Бесплатно"),
            }[fault]
            data = data.replace(before, after)
        path.write_text(data, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        verify(resource)
