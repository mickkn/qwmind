"""
:File:        src/qwbot/windows.py

:Details:     Focus-checked Windows keyboard and mouse control for ezQuake.

:Date:        30-10-2026
:Author:      Mick K.
"""

import ctypes
import math
import os
import time
from ctypes import wintypes
from pathlib import Path


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
    ]


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class InputData(ctypes.Union):
    _fields_ = [
        ("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", InputData)]


class Win32Input:
    """Keep Win32 calls isolated so input behavior can be tested without a game."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Windows input requires Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.SendInput.argtypes = [
            wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int,
        ]
        self.user32.SendInput.restype = wintypes.UINT
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def foreground(self):
        window = self.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        return window, pid.value

    def executable(self, pid):
        handle = self.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not self.kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            return Path(buffer.value).name.lower()
        finally:
            self.kernel32.CloseHandle(handle)

    def emergency_stop(self):
        return bool(self.user32.GetAsyncKeyState(0x7B) & 0x8000)

    def _send(self, event):
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
            raise OSError(
                "SendInput failed; run the bot and ezQuake at the same privilege level"
            )

    def key(self, scan_code, down):
        event = Input(type=1)
        event.ki = KeyboardInput(wScan=scan_code, dwFlags=0x0008 | (0 if down else 0x0002))
        self._send(event)

    def mouse(self, counts):
        event = Input(type=0)
        event.mi = MouseInput(dx=counts, dwFlags=0x0001)
        self._send(event)


class WindowsTransport:
    """Translate movement commands into input only while the target stays focused."""

    SCAN_CODES = {"forward": 0x11, "moveleft": 0x1E, "moveright": 0x20, "jump": 0x39}

    def __init__(self, timeout=8, pid=None, mouse_counts_per_degree=15.15):
        self.timeout = timeout
        self.pid = pid
        self.mouse_counts_per_degree = mouse_counts_per_degree
        self.api = Win32Input()
        self.window = None
        self.held = set()

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            if self.api.emergency_stop():
                raise RuntimeError("F12 emergency stop")
            window, pid = self.api.foreground()
            if window and pid:
                matches = pid == self.pid if self.pid is not None else (
                    self.api.executable(pid).startswith("ezquake")
                )
                if matches:
                    self.window, self.pid = window, pid
                    return self
            if time.monotonic() >= deadline:
                raise RuntimeError("Focus the ezQuake game window before the timeout expires")
            time.sleep(0.05)

    def check(self):
        if self.api.emergency_stop():
            raise RuntimeError("F12 emergency stop")
        if self.window is None or self.api.foreground() != (self.window, self.pid):
            raise RuntimeError("ezQuake lost focus; input stopped")

    def send(self, command):
        if command.startswith("-") and command[1:] in self.SCAN_CODES:
            name = command[1:]
            if name in self.held:
                # Releases must also work after focus loss or an emergency stop.
                self.api.key(self.SCAN_CODES[name], False)
                self.held.remove(name)
            return
        self.check()
        if command.startswith("+") and command[1:] in self.SCAN_CODES:
            name = command[1:]
            if name not in self.held:
                self.api.key(self.SCAN_CODES[name], True)
                self.held.add(name)
        elif command.startswith("rotate "):
            angle = float(command.split(" ", 1)[1])
            if not math.isfinite(angle) or abs(angle) > 360:
                raise ValueError("Invalid rotation angle")
            self.api.mouse(round(angle * self.mouse_counts_per_degree))
        else:
            raise ValueError(f"Unsupported Windows input command: {command}")

    def __exit__(self, *_):
        errors = []
        for name in tuple(self.held):
            try:
                self.send("-" + name)
            except OSError as exc:
                errors.append(str(exc))
        self.window = None
        if errors:
            raise OSError("Could not release input keys: " + "; ".join(errors))
