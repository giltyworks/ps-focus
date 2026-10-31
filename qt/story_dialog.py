"""The session story window, opened from a day's overview: a preview of the story card for that day's session, a photo
to put behind it, every piece of its text open to change, and buttons to copy the 1080x1920 image or save it as a PNG
to post from a phone. The card itself is painted by story_card"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QImage, QImageReader, QMouseEvent, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QWidget

from session_story import StoryText

from .app_dialog import AppDialog
from .header import draw_checkbox
from .module import PaintedButton, draw_rounded_box
from .settings_page import wrap
from .story_card import STORY_SIZE, render_story
from .theme import Fonts, color, draw_text, line_height

PADDING = 14
# The preview: the story at a quarter of its size, so 270 by 480
PREVIEW_SCALE = 0.25
PREVIEW_RADIUS = 6
COLUMN_WIDTH = 250
COLUMN_GAP = 18
FIELD_HEIGHT = 26
FIELD_PADX = 6
LABEL_GAP = 3
ROW_GAP = 9
BUTTON_PADX, BUTTON_PADY = 12, 6
CHECKBOX_SIZE = 18
# Typing waits this long before the preview is painted again, so each key press stays quick
PREVIEW_DELAY_MS = 120
# The text a person can change, with the name each field shows above it
FIELDS = (("title", "Title"), ("date", "Date"), ("programs", "Programs"), ("focus_time", "Focus time"), ("started", "Started"))
PHOTO_FILTER = "Images (*.jpg *.jpeg *.png *.webp *.bmp)"


def read_photo(path: str) -> QImage:
    """The photo turned upright as the phone or camera took it, or a null image if it cannot be read"""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    return reader.read()


def default_file_name(session_day: date) -> str:
    return f"PS Focus session {session_day.isoformat()}.png"


class StoryDialog(AppDialog):
    def __init__(self, parent: QWidget | None, fonts: Fonts, session_day: date, text: StoryText) -> None:
        super().__init__(parent, "Share session", modal=True)
        self.fonts = fonts
        self.session_day = session_day
        self.text = text
        self.photo: QImage | None = None
        self.photo_name = "No photo yet"
        self.framed = True
        self.option_hovered = False
        self.status = ("", "muted")
        self.story = render_story(None, text)
        self.setMouseTracking(True)
        self.render_timer = QTimer(self, singleShot=True, interval=PREVIEW_DELAY_MS)
        self.render_timer.timeout.connect(self.render)
        self.photo_button = PaintedButton("Choose photo…", self.choose_photo, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text", solid=True)
        self.copy_button = PaintedButton("Copy image", self.copy_image, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text")
        self.save_button = PaintedButton("Save image…", self.save_image, fonts, BUTTON_PADX, BUTTON_PADY, text_color="accent", fill="accent_dark", solid=True)
        self.buttons = [self.photo_button, self.copy_button, self.save_button]
        self.fields: dict[str, QLineEdit] = {}
        style = (
            f"QLineEdit {{ background: {color('panel').name()}; color: {color('text').name()};"
            f" border: 1px solid {color('border').name()}; padding: 0 {FIELD_PADX - 2}px;"
            f" selection-background-color: {color('accent_dark').name()}; }}"
            f" QLineEdit:focus {{ border-color: {color('calendar_blue').name()}; }}"
        )
        for name, _label in FIELDS:
            field = QLineEdit(getattr(text, name), self)
            field.setFont(fonts.small)
            field.setStyleSheet(style)
            field.textEdited.connect(self._edited)
            self.fields[name] = field
        self._lay_out()

    def _lay_out(self) -> None:
        small = line_height(self.fonts.small)
        preview_width = round(STORY_SIZE.width() * PREVIEW_SCALE)
        preview_height = round(STORY_SIZE.height() * PREVIEW_SCALE)
        self.preview = QRectF(PADDING, PADDING, preview_width, preview_height)
        left = PADDING + preview_width + COLUMN_GAP
        self.column_left = left
        top = PADDING
        self.photo_button.place(left, top)
        self.photo_name_top = top + (self.photo_button.height - small) // 2
        top += self.photo_button.height + ROW_GAP + 4
        self.label_tops = {}
        for name, _label in FIELDS:
            self.label_tops[name] = top
            top += small + LABEL_GAP
            self.fields[name].setGeometry(left, top, COLUMN_WIDTH, FIELD_HEIGHT)
            top += FIELD_HEIGHT + ROW_GAP
        top += 2
        row_height = max(small, CHECKBOX_SIZE)
        self.option_area = (left, top, left + COLUMN_WIDTH, top + row_height)
        self.checkbox_center = QPointF(left + CHECKBOX_SIZE / 2 - 2, top + row_height / 2)
        self.option_label = (left + CHECKBOX_SIZE + 4, top + (row_height - small) // 2)
        top += row_height + ROW_GAP + 4
        self.records_top = top
        bottom = PADDING + preview_height
        self.save_button.place(left + COLUMN_WIDTH - self.save_button.width, bottom - self.save_button.height)
        self.copy_button.place(self.save_button.left - 6 - self.copy_button.width, self.save_button.top)
        self.status_top = self.save_button.top - ROW_GAP - small
        self.setFixedSize(left + COLUMN_WIDTH + PADDING, bottom + PADDING)

    def _edited(self) -> None:
        self.text = self.text.edited(**{name: field.text() for name, field in self.fields.items()})
        self.render_timer.start()

    def render(self) -> None:
        self.story = render_story(self.photo, self.text, self.framed)
        self.update()

    def choose_photo(self, path: str | None = None) -> bool:
        """Put a photo behind the card, asking which unless given its path; return whether one was taken"""
        if path is None:
            folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            path, _filter = QFileDialog.getOpenFileName(self, "Choose a photo", folder, PHOTO_FILTER)
            if not path:
                return False
        photo = read_photo(path)
        if photo.isNull():
            self.status = ("That photo couldn't be opened. Try a JPEG or PNG", "red")
            self.update()
            return False
        self.photo = photo
        self.photo_name = Path(path).name
        self.status = ("", "muted")
        self.render()
        return True

    def copy_image(self) -> None:
        self.render()
        QApplication.clipboard().setImage(self.story)
        self.status = ("Copied. Paste it into a message or another app", "accent")
        self.update()

    def save_image(self, path: str | None = None) -> bool:
        """Save the story as a PNG, asking where unless given a path; return whether it was saved"""
        if path is None:
            folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            path, _filter = QFileDialog.getSaveFileName(
                self, "Save story", str(Path(folder) / default_file_name(self.session_day)), "PNG image (*.png)"
            )
            if not path:
                return False
        if not path.lower().endswith(".png"):
            path += ".png"
        self.render()
        if self.story.save(path, "PNG"):
            self.status = (f"Saved {Path(path).name}", "accent")
            saved = True
        else:
            self.status = ("Couldn't save there. Try another folder", "red")
            saved = False
        self.update()
        return saved

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), color("background"))
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        draw_rounded_box(painter, self.preview.adjusted(-1, -1, 1, 1), PREVIEW_RADIUS + 1, color("panel"), color("border"))
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(self.preview, PREVIEW_RADIUS, PREVIEW_RADIUS)
        painter.setClipPath(clip)
        painter.drawImage(self.preview, self.story)
        painter.restore()
        left = self.column_left
        name = self.fonts.small
        photo_name_left = self.photo_button.right + 8
        photo_name = QFontMetrics(name).elidedText(self.photo_name, Qt.TextElideMode.ElideMiddle, left + COLUMN_WIDTH - photo_name_left)
        draw_text(painter, photo_name_left, self.photo_name_top, photo_name, color("muted"), name)
        for field, label in FIELDS:
            draw_text(painter, left, self.label_tops[field], label, color("muted"), name)
        draw_checkbox(painter, self.checkbox_center, self.framed, self.option_hovered)
        draw_text(painter, *self.option_label, "Blurred photo around the card", color("text"), name)
        records = (
            f"Records: {', '.join(self.text.record_names)}" if self.text.record_names else "No records this session"
        )
        for index, line in enumerate(wrap(records, name, COLUMN_WIDTH)):
            draw_text(painter, left, self.records_top + index * line_height(name), line, color("muted"), name)
        message, message_color = self.status
        if message:
            for index, line in enumerate(reversed(wrap(message, name, COLUMN_WIDTH))):
                draw_text(painter, left, self.status_top - index * line_height(name), line, color(message_color), name)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def _over_option(self, point) -> bool:
        left, top, right, bottom = self.option_area
        return left <= point.x() < right and top <= point.y() < bottom

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if any([button.press(point) for button in self.buttons]):
            self.update()
        elif self._over_option(point):
            self.framed = not self.framed
            self.render()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(event.position().toPoint()) for button in self.buttons]):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        changed = PaintedButton.update_hover(self.buttons, point)
        if self._over_option(point) != self.option_hovered:
            self.option_hovered = self._over_option(point)
            changed = True
        if changed:
            self.update()
        over = self._over_option(point) or any(button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _event) -> None:
        if PaintedButton.update_hover(self.buttons, None) or self.option_hovered:
            self.option_hovered = False
            self.update()
