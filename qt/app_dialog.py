"""What PS Focus's small windows share, the day overview, a friend's details, Feedback and Uninstall: a Windows title
bar with the logo, coloured dark as they show, and opening centred over PS Focus's window"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QWidget

from app_config import resource_path
from windows_startup import set_title_bar_colors_for_handle


class AppDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, modal: bool = True) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        if modal:
            # Taking the clicks from PS Focus while open, and gone once closed
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Coloured as it shows, not before: asking for the window's handle before it is shown made Windows stop
        # passing PS Focus's small redraws to the screen, so hover and scrolling seemed frozen until a full redraw
        set_title_bar_colors_for_handle(int(self.winId()))

    def show_centred_on(self, window: QWidget) -> None:
        """Open over the middle of the window, kept on its screen, which may lie left of or above the main screen"""
        self.adjustSize()
        frame = window.frameGeometry()
        size = self.frameGeometry().size()
        left = frame.x() + (frame.width() - size.width()) // 2
        top = frame.y() + (frame.height() - size.height()) // 2
        screen = (window.screen() or self.screen()).availableGeometry()
        left = max(screen.left(), min(left, screen.right() + 1 - size.width()))
        top = max(screen.top(), min(top, screen.bottom() + 1 - size.height()))
        self.move(QPoint(left, top))
        self.show()
        self.activateWindow()
