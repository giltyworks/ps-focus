"""Colours and fonts of the Qt interface, the same as the Tk one's"""

from __future__ import annotations

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


def line_height(*fonts: QFont) -> int:
    """Height of a line of text in the tallest of these fonts, as Tk's linespace"""
    return max(QFontMetrics(each).height() for each in fonts)


def ascent(font_: QFont) -> int:
    return QFontMetrics(font_).ascent()
