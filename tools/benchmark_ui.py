"""Compare source UI tick costs in isolated processes; never touches real data or Google."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def memory_mib():
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi')
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return round(counters.working / 1048576, 1)


def measure(toolkit):
    import app_config
    from tracker import ActivityStore
    settings = {**app_config.DEFAULT_SETTINGS, 'show_graph': True, 'show_calendar': True, 'show_stats': True}
    app_config.APP_DATA.mkdir(parents=True, exist_ok=True)
    seed = ActivityStore(app_config.DATABASE_PATH, app_config.BACKUP_DIRECTORIES)
    for offset in range(180):
        seed.record_active_second(datetime.now() - timedelta(days=offset), 'Photoshop')
    seed.close()
    began = time.perf_counter()
    if toolkit == 'qt':
        from PySide6.QtWidgets import QApplication
        from qt.app import PSFocusQt
        patches = [patch('qt.app.load_settings', return_value=settings), patch.object(PSFocusQt, '_start_tray_icon'), patch('qt.app.foreground_application', return_value=None)]
        for item in patches:
            item.start()
        application = QApplication([])
        app = PSFocusQt(application)
        for timer in (app.tick_timer, app.poll_timer, app.backup_timer):
            timer.stop()
        flush = application.processEvents
        show, hide = app.window.showNormal, app.window.hide
        module = 'qt.app'
    else:
        import tkinter as tk
        from main import PSFocusApp
        patches = [patch('main.load_settings', return_value=settings), patch.object(PSFocusApp, '_start_tray_icon'), patch.object(PSFocusApp, '_check_for_updates'), patch.object(PSFocusApp, '_send_pending_feedback'), patch.object(PSFocusApp, '_celebrate_level_up'), patch('main.foreground_application', return_value=None)]
        for item in patches:
            item.start()
        root = tk.Tk()
        app = PSFocusApp(root)
        flush = root.update
        show, hide = root.deiconify, root.withdraw
        module = 'main'
    flush()
    result = {'toolkit': toolkit, 'initialise_ms': round((time.perf_counter() - began) * 1000, 1), 'scenarios': {}}
    for hidden in (False, True):
        (hide if hidden else show)()
        flush()
        for active in (False, True):
            samples = []
            with patch(module + '.foreground_application', return_value='Photoshop' if active else None), patch(module + '.user_is_active', return_value=True):
                for _ in range(30):
                    app.last_tick_time = time.monotonic() - 1
                    start = time.perf_counter()
                    app._track_and_refresh()
                    flush()
                    samples.append((time.perf_counter() - start) * 1000)
            key = ('hidden' if hidden else 'visible') + ('_active' if active else '_idle')
            result['scenarios'][key] = {'median_tick_ms': round(statistics.median(samples), 3), 'working_set_mib': memory_mib()}
    app.store.close()
    if toolkit == 'tk':
        root.destroy()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=('tk', 'qt'))
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(measure(args.worker)))
        return
    results = []
    for toolkit in ('tk', 'qt'):
        with tempfile.TemporaryDirectory(prefix='ui-benchmark-') as folder:
            environment = {**os.environ, 'PSFOCUS_DATA_DIR': folder, 'QT_QPA_PLATFORM': 'offscreen'}
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', toolkit], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45)
            if process.returncode:
                results.append({'toolkit': toolkit, 'unavailable': process.stderr.strip()})
                continue
            results.append(json.loads(process.stdout.strip().splitlines()[-1]))
    output = ROOT / 'build/qt-preview/ui-benchmark.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'conditions': 'Source processes; 180 seeded days; all modules enabled; 30 accelerated ticks per scenario; Qt offscreen, Tk native; no cloud, tray or celebrations. Initialisation includes UI imports; tick measurements include event processing. Not a real-time CPU or packaged startup benchmark.', 'results': results}, indent=2), encoding='utf-8')
    print(output.read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
