"""Enforce the signed mod directory in our launcher, not remote client attestation."""

from pathlib import Path, PurePosixPath

from launcher.releases import Release, ReleaseError, sha256_file

ROOTS = {"mods", "coremods"}


def _paths(release: Release):
    expected = {
        file.path: file
        for file in release.files
        if PurePosixPath(file.path).parts[0].casefold() in ROOTS
    }
    directories = set(ROOTS)
    for file in expected.values():
        directories.update(
            str(parent)
            for parent in PurePosixPath(file.path).parents
            if str(parent) != "."
        )
    return expected, directories


def _remove_extra(path: Path, folder: Path, budget: list[int], depth=0) -> int:
    # Never follow a link/junction or traverse beyond this instance's mod folders.
    if not path.parent.resolve().is_relative_to(folder.resolve()) or depth > 32:
        raise ReleaseError("Небезопасный путь в папке модов.")
    budget[0] -= 1
    if budget[0] < 0:
        raise ReleaseError("Слишком много посторонних файлов в папке модов.")
    if path.is_symlink():
        path.unlink()
    elif path.is_junction():
        path.rmdir()
    elif path.is_dir():
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ReleaseError("Папка модов выходит за пределы сборки.")
        for child in path.iterdir():
            _remove_extra(child, folder, budget, depth + 1)
        path.rmdir()
    else:
        path.unlink()
    return 1


def clean_extra_mods(release: Release, folder: Path) -> int:
    """Silently remove extras only inside mods/coremods; leave other player data alone."""
    expected, directories = _paths(release)
    removed, budget = 0, [10000]
    stack = [
        folder / name
        for name in ROOTS
        if (folder / name).exists()
        or (folder / name).is_symlink()
        or (folder / name).is_junction()
    ]
    try:
        while stack:
            path = stack.pop()
            relative = path.relative_to(folder).as_posix()
            # Exact spelling prevents case-variant duplicates loading on Linux/macOS.
            if path.is_symlink() or path.is_junction():
                removed += _remove_extra(path, folder, budget)
            elif path.is_dir():
                if relative not in directories:
                    removed += _remove_extra(path, folder, budget)
                else:
                    stack.extend(path.iterdir())
            elif relative not in expected:
                removed += _remove_extra(path, folder, budget)
        return removed
    except OSError:
        raise ReleaseError(
            "Не удалось подготовить папку модов. Проверьте доступ к файлам сборки."
        ) from None


def verify_mods(release: Release, folder: Path) -> None:
    expected, directories = _paths(release)
    visited = set()
    stack = [
        folder / name
        for name in ROOTS
        if (folder / name).exists()
        or (folder / name).is_symlink()
        or (folder / name).is_junction()
    ]
    try:
        while stack:
            path = stack.pop()
            relative = path.relative_to(folder).as_posix()
            if path.is_symlink() or path.is_junction():
                raise ReleaseError(
                    "Ссылки в папках модов не разрешены. Используйте файлы из сборки."
                )
            if path.is_dir():
                if relative not in directories:
                    raise ReleaseError(
                        "В папке модов найдена посторонняя папка. Переместите её из сборки перед запуском."
                    )
                stack.extend(path.iterdir())
            else:
                artifact = expected.get(relative)
                if artifact is None or relative in visited:
                    raise ReleaseError(
                        "В папке модов найден посторонний файл. Переместите его из сборки перед запуском."
                    )
                if (
                    not path.is_file()
                    or path.stat().st_size != artifact.size
                    or sha256_file(path) != artifact.sha256
                ):
                    raise ReleaseError(
                        "Файл мода изменён или повреждён. Повторите проверку сборки в лаунчере."
                    )
                visited.add(relative)
        if visited != expected.keys():
            raise ReleaseError(
                "Часть модов отсутствует. Повторите проверку сборки в лаунчере."
            )
    except OSError:
        raise ReleaseError(
            "Не удалось проверить папку модов. Проверьте доступ к файлам сборки."
        ) from None
