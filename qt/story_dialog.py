"""The session story window, opened from a day's overview: a preview of the story card for that day's session, which a
click chooses a photo for and a button over its corner shows larger, and buttons to copy the 1080x1920 image, save it as a
PNG or save it to iCloud Photos or Google Drive to post from a phone. The card itself is painted by story_card"""

from __future__ import annotations

import ctypes
import os
import string
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, QStandardPaths, Qt
from PySide6.QtGui import QIcon, QImage, QImageReader, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from app_config import EDGE_PADDING, resource_path
from session_story import StoryText

from .app_dialog import AppDialog
from .app_popup import CLOSE_WIDTH, AppPopup
from .header import fit_text
from .module import PaintedButton, draw_rounded_box
from .settings_page import wrap
from .story_card import STORY_SIZE, render_story
from .theme import Fonts, color, draw_text, line_height
from .title_bar import ICON_SIZE, TITLE_BAR_HEIGHT

WINDOW_TITLE = "Share session"
PADDING = 3
# The preview: the story at a quarter of its size, so 270 by 480; a click on it chooses a photo. The button over its top
# right corner, which shows it larger, its size, its distance from the corner and how solid it is
ENLARGE_BUTTON_SIZE = (26, 24)
ENLARGE_BUTTON_MARGIN = 5
ENLARGE_BUTTON_ALPHA = 200
PREVIEW_SCALE = 0.25
PREVIEW_RADIUS = 6
ROW_GAP = 9
BUTTON_PADX, BUTTON_PADY = 12, 6
ICON_BUTTON_WIDTH = 34
# Space before the words of a button that has them, which are cut short if they would not otherwise fit
TEXT_BUTTON_PADX = 8
# The space above and below the buttons under the preview
BUTTON_GAP = 3
# The most lines below the buttons for what the last save said
STATUS_LINES = 3
# The enlarged preview takes this share of the screen's height, the Windows title bar included
LARGE_PREVIEW_HEIGHT = 0.9
TITLE_BAR_ALLOWANCE = 40
PHOTO_FILTER = "Images (*.jpg *.jpeg *.png *.webp *.bmp)"


def read_photo(path: str) -> QImage:
    """The photo turned upright as the phone or camera took it, or a null image if it cannot be read"""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    return reader.read()


def icloud_uploads_folder() -> Path | None:
    """Where iCloud for Windows takes pictures to put in iCloud Photos, or None when it isn't set up for Photos. The
    current app syncs the Photos folder in iCloudPhotos itself; the older one had an Uploads folder under Pictures"""
    home = Path.home()
    for folder in (home / "iCloudPhotos" / "Photos", home / "Pictures" / "iCloud Photos" / "Uploads"):
        if folder.parent.is_dir():
            return folder
    return None


def fixed_drive_letters() -> str:
    """The letters of the drives that are part of the PC, as Windows lists them. Removable and network drives, which can
    stall for seconds when looked at while nothing answers, are left out; Google Drive's own drive counts as fixed"""
    if os.name != "nt":
        return ""
    kernel32 = ctypes.windll.kernel32
    present = kernel32.GetLogicalDrives()
    # DRIVE_FIXED
    return "".join(letter for index, letter in enumerate(string.ascii_uppercase) if present >> index & 1 and kernel32.GetDriveTypeW(f"{letter}:\\") == 3)


def google_drive_folder() -> Path | None:
    """A PS Focus Stories folder inside My Drive, as Google Drive for desktop shows it, or None when it isn't set up.
    Drive for desktop makes My Drive a drive letter of its own, or a folder in the user's home"""
    candidates = [Path(f"{letter}:/") / "My Drive" for letter in fixed_drive_letters()]
    candidates += [Path.home() / "Google Drive" / "My Drive", Path.home() / "Google Drive"]
    for mine in candidates:
        if mine.is_dir():
            return mine / "PS Focus Stories"
    return None


def default_file_name(session_day: date) -> str:
    return f"PS Focus session {session_day.isoformat()}.png"


class LeftTextButton(PaintedButton):
    """A button whose words start at its left edge, a little in; they are cut short if the button has been made too
    narrow for them"""

    def paint(self, painter: QPainter) -> None:
        words, self.text = self.text, ""
        super().paint(painter)
        self.text = words
        draw_text(
            painter, self.left + TEXT_BUTTON_PADX, self.top + (self.height - line_height(self.font)) // 2,
            fit_text(words, self.font, self.width - 2 * TEXT_BUTTON_PADX), color(self.text_color if self.enabled else "muted"), self.font,
        )


class IconButton(PaintedButton):
    """A button that shows a small drawn icon in place of words; what it does is shown as a tooltip"""

    def __init__(self, glyph: str, tooltip: str, command, fonts: Fonts, text_color: str = "text", fill: str = "panel_alt", solid: bool = False) -> None:
        super().__init__("", command, fonts, BUTTON_PADX, BUTTON_PADY, text_color=text_color, fill=fill, solid=solid)
        self.glyph = glyph
        self.tooltip = tooltip
        self.width = ICON_BUTTON_WIDTH

    def paint(self, painter: QPainter) -> None:
        super().paint(painter)
        x = self.left + self.width / 2
        y = self.top + self.height / 2
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(color(self.text_color if self.enabled else "muted"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self.glyph == "copy":
            # Two overlapping rounded squares: the one behind is cut away where the one in front, and a small gap around
            # it, covers it
            cover = QPainterPath()
            cover.addRoundedRect(QRectF(x - 4.2, y - 4.2, 11.4, 12.4), 2.7, 2.7)
            outside = QPainterPath()
            outside.addRect(QRectF(self.left, self.top, self.width, self.height))
            painter.setClipPath(outside.subtracted(cover))
            painter.drawRoundedRect(QRectF(x - 6, y - 7, 9, 10), 1.5, 1.5)
            painter.setClipping(False)
            painter.drawRoundedRect(QRectF(x - 3, y - 3, 9, 10), 1.5, 1.5)
        elif self.glyph == "expand":
            # Four corner brackets of a square
            for sign_x, sign_y in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                corner = QPointF(x + sign_x * 5.5, y + sign_y * 5.5)
                painter.drawPolyline([QPointF(corner.x() - sign_x * 4, corner.y()), corner, QPointF(corner.x(), corner.y() - sign_y * 4)])
        elif self.glyph == "photo":
            # A picture, a sun and a hill in a frame, with a plus in its top right corner where the frame is cut away
            corner = QPointF(x + 7, y - 6)
            cover = QPainterPath()
            cover.addEllipse(corner, 4.4, 4.4)
            outside = QPainterPath()
            outside.addRect(QRectF(self.left, self.top, self.width, self.height))
            painter.setClipPath(outside.subtracted(cover))
            painter.drawRoundedRect(QRectF(x - 7, y - 6, 14, 12), 2, 2)
            painter.drawEllipse(QPointF(x - 3.5, y - 2), 1.2, 1.2)
            painter.drawPolyline([QPointF(x - 6.5, y + 5), QPointF(x - 1.5, y + 0.5), QPointF(x + 1, y + 3), QPointF(x + 3, y + 1.2),
                                  QPointF(x + 6.5, y + 5)])
            painter.setClipping(False)
            painter.drawLine(QPointF(corner.x() - 2.8, corner.y()), QPointF(corner.x() + 2.8, corner.y()))
            painter.drawLine(QPointF(corner.x(), corner.y() - 2.8), QPointF(corner.x(), corner.y() + 2.8))
        else:
            # An arrow down into a tray
            painter.drawLine(QPointF(x, y - 6), QPointF(x, y + 3))
            painter.drawPolyline([QPointF(x - 4, y - 1), QPointF(x, y + 3), QPointF(x + 4, y - 1)])
            painter.drawPolyline([QPointF(x - 6, y + 2), QPointF(x - 6, y + 7), QPointF(x + 6, y + 7), QPointF(x + 6, y + 2)])
        painter.restore()


class LargePreview(AppDialog):
    """The story as large as the screen allows, to look over before it is shared; a click or Escape closes it"""

    def __init__(self, parent: QWidget, story: QImage) -> None:
        super().__init__(parent, "Preview")
        screen = (parent.screen() or self.screen()).availableGeometry()
        height = round(screen.height() * LARGE_PREVIEW_HEIGHT) - TITLE_BAR_ALLOWANCE
        width = round(height * story.width() / story.height())
        self.story = story.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.drawImage(0, 0, self.story)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class StoryDialog(AppPopup):
    """Drawn with the app's own title row, as the small popups are, so the photo's button can sit in it beside the ×;
    but a window that stays until it is closed, not a popup that a click elsewhere closes, and that takes the clicks
    from PS Focus while open, as the app's dialogs do"""

    def __init__(self, parent: QWidget | None, fonts: Fonts, session_day: date, text: StoryText) -> None:
        super().__init__(parent, fonts, WINDOW_TITLE)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowIcon(QIcon(str(resource_path("assets/icons/PSFocus.ico"))))
        # The title row is as tall as the main window's
        self.title_height = TITLE_BAR_HEIGHT
        self.session_day = session_day
        self.text = text
        self.photo: QImage | None = None
        self.photo_name = ""
        self.status = ("", "muted")
        self.story = render_story(None, text)
        self.setMouseTracking(True)
        self.photo_button = IconButton("photo", "Choose photo…", self.choose_photo, fonts, solid=True)
        self.copy_button = IconButton("copy", "Copy to clipboard", self.copy_image, fonts)
        self.save_button = IconButton("download", "Save image…", self.save_image, fonts, text_color="accent", fill="accent_dark", solid=True)
        self.icloud_button = LeftTextButton("Save to iCloud", self.save_to_icloud, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text")
        self.drive_button = LeftTextButton("Save to G Drive", self.save_to_google_drive, fonts, BUTTON_PADX, BUTTON_PADY, text_color="text")
        # Over the preview's top right corner, a little see-through so the picture shows round it
        self.enlarge_button = IconButton("expand", "Expand", self.enlarge_preview, fonts, solid=True)
        self.enlarge_button.alpha = ENLARGE_BUTTON_ALPHA
        self.buttons = [self.photo_button, self.enlarge_button, self.drive_button, self.icloud_button, self.copy_button, self.save_button]
        self._lay_out()

    def _lay_out(self) -> None:
        small = line_height(self.fonts.small)
        preview_width = round(STORY_SIZE.width() * PREVIEW_SCALE)
        preview_height = round(STORY_SIZE.height() * PREVIEW_SCALE)
        self.window_width = preview_width + 2 * PADDING
        # In the title row, left of the close button, the photo's icon button, a little shorter than the row; the title
        # keeps clear of it
        self.photo_button.height = self.title_height - 8
        self.photo_button.place(self.window_width - CLOSE_WIDTH - BUTTON_GAP - ICON_BUTTON_WIDTH, 4)
        self.title_reserve = ICON_BUTTON_WIDTH + BUTTON_GAP
        preview_top = self.title_height + BUTTON_GAP
        self.preview = QRectF(PADDING, preview_top, preview_width, preview_height)
        self.enlarge_button.width, self.enlarge_button.height = ENLARGE_BUTTON_SIZE
        self.enlarge_button.place(round(self.preview.right()) - self.enlarge_button.width - ENLARGE_BUTTON_MARGIN, preview_top + ENLARGE_BUTTON_MARGIN)
        bottom = preview_top + preview_height
        # Under the preview, as wide as it: the records, if the session set any, then one row of buttons, left to
        # right: iCloud, G Drive, copy and download, the first two as wide as the wider and no wider than the row allows;
        # and, when there is one, the status
        self.content_width = preview_width
        self.records_top = bottom + ROW_GAP
        if self.text.record_names:
            self.records_lines = wrap(f"Records: {', '.join(self.text.record_names)}", self.fonts.small, self.content_width)
            top = self.records_top + len(self.records_lines) * small + BUTTON_GAP
        else:
            self.records_lines = []
            top = bottom + BUTTON_GAP
        room = self.content_width - 2 * ICON_BUTTON_WIDTH - 3 * BUTTON_GAP
        wide = max(self.icloud_button.width, self.drive_button.width)
        if 2 * wide > room:
            # Too wide for the row: the two text buttons shrink so the four fill it exactly, from the preview's left
            # edge to its right
            self.icloud_button.width = room // 2
            self.drive_button.width = room - room // 2
        else:
            self.icloud_button.width = self.drive_button.width = wide
        left_edge = PADDING
        for button in (self.icloud_button, self.drive_button, self.copy_button, self.save_button):
            button.place(left_edge, top)
            left_edge += button.width + BUTTON_GAP
        buttons_bottom = top + self.drive_button.height
        self.status_top = buttons_bottom + BUTTON_GAP
        # The window ends just under the buttons, and is made taller only while a message is shown below them
        self.base_height = buttons_bottom + PADDING
        self._fit_height()

    @property
    def status(self) -> tuple[str, str]:
        """What the last save said, and the colour to say it in"""
        return self._status

    @status.setter
    def status(self, value: tuple[str, str]) -> None:
        self._status = value
        if hasattr(self, "base_height"):
            self._fit_height()

    def _fit_height(self) -> None:
        message = self._status[0]
        lines = wrap(message, self.fonts.small, self.content_width)[:STATUS_LINES] if message else []
        extra = BUTTON_GAP + len(lines) * line_height(self.fonts.small) if lines else 0
        self.setFixedSize(self.window_width, self.base_height + extra)

    def render(self) -> None:
        self.story = render_story(self.photo, self.text)
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
        # The photo's name goes in the window's title bar, after the window's name
        self.setWindowTitle(f"{WINDOW_TITLE} - {self.photo_name}")
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

    def enlarge_preview(self) -> None:
        self.render()
        LargePreview(self, self.story).show_centred_on(self)

    def _save_to_synced_folder(self, folder: Path | None, service: str, missing: str, synced: str, failed: str) -> bool:
        """Put the story, under a name not yet taken, in a folder a sync program sends to an online service; return
        whether it was saved. With no folder, say what is missing"""
        if folder is None:
            self.status = (missing, "red")
            self.update()
            return False
        self.render()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / default_file_name(self.session_day)
            number = 2
            while target.exists():
                target = folder / f"PS Focus session {self.session_day.isoformat()} ({number}).png"
                number += 1
            saved = self.story.save(str(target), "PNG")
        except OSError:
            saved = False
        self.status = (f"Saved to {service}. {synced}", "accent") if saved else (failed, "red")
        self.update()
        return saved

    def save_to_icloud(self, folder: Path | None = None) -> bool:
        """Put the story in the folder iCloud for Windows syncs, which sends it to iCloud Photos"""
        return self._save_to_synced_folder(
            folder or icloud_uploads_folder(), "iCloud Photos",
            "iCloud Photos isn't set up on this PC. Install iCloud for Windows and turn Photos on",
            "It reaches your devices once iCloud syncs", "Couldn't save to iCloud Photos. Is iCloud for Windows running?",
        )

    def save_to_google_drive(self, folder: Path | None = None) -> bool:
        """Put the story in a PS Focus Stories folder in My Drive, which Google Drive for desktop uploads"""
        return self._save_to_synced_folder(
            folder or google_drive_folder(), "Google Drive",
            "Google Drive isn't set up on this PC. Install Google Drive for desktop and sign in",
            "It appears in Drive once Google Drive for desktop uploads it", "Couldn't save to Google Drive. Is Google Drive for desktop running?",
        )

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        self.paint_frame(painter)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        draw_rounded_box(painter, self.preview.adjusted(-1, -1, 1, 1), PREVIEW_RADIUS + 1, color("panel"), color("border"))
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(self.preview, PREVIEW_RADIUS, PREVIEW_RADIUS)
        painter.setClipPath(clip)
        painter.drawImage(self.preview, self.story)
        painter.restore()
        name = self.fonts.small
        for index, line in enumerate(self.records_lines):
            draw_text(painter, PADDING, self.records_top + index * line_height(name), line, color("muted"), name)
        message, message_color = self.status
        if message:
            for index, line in enumerate(wrap(message, name, self.content_width)[:STATUS_LINES]):
                draw_text(painter, PADDING, self.status_top + index * line_height(name), line, color(message_color), name)
        for button in self.buttons:
            button.paint(painter)
        painter.end()

    def paint_frame(self, painter: QPainter) -> None:
        """The main window's title row: the icon and the name at the left, the close button at the right; and a faint
        outline"""
        painter.fillRect(self.rect(), color("background"))
        painter.drawPixmap(EDGE_PADDING, (self.title_height - ICON_SIZE) // 2, self.windowIcon().pixmap(ICON_SIZE, ICON_SIZE))
        name_left = EDGE_PADDING + ICON_SIZE + 8
        close = self.close_area()
        title = fit_text(self.windowTitle(), self.fonts.small, close.left() - self.title_reserve - 6 - name_left)
        draw_text(painter, name_left, (self.title_height - line_height(self.fonts.small)) // 2, title, color("text"), self.fonts.small)
        self.paint_close(painter)
        self.paint_outline(painter)

    def title_control_at(self, point: QPoint) -> bool:
        return self.photo_button.contains(point)

    def content_pressed(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position().toPoint()
        if any([button.press(point) for button in self.buttons]):
            self.update()
        elif self.preview.contains(point):
            # Clicking the picture is how a photo is put behind it
            self.choose_photo()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and any([button.release(event.position().toPoint()) for button in self.buttons]):
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        # The buttons' hover and tooltips follow the pointer everywhere, the photo's being in the title row
        point = event.position().toPoint()
        if PaintedButton.update_hover(self.buttons, point):
            self.update()
        tip = next((button.tooltip for button in self.buttons if isinstance(button, IconButton) and button.contains(point)), "")
        self.setToolTip(tip or ("Choose a photo…" if self.preview.contains(point) else ""))
        super().mouseMoveEvent(event)

    def content_moved(self, event: QMouseEvent) -> None:
        point = event.position().toPoint()
        over = self.preview.contains(point) or any(button.contains(point) for button in self.buttons)
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if PaintedButton.update_hover(self.buttons, None):
            self.update()
