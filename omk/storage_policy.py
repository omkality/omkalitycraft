"""Read-only deployment budgeting; never changes a world, backup or mod config."""

import os

DEFAULTS = {
    "disk_gib": 200,
    "system_gib": 16,
    "worlds_gib": 32,
    "backups_gib": 48,
    "logs_gib": 4,
    "content_gib": 24,
    "staging_gib": 40,
    "reserve_gib": 24,
    "backup_count": 12,
    "backup_interval_hours": 2,
}


def storage_plan(environ=None):
    environment = os.environ if environ is None else environ
    values = {}
    try:
        for key, default in DEFAULTS.items():
            name = "OMK_STORAGE_" + key.upper()
            raw = environment.get(name, str(default)).strip()
            if not raw.isascii() or not raw.isdecimal() or len(raw) > 5:
                raise ValueError(name)
            value = int(raw)
            maximum = {"backup_interval_hours": 168, "backup_count": 32000}.get(
                key, 65536
            )
            minimum = 2 if key == "backup_count" else 1
            if not minimum <= value <= maximum:
                raise ValueError(name)
            values[key] = value
    except ValueError as error:
        # Never print the supplied environment value: it could be a pasted secret.
        return {"ok": False, "error": "Некорректная настройка " + str(error)}
    budgets = {
        k: v for k, v in values.items() if k.endswith("_gib") and k != "disk_gib"
    }
    allocated = sum(budgets.values())
    if allocated > values["disk_gib"]:
        return {"ok": False, "error": "Сумма бюджетов превышает размер диска."}
    if values["staging_gib"] < values["worlds_gib"]:
        return {"ok": False, "error": "Staging меньше бюджета исходных миров."}
    return {
        "ok": True,
        "mode": "planning_only",
        "enforced": False,
        "disk_gib": values["disk_gib"],
        "budgets_gib": {k.removesuffix("_gib"): v for k, v in budgets.items()},
        "unallocated_gib": values["disk_gib"] - allocated,
        "ftb_backups_proposal": {
            "backup_timer": values["backup_interval_hours"],
            "backups_to_keep": values["backup_count"],
            "max_total_size": str(values["backups_gib"]) + " GB",
        },
        "limits": [
            "Расчёт ничего не записывает и не удаляет; это не дисковая квота.",
            "Размер диска — заданный бюджет, а не автоматический размер Docker host.",
            "Сжатие не гарантируется; staging должен вместить новую копию с запасом.",
            "FTB 1.1.0.1 удаляет прежние копии до завершения новой; нужен отдельный тест отказа.",
            "Для применения env нужен адаптер конфигурации; готового безопасного backup apply пока нет.",
        ],
    }


def add_storage_commands(sub):
    parser = sub.add_parser("storage", help="Read-only VPS storage budget")
    parser.add_subparsers(dest="action", required=True).add_parser("plan")
