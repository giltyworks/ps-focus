"""The uninstall window, opened by `PS Focus.exe --uninstall` from Installed apps; laid out as the Tk ui_uninstall.py.
The removal itself is in uninstall.py"""

from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from app_config import resource_path
from uninstall import DONE_MESSAGE_DELETED, DONE_MESSAGE_KEPT, WARNING_MESSAGE, WINDOW_TITLE, APP_NAME, uninstall
from windows_startup import set_title_bar_colors_for_handle

from .header import draw_checkbox
from .module import PaintedButton
from .settings_page import wrap
from .theme import Fonts, color, draw_text, line_height, text_width

# Space around the window's contents, and the width its text wraps at, as the Tk window
PADDING = 14
TEXT_WIDTH = 300
CHECKBOX_SIZE = 18
CHECKBOX_LABEL_GAP = 6
BUTTON_PADX, BUTTON_PADY = 17, 6


class UninstallWindow(QDialog):
    def __init__(self, fonts: Fonts, run: Callable[[bool], list] = uninstall, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.fonts = fonts
        self.run = run
        self.delete_data = False
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.title = f"Remove {APP_NAME} from this PC?"
        self.note = wrap(
            "Your activity history, settings, and backups are kept unless you choose to delete them below", fonts.small, TEXT_WIDTH
        )
        self.cancel_button = PaintedButton("Cancel", self.reject, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text")
        self.uninstall_button = PaintedButton(
            "Uninstall", self.confirm, fonts, BUTTON_PADX, BUTTON_PADY, text_color="accent", fill="accent_dark"
        )
        self.buttons = [self.cancel_button, self.uninstall_button]
        self._lay_out()
        set_title_bar_colors_for_handle(int(self.winId()))

    def _lay_out(self) -> None:
        small = line_height(self.fonts.small)
        width = PADDING + max(TEXT_WIDTH, text_width(self.fonts.bold, self.title)) + PADDING
        self.title_top = PADDING
        top = PADDING + line_height(self.fonts.bold) + 4
        self.note_top = top
        top += len(self.note) * small + 12
        # The option: its name, then the app's checkbox; clicking either ticks it
        row_height = max(small, CHECKBOX_SIZE)
        label_width = text_width(self.fonts.small, "Also delete all user data")
        self.option_area = (PADDING, top, PADDING + label_width + CHECKBOX_LABEL_GAP + CHECKBOX_SIZE, top + row_height)
        self.label_top = top + (row_height - small) // 2
        self.checkbox_center = QPointF(PADDING + label_width + CHECKBOX_LABEL_GAP + CHECKBOX_SIZE / 2, top + row_height / 2)
        top += row_height + 14
        self.uninstall_button.place(width - PADDING - self.uninstall_button.width, top)
        self.cancel_button.place(self.uninstall_button.left - 6 - self.cancel_button.width, top)
        top += self.uninstall_button.height + PADDING
        self.setFixedSize(width, top)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        draw_text(painter, PADDING, self.title_top, self.title, color("text"), self.fonts.bold)
        for index, line in enumerate(self.note):
            draw_text(painter, PADDING, self.note_top + index * line_height(self.fonts.small), line, color("muted"), self.fonts.small)
        draw_text(painter, PADDING, self.label_top, "Also delete all user data", color("text"), self.fonts.small)
        draw_checkbox(painter, self.checkbox_center, self.delete_data)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def _over_option(self, point) -> bool:
        left, top, right, bottom = self.option_area
        return left <= point.x() < right and top <= point.y() < bottom

    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if any([button.press(point) for button in self.buttons]):
            self.update()
        elif self._over_option(point):
            self.delete_data = not self.delete_data
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(event.position().toPoint()) for button in self.buttons]):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over = self._over_option(point) or any(button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def confirm(self) -> bool:
        """Run the uninstall, asking first when user data would be deleted; return whether it ran"""
        if self.delete_data:
            answer = QMessageBox.warning(
                self, WINDOW_TITLE, WARNING_MESSAGE, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.hide()
        failed = self.run(self.delete_data)
        if failed:
            remaining = "\n".join(str(path) for path in failed)
            QMessageBox.warning(None, WINDOW_TITLE, f"{APP_NAME} was removed, but these items could not be deleted:\n\n{remaining}")
        else:
            QMessageBox.information(None, WINDOW_TITLE, DONE_MESSAGE_DELETED if self.delete_data else DONE_MESSAGE_KEPT)
        self.accept()
        return True


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("The PS Focus uninstaller runs only on Windows")
    # Everything removed belongs to the current user, so the uninstaller runs without administrator rights
    application = QApplication.instance() or QApplication(sys.argv)
    window = UninstallWindow(Fonts())
    window.exec()
    del application
