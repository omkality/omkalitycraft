"""Owner CLI filesystem boundary. No passwords, permission changes or network calls."""

import ctypes
import os
import stat
from functools import lru_cache
from pathlib import Path

SYSTEM = "S-1-5-18"
ADMINISTRATORS = "S-1-5-32-544"
OWNER_RIGHTS = "S-1-3-4"
CREATOR_OWNER = "S-1-3-0"
ERROR = "Owner-only operator access is required"


def _validate_windows_acl(owner, current, entries):
    privileged = {SYSTEM, ADMINISTRATORS}
    if owner not in {current, *privileged} or entries is None:
        raise PermissionError(ERROR)
    for kind, flags, mask, sid in entries:
        if kind == 1:  # A deny cannot grant access.
            continue
        if kind != 0:  # Unknown/callback/object grants require an explicit review.
            raise PermissionError(ERROR)
        if (
            mask
            and sid not in {current, OWNER_RIGHTS, *privileged}
            and (sid != CREATOR_OWNER or not flags & 0x08)
        ):
            raise PermissionError(ERROR)


@lru_cache(maxsize=1)
def _windows_api():
    pointer = ctypes.c_void_p
    dword = ctypes.c_uint32
    pp = ctypes.POINTER(pointer)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "GetNamedSecurityInfoW": (
            dword,
            [ctypes.c_wchar_p, dword, dword, pp, pp, pp, pp, pp],
        ),
        "GetAclInformation": (ctypes.c_int, [pointer, pointer, dword, dword]),
        "GetAce": (ctypes.c_int, [pointer, dword, pp]),
        "IsValidSid": (ctypes.c_int, [pointer]),
        "ConvertSidToStringSidW": (ctypes.c_int, [pointer, pp]),
        "OpenProcessToken": (ctypes.c_int, [pointer, dword, pp]),
        "GetTokenInformation": (
            ctypes.c_int,
            [pointer, dword, pointer, dword, ctypes.POINTER(dword)],
        ),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(adv, name)
        function.restype, function.argtypes = result, arguments
    kernel.GetCurrentProcess.restype = pointer
    kernel.GetCurrentProcess.argtypes = []
    kernel.CloseHandle.argtypes = [pointer]
    kernel.CloseHandle.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    return adv, kernel


def _sid_text(adv, kernel, sid):
    output = ctypes.c_void_p()
    if (
        not sid
        or not adv.IsValidSid(sid)
        or not adv.ConvertSidToStringSidW(sid, ctypes.byref(output))
    ):
        raise PermissionError(ERROR)
    try:
        return ctypes.wstring_at(output)
    finally:
        kernel.LocalFree(output)


def _process_sid(adv, kernel):
    token = ctypes.c_void_p()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise PermissionError(ERROR)
    try:
        size = ctypes.c_uint32()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not ctypes.sizeof(ctypes.c_void_p) <= size.value <= 65536:
            raise PermissionError(ERROR)
        data = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, data, size, ctypes.byref(size)):
            raise PermissionError(ERROR)
        return _sid_text(adv, kernel, ctypes.c_void_p.from_buffer(data).value)
    finally:
        kernel.CloseHandle(token)


def _windows_acl(path):
    adv, kernel = _windows_api()
    owner, dacl, descriptor = (ctypes.c_void_p() for _ in range(3))
    status = adv.GetNamedSecurityInfoW(
        str(path),
        1,
        5,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    try:
        if status or not dacl:
            raise PermissionError(ERROR)
        size_info = (ctypes.c_uint32 * 3)()
        if (
            not adv.GetAclInformation(dacl, size_info, ctypes.sizeof(size_info), 2)
            or size_info[0] > 128
        ):
            raise PermissionError(ERROR)
        entries = []
        for index in range(size_info[0]):
            ace = ctypes.c_void_p()
            if not adv.GetAce(dacl, index, ctypes.byref(ace)):
                raise PermissionError(ERROR)
            header = (ctypes.c_ubyte * 4).from_address(ace.value)
            kind, flags = header[0], header[1]
            if kind not in {0, 1} or int.from_bytes(bytes(header[2:4]), "little") < 16:
                raise PermissionError(ERROR)
            mask = ctypes.c_uint32.from_address(ace.value + 4).value
            entries.append((kind, flags, mask, _sid_text(adv, kernel, ace.value + 8)))
        _validate_windows_acl(
            _sid_text(adv, kernel, owner), _process_sid(adv, kernel), entries
        )
    finally:
        if descriptor:
            kernel.LocalFree(descriptor)


def require_private(path: Path, *, directory=False, secret=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise PermissionError(ERROR)
    if os.name == "nt":
        _windows_acl(path)
    elif info.st_uid != os.geteuid():
        raise PermissionError(ERROR)
    elif (directory or secret) and info.st_mode & 0o077:
        raise PermissionError(
            "The private operator directory requires mode 700"
            if directory
            else "Operator credentials require mode 600"
        )
