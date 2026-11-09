"""Keep the accepted Windows JAR byte format identical on every build host."""

from zipfile import ZipInfo


def entry(name):
    info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 0
    return info


def ordered(paths):
    return sorted(paths, key=lambda path: path.as_posix().casefold())
