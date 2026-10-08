"""The feedback form, opened from the level badge until the level is revealed, and from Settings' Got feedback?"""

from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QFocusEvent, QIcon, QKeyEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QWidget

from app_config import FEEDBACK_PLACEHOLDER, FEEDBACK_PLACEHOLDER_PROMPT, resource_path
from feedback import FeedbackOutbox
from windows_startup import set_title_bar_colors_for_handle

from .module import PaintedButton
from .theme import Fonts, color, draw_text, font, line_height, text_width

# Laid out as the Tk dialog was packed, see ui_feedback._open_feedback_dialog: the space at the dialog's sides, the
# inset a Tk label kept its text at, the message box's size in characters and lines and its padding, and the buttons'
LABEL_INSET = 3
SIDE = 16
MESSAGE_CHARACTERS = 44
MESSAGE_LINES = 7
MESSAGE_PADX, MESSAGE_PADY = 8, 6
BUTTON_PADX, BUTTON_PADY = 17, 6
STAR_COUNT = 5
EMPTY_STAR, FULL_STAR = "\U00002606", "\U00002605"
# How long the thank-you stays before the form closes
CLOSE_DELAY_MS = 1200


class MessageBox(QPlainTextEdit):
    """The message, with the placeholder shown while nothing is typed: its first line in the text colour, the rest
    muted, as the Tk box showed them"""

    def __init__(self, fonts: Fonts) -> None:
        super().__init__()
        self.setFont(fonts.small)
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(MESSAGE_PADX, MESSAGE_PADY, MESSAGE_PADX, MESSAGE_PADY)
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {color('panel').name()}; color: {color('text').name()};"
            f" border: 1px solid {color('border').name()}; selection-background-color: {color('accent_dark').name()}; }}"
        )
        width = text_width(fonts.small, "0" * MESSAGE_CHARACTERS) + 2 * MESSAGE_PADX + 2
        self.setFixedSize(width, MESSAGE_LINES * line_height(fonts.small) + 2 * MESSAGE_PADY + 2)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.document().isEmpty():
            painter = QPainter(self.viewport())
            painter.setFont(self.font())
            area = self.viewport().rect()
            prompt = FEEDBACK_PLACEHOLDER_PROMPT.rstrip("\n")
            painter.setPen(color("text"))
            painter.drawText(area, Qt.TextFlag.TextSingleLine, prompt)
            painter.setPen(color("muted"))
            rest = area.adjusted(0, line_height(self.font()), 0, 0)
            painter.drawText(rest, Qt.TextFlag.TextWordWrap, FEEDBACK_PLACEHOLDER)
            painter.end()


class StarRow(QWidget):
    """Five stars to rate by; clicking the chosen star again clears the rating. With the keyboard, the arrow keys move
    between them and Enter or Space chooses one"""

    def __init__(self, on_changed: Callable[[], None]) -> None:
        super().__init__()
        self.on_changed = on_changed
        self.font = font(18, family="Segoe UI Symbol")
        self.rating = 0
        self.focused_star = 1
        # The focused star is outlined only once the keyboard has been used to reach it
        self.keyboard_focus = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.star_width = text_width(self.font, EMPTY_STAR) + 2 * LABEL_INSET
        # Each star was a label packed a pixel from its neighbours
        self.setFixedSize(STAR_COUNT * (self.star_width + 2), line_height(self.font) + 2 * LABEL_INSET)

    def _star_left(self, value: int) -> int:
        return 1 + (value - 1) * (self.star_width + 2)

    def _star_at(self, point: QPoint) -> int | None:
        for value in range(1, STAR_COUNT + 1):
            if self._star_left(value) <= point.x() < self._star_left(value) + self.star_width:
                return value
        return None

    def choose(self, value: int) -> None:
        self.rating = 0 if self.rating == value else value
        self.update()
        self.on_changed()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        for value in range(1, STAR_COUNT + 1):
            filled = value <= self.rating
            left = self._star_left(value)
            draw_text(painter, left + LABEL_INSET, LABEL_INSET, FULL_STAR if filled else EMPTY_STAR, color("gold" if filled else "muted"), self.font)
            if self.hasFocus() and self.keyboard_focus and value == self.focused_star:
                painter.setPen(color("muted"))
                painter.drawRect(QRect(left, 0, self.star_width - 1, self.height() - 1))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        value = self._star_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and value is not None:
            self.focused_star = value
            self.keyboard_focus = False
            self.choose(value)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        over = self._star_at(event.position().toPoint()) is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        self.keyboard_focus = True
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = 1 if key == Qt.Key.Key_Right else -1
            self.focused_star = (self.focused_star - 1 + step) % STAR_COUNT + 1
            self.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.choose(self.focused_star)
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()


class FeedbackDialog(QDialog):
    """The app passes in the outbox to keep the feedback in, how long until more may be sent (None when it may be sent
    now), and what to do once it has been kept: counting it, sending it and revealing the level"""

    def __init__(
        self,
        parent: QWidget,
        fonts: Fonts,
        outbox: FeedbackOutbox,
        cooldown_remaining: Callable[[], object],
        on_submitted: Callable[[], None],
        reveal_prompt: bool = False,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.fonts = fonts
        self.outbox = outbox
        self.cooldown_remaining = cooldown_remaining
        self.on_submitted = on_submitted
        self.setWindowTitle("Feedback")
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.title = "Rate us to reveal your level" if reveal_prompt else "Rate your experience"
        self.status = ("", "muted")
        self.stars = StarRow(self._clear_status)
        self.stars.setParent(self)
        self.message = MessageBox(fonts)
        self.message.setParent(self)
        self.message.textChanged.connect(self._message_changed)
        self.not_now_button = PaintedButton("Not now", self.close, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text")
        self.submit_button = PaintedButton(
            "Submit", self.submit, fonts, BUTTON_PADX, BUTTON_PADY, text_color="accent", fill="accent_dark"
        )
        self.buttons = [self.not_now_button, self.submit_button]
        self._lay_out()
        if self._show_cooldown():
            self.submit_button.enabled = False
        set_title_bar_colors_for_handle(int(self.winId()))

    def _lay_out(self) -> None:
        small = line_height(self.fonts.small)
        top = 14
        self.title_top = top + LABEL_INSET
        top += line_height(self.fonts.bold) + 2 * LABEL_INSET + 2
        self.stars.move(14, top)
        top += self.stars.height() + 6
        self.message.move(SIDE, top)
        top += self.message.height() + 8
        width = SIDE + self.message.width() + SIDE
        self.status_top = top + LABEL_INSET
        top += small + 2 * LABEL_INSET + 6
        right = width - SIDE
        self.submit_button.place(right - self.submit_button.width, top)
        self.not_now_button.place(self.submit_button.left - 6 - self.not_now_button.width, top)
        top += self.submit_button.height + 14
        self.setFixedSize(width, top)

    def _set_status(self, text: str, color_name: str) -> None:
        self.status = (text, color_name)
        self.update()

    def _clear_status(self) -> None:
        self._set_status("", "muted")

    def _message_changed(self) -> None:
        if self.message.toPlainText():
            self._clear_status()

    def _show_cooldown(self) -> bool:
        remaining = self.cooldown_remaining()
        if remaining is None:
            return False
        minutes = math.ceil(remaining.total_seconds() / 60)
        self._set_status(f"You can send more feedback in {minutes} minute{'' if minutes == 1 else 's'}", "orange")
        return True

    def submit(self) -> None:
        if not self.submit_button.enabled or self._show_cooldown():
            return
        message = self.message.toPlainText().strip()
        if not self.stars.rating and not message:
            self._set_status("Add a star rating or a message first", "red")
            return
        try:
            self.outbox.add(self.stars.rating or None, message)
        except OSError as error:
            self._set_status(f"Could not save feedback: {error}", "red")
            return
        self.on_submitted()
        self.submit_button.enabled = False
        self._set_status("Thank you for your feedback", "active_green")
        QTimer.singleShot(CLOSE_DELAY_MS, self.close)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        draw_text(painter, SIDE + LABEL_INSET, self.title_top, self.title, color("text"), self.fonts.bold)
        text, color_name = self.status
        if text:
            draw_text(painter, SIDE + LABEL_INSET, self.status_top, text, color(color_name), self.fonts.small)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and any([button.press(event.position().toPoint()) for button in self.buttons]):
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(event.position().toPoint()) for button in self.buttons]):
            self.update()

    def leaveEvent(self, _event) -> None:
        if PaintedButton.update_hover(self.buttons, None):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        if PaintedButton.update_hover(self.buttons, point):
            self.update()
        over = any(button.enabled and button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def show_centred_on(self, window: QWidget) -> None:
        frame = window.frameGeometry()
        x = window.x() + (frame.width() - self.frameGeometry().width()) // 2
        y = window.y() + (frame.height() - self.frameGeometry().height()) // 2
        self.move(max(0, x), max(0, y))
        self.show()
        self.activateWindow()
        self.message.setFocus()
