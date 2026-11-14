"""Windowed entry point for the Windows shortcut. No console is required.

Integration assistance: OpenAI Codex. Uses Python's standard library.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import runpy
import sys
import traceback

folder = Path(__file__).resolve().parent
os.chdir(folder)
sys.path.insert(0, str(folder))


def show_error(message):
    ctypes.windll.user32.MessageBoxW(None, message, 'SignalSpeak could not start', 0x10)


def main():
    # Prevent accidentally starting two eye-control processes on the same desktop.
    ctypes.windll.kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
    ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\SignalSpeakDesktopLauncher')
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, 'SignalSpeak is already running. Use F8 to pause or F9 to close it.', 'SignalSpeak', 0x40)
        return
    try:
        with (folder / 'startup.log').open('a', encoding='utf-8') as log:
            sys.stdout = log
            sys.stderr = log
            try:
                runpy.run_path(str(folder / 'main.py'), run_name='__main__')
            except Exception:
                traceback.print_exc(file=log)
                log.flush()
                show_error('SignalSpeak could not start. Details were saved in startup.log in the app folder.\n\nMake sure setup and patient pairing have been completed.')
    finally:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)


if __name__ == '__main__':
    main()
