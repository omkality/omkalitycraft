"""Render the approved runtime metadata snapshot; never connect to a game server."""

import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path


def cell(value) -> str:
    text = "—" if value is None else str(value)
    return html.escape(re.sub("§.", "", text)).replace("|", "\\|").replace("\n", " ")


def render(data: dict) -> str:
    commands = data["commands"]
    lines = [
        "# Полный реестр серверных команд DJ2",
        "",
        "Снимок зарегистрированных команд Forge 1.12.2 / DJ2 RU 2.21.3 от 2026-10-30.",
        f"Всего **{len(commands)} записей**, включая обнаруженные подкоманды Forge CommandTree.",
        "Это факт регистрации, а не отметка успешного выполнения каждой команды.",
        "",
        "[Назад к практическому справочнику](README.md). [Исходные метаданные](registry.json).",
        "",
        "Уровень 0 обычно означает доступ обычному игроку; 1–4 — уровни OP Minecraft.",
        "Отдельные реализации дополнительно проверяют владельца/измерение/предмет/право;",
        "FTB-ranks может переопределить доступ по точному node. `—` означает, что уровень",
        "не получен стандартным методом. Не выдавайте права только по этой колонке.",
        "У корневой команды-дерева может не быть собственного node: права заданы у листьев.",
        "",
        "Синтаксис взят из getUsage; ключи локализации разрешены из установленных en_us.lang.",
        "Оставшийся ключ означает отсутствие строки в доступных ресурсах. Алиасы корня",
        "включают фактические ключи реестра. Встроенные в execute подкоманды, не оформленные",
        "как Forge CommandTree, отражены синтаксисом корня и не считаются отдельными записями.",
        "Клиентские команды/клавиши и пункты GUI не принадлежат серверному реестру.",
    ]
    groups = defaultdict(list)
    for command in commands:
        groups[command["owner_hint"]].append(command)
    for owner, rows in sorted(groups.items()):
        lines.extend(
            [
                "",
                f"## {cell(owner)}",
                "",
                "| Команда | Алиасы/реестр | Уровень | Permission node | Синтаксис |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            aliases = row.get("registry_keys") or row.get("aliases") or []
            aliases = [value for value in aliases if "/" + value != row["path"]]
            values = [
                row["path"],
                ", ".join(aliases) or None,
                row["base_level"],
                row["permission_node"],
                row["usage_resolved"],
            ]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "## Все параметры рангов",
            "",
            "Пустой override означает использование наследования/заводского значения.",
            "",
            "| Node | Заводской игрок | Заводской OP | Наш тестовый player override |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in data["rank_configs"]:
        values = [
            row["node"],
            row["default_player"],
            row["default_op"],
            row["lab_player_override"] or None,
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "## Дополнительные зарегистрированные права",
            "",
            "ALL — доступно обычному игроку по умолчанию, OP — оператору, NONE — явно не выдаётся.",
            "Эта таблица дополняет command nodes выше и не заменяет проверки внутри команд.",
            "",
            "| Node | Заводской доступ | Описание API |",
            "| --- | --- | --- |",
        ]
    )
    for row in data["permissions"]:
        lines.append(
            "| "
            + " | ".join(cell(row[key]) for key in ["node", "default", "description"])
            + " |"
        )
    lines.extend(
        [
            "",
            "## Повторяющиеся права блоков и предметов",
            "",
            "Индивидуальные записи этой группы сведены в семейства. Точные исключения",
            "содержатся в registry.json; полный сырой снимок создаётся в локальном стенде.",
            "",
            "| Шаблон | Записей | Заводские уровни |",
            "| --- | --- | --- |",
        ]
    )
    for row in data["permission_families"]:
        lines.append(
            "| "
            + " | ".join(
                cell(value) for value in [row["prefix"], row["count"], row["defaults"]]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(
        render(json.loads(args.source.read_text(encoding="utf-8"))), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
