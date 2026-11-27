"""KinoSuite Hub — Unified Creative Suite entry point.

Launch directly for the KinoSuite Hub window, or pass any creative file path
(e.g. `KinoSuite.exe track.wav` or `photo.png`) to route and open it in the
matching KinoSuite app automatically.
"""
from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import QDir, QLockFile, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from kinosuite.icons import make_suite_pixmap
from kinosuite.mainwindow import KinoSuiteHubWindow
from kinosuite.registry import SuiteConfig, discover_suite_apps, launch_kino_app, portal_targets, route_file_to_app
from kinosuite.theme import KINOSUITE_HUB_DARK

APP_USER_MODEL_ID = "KinoSuite.Hub.Desktop.1"
SINGLE_INSTANCE_MUTEX = "Local\\KinoSuite_Hub_SingleInstance_Mutex_v1"
SINGLE_INSTANCE_WAKE_EVENT = "Local\\KinoSuite_Hub_WakeEvent_v1"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceGuard:
    """Guarantees only one KinoSuite Hub instance runs at a time and focuses it on re-launch."""

    def __init__(
        self,
        mutex_name: str = SINGLE_INSTANCE_MUTEX,
        event_name: str = SINGLE_INSTANCE_WAKE_EVENT,
    ) -> None:
        self.mutex_name = mutex_name
        self.event_name = event_name
        self._mutex = None
        self._wake_event = None
        self._lock_file: QLockFile | None = None
        self._k32 = None
        self.is_primary = False

    def acquire(self) -> bool:
        if sys.platform == "win32":
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CreateEventW.restype = ctypes.c_void_p
            k32.SetEvent.argtypes = [ctypes.c_void_p]
            k32.SetEvent.restype = ctypes.c_bool
            k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.WaitForSingleObject.restype = ctypes.c_uint32
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            k32.CloseHandle.restype = ctypes.c_bool
            self._k32 = k32

            ctypes.set_last_error(0)
            h_mutex = k32.CreateMutexW(None, False, self.mutex_name)
            err = ctypes.get_last_error()
            h_event = k32.CreateEventW(None, False, False, self.event_name)
            if not h_mutex:
                if h_event:
                    k32.CloseHandle(h_event)
                return True  # Fail-open only if OS call unexpectedly fails

            if err == ERROR_ALREADY_EXISTS:
                # Signal the running primary instance to restore & come to foreground
                try:
                    ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
                except Exception:
                    pass
                if h_event:
                    k32.SetEvent(h_event)
                    k32.CloseHandle(h_event)
                k32.CloseHandle(h_mutex)
                self.is_primary = False
                return False

            self._mutex = h_mutex
            self._wake_event = h_event
            self.is_primary = True
            return True

        lock_path = os.path.join(QDir.tempPath(), f"{self.mutex_name.replace(chr(92), '_')}.lock")
        lf = QLockFile(lock_path)
        lf.setStaleLockTime(0)
        if not lf.tryLock(0):
            self.is_primary = False
            return False
        self._lock_file = lf
        self.is_primary = True
        return True

    def poll_wake_requested(self) -> bool:
        if sys.platform == "win32" and self._k32 and self._wake_event:
            return self._k32.WaitForSingleObject(self._wake_event, 0) == 0
        return False

    def release(self) -> None:
        if sys.platform == "win32" and self._k32:
            if self._wake_event:
                self._k32.CloseHandle(self._wake_event)
                self._wake_event = None
            if self._mutex:
                self._k32.CloseHandle(self._mutex)
                self._mutex = None
        if self._lock_file is not None:
            self._lock_file.unlock()
            self._lock_file = None
        self.is_primary = False


def _bring_window_to_front(win: KinoSuiteHubWindow) -> None:
    was_minimized = win.isMinimized()
    if was_minimized:
        win.showNormal()
    else:
        win.show()
    win.setWindowState((win.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
    win.raise_()
    win.activateWindow()
    if sys.platform == "win32":
        try:
            u32 = ctypes.windll.user32
            hwnd = ctypes.c_void_p(int(win.winId()))
            u32.ShowWindow(hwnd, 9 if was_minimized else 5)  # SW_RESTORE if minimized, else SW_SHOW
            u32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _set_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            shell32 = ctypes.windll.shell32
            shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def _load_suite_icon(suite_root: str) -> QIcon:
    ico_path = os.path.join(suite_root, "KinoSuite.ico")
    if os.path.isfile(ico_path):
        ic = QIcon(ico_path)
        if not ic.isNull():
            return ic
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(make_suite_pixmap(sz))
    return ic


def main() -> int:
    suite_root = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    file_args = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isfile(a)]

    if "--portal-open" in sys.argv:
        app = QApplication(sys.argv)
        app.setWindowIcon(_load_suite_icon(suite_root))
        app.setStyleSheet(KINOSUITE_HUB_DARK)
        config = SuiteConfig(suite_root)
        apps = discover_suite_apps(suite_root,config)
        for path in file_args:
            targets = portal_targets(path,apps)
            if not targets:
                QMessageBox.information(None,"KinoPortal",f"{os.path.basename(path)} was saved in Portal Inbox. No installed KinoSuite app can open it.")
                continue
            target = targets[0]
            if len(targets) > 1:
                names = [target.name for target in targets]
                name, accepted = QInputDialog.getItem(None,"Open from KinoPortal",os.path.basename(path),names,0,False)
                if not accepted:
                    continue
                target = targets[names.index(name)]
            try:
                launch_kino_app(target,[path])
                config.add_recent(path,target.app_id)
            except OSError as error:
                QMessageBox.warning(None,"KinoPortal",str(error))
        return 0

    # Fast universal file-router CLI mode when invoked with file arguments
    if file_args and "--hub" not in sys.argv:
        cfg = SuiteConfig(suite_root)
        apps = discover_suite_apps(suite_root, cfg)
        routed_any = False
        for fp in file_args:
            target = route_file_to_app(fp, apps)
            if target:
                launch_kino_app(target, [fp])
                cfg.add_recent(fp, target.app_id)
                routed_any = True
        if routed_any:
            return 0

    # Enforce single KinoSuite Hub instance; if already open, wake & focus it and exit cleanly
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquire():
        return 0

    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("KinoSuite")
    app.setOrganizationName("KinoSuite")
    app.setStyleSheet(KINOSUITE_HUB_DARK)

    icon = _load_suite_icon(suite_root)
    app.setWindowIcon(icon)

    win = KinoSuiteHubWindow(suite_root=suite_root)
    win.setWindowIcon(icon)
    win.show()
    win.apply_native_taskbar_icon()

    wake_timer = QTimer(win)
    wake_timer.setInterval(150)
    wake_timer.timeout.connect(lambda: _bring_window_to_front(win) if instance_guard.poll_wake_requested() else None)
    wake_timer.start()

    try:
        return app.exec()
    finally:
        wake_timer.stop()
        instance_guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
