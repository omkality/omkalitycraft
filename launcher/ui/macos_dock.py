"""Keep the launcher out of the Mac Dock while it supervises the game."""

import contextlib
import ctypes
import sys

from PySide6.QtGui import QGuiApplication


def set_launcher_dock_visible(visible: bool) -> None:
    """Switch the running Cocoa app between regular and accessory modes."""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return
    with contextlib.suppress(OSError, AttributeError):
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        pointer = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = pointer
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = pointer
        application = ctypes.CFUNCTYPE(pointer, pointer, pointer)(
            ("objc_msgSend", objc)
        )
        change_policy = ctypes.CFUNCTYPE(
            ctypes.c_bool, pointer, pointer, ctypes.c_long
        )(("objc_msgSend", objc))
        app = application(
            objc.objc_getClass(b"NSApplication"),
            objc.sel_registerName(b"sharedApplication"),
        )
        if app:
            change_policy(
                app, objc.sel_registerName(b"setActivationPolicy:"), 0 if visible else 1
            )
