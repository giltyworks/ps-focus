"""Colours and fonts of the Qt interface, the same as the Tk one's"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache

from PySide6.QtGui import QColor, QFont, QFontMetrics

import app_config
from app_config import COLORS


def color(name: str) -> QColor:
    return QColor(COLORS[name])


def font(size: int, semibold: bool = False) -> QFont:
    result = QFont("Segoe UI")
    result.setPointSize(size)
    result.setWeight(QFont.Weight.DemiBold if semibold else QFont.Weight.Normal)
    return result


class Fonts:
    """The app's fonts, matching the Tk ones in PSFocusApp._configure_window. Made once a QApplication exists"""

    def __init__(self) -> None:
        self.normal = font(10)
        self.bold = font(10, semibold=True)
        self.small = font(9)
        self.account = font(11)
        self.counter = font(10)
        self.two_week = font(app_config.HEADING_FONT_SIZE)
        self.title = font(20, semibold=True)
        self.metric = font(app_config.METRIC_FONT_SIZE, semibold=True)


@lru_cache(maxsize=None)
def _windows_metrics(family: str, point_size: int, weight: int) -> tuple[int, int] | None:
    """Ascent and descent of a font as Windows' own text measuring gives them, which Tk lays its text out by. Qt
    rounds some sizes differently, putting 9 point text a pixel lower than in the Tk app"""
    if os.name != "nt":
        return None

    class TextMetric(ctypes.Structure):
        _fields_ = [
            ("height", wintypes.LONG), ("ascent", wintypes.LONG), ("descent", wintypes.LONG),
            ("rest", ctypes.c_byte * 48),
        ]

    gdi32, user32 = ctypes.WinDLL("gdi32"), ctypes.WinDLL("user32")
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [ctypes.c_wchar_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.GetTextMetricsW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    context = user32.GetDC(None)
    # Points to pixels at the 96 dots per inch Qt lays out by, rounded as Tk does; negative asks for the glyphs' height
    font_handle = gdi32.CreateFontW(-round(point_size * 96 / 72), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 0, 0, family)
    try:
        previous = gdi32.SelectObject(context, font_handle)
        metric = TextMetric()
        found = gdi32.GetTextMetricsW(context, ctypes.byref(metric))
        gdi32.SelectObject(context, previous)
    finally:
        gdi32.DeleteObject(font_handle)
        user32.ReleaseDC(None, context)
    return (metric.ascent, metric.descent) if found else None


def _metrics(font_: QFont) -> tuple[int, int]:
    measured = _windows_metrics(font_.family(), font_.pointSize(), int(font_.weight()))
    if measured is None:
        metrics = QFontMetrics(font_)
        return metrics.ascent(), metrics.descent()
    return measured


def line_height(*fonts: QFont) -> int:
    """Height of a line of text in the tallest of these fonts, as Tk's linespace"""
    return max(sum(_metrics(each)) for each in fonts)


def ascent(font_: QFont) -> int:
    """From the top of a line of text to its baseline, which text is drawn on"""
    return _metrics(font_)[0]
