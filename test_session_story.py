"""The session story card: what it says about a day's session, the records it counts, and the image it saves"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from session_story import StoryText, format_date, format_focus_time, format_start, part_of_day, record_name, story_text
from tracker import ActivityStore

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ActivityStore(Path(self.temporary.name).resolve() / "activity.sqlite3")
        self.addCleanup(self.store.close)

    def record(self, day: str, seconds: int, application: str = "Photoshop", slot: int = 10) -> None:
        with self.store.connection:
            self.store.connection.execute(
                "INSERT INTO activity (day, slot, seconds, application) VALUES (?, ?, ?, ?)", (day, slot, seconds, application)
            )


class SessionRecordTests(StoreTestCase):
    def test_the_first_session_of_a_period_sets_no_record(self):
        self.record("2026-10-05", 3600)
        self.assertEqual(self.store.session_records(date(2026, 10, 5)), [])

    def test_beating_every_earlier_session_is_the_record_of_all_time_only(self):
        self.record("2025-06-01", 3000)
        self.record("2026-10-05", 2000)
        self.record("2026-10-20", 3600)
        # The longest ever is also the longest of its year and month, but only the biggest record shows
        self.assertEqual(self.store.session_records(date(2026, 10, 20)), ["ever"])

    def test_a_shorter_session_can_still_be_the_longest_of_its_year_or_month(self):
        self.record("2025-06-01", 9000)
        self.record("2026-02-01", 2000)
        self.record("2026-10-05", 1500)
        self.record("2026-10-20", 3000)
        self.assertEqual(self.store.session_records(date(2026, 10, 20)), ["year"])
        self.record("2026-10-21", 2500)
        self.assertEqual(self.store.session_records(date(2026, 10, 21)), [])
        self.record("2026-11-02", 1000)
        self.record("2026-11-03", 1200)
        self.assertEqual(self.store.session_records(date(2026, 11, 3)), ["month"])

    def test_records_are_counted_as_they_stood_on_the_day(self):
        self.record("2026-10-05", 2000)
        self.record("2026-10-06", 3000)
        # Beaten later, but it was the record when it was set
        self.record("2026-10-07", 4000)
        self.assertEqual(self.store.session_records(date(2026, 10, 6)), ["ever"])

    def test_a_tie_or_a_day_under_the_session_minimum_is_no_record(self):
        self.record("2026-10-05", 3000)
        self.record("2026-10-06", 3000)
        self.assertEqual(self.store.session_records(date(2026, 10, 6)), [])
        self.record("2026-10-07", 800)
        self.assertEqual(self.store.session_records(date(2026, 10, 7)), [])

    def test_the_main_programs_record_counts_once_several_programs_are_tracked(self):
        self.record("2026-10-05", 5000, "Photoshop")
        self.record("2026-10-06", 1000, "Krita")
        self.record("2026-10-07", 3000, "Photoshop")
        self.record("2026-10-07", 1200, "Krita")
        # Not the longest session overall, but the longest in Krita, which led neither earlier day; here Photoshop leads
        self.assertEqual(self.store.session_records(date(2026, 10, 7)), [])
        self.record("2026-10-08", 2000, "Krita")
        self.assertEqual(self.store.session_records(date(2026, 10, 8)), ["program"])

    def test_with_one_program_ever_its_record_would_only_repeat_the_overall_one(self):
        self.record("2026-10-05", 2000)
        self.record("2026-10-06", 3000)
        self.assertNotIn("program", self.store.session_records(date(2026, 10, 6)))


class StoryTextTests(StoreTestCase):
    def test_formats(self):
        self.assertEqual(format_focus_time(6720), "1h 52m")
        self.assertEqual(format_focus_time(2700), "45m")
        self.assertEqual(format_focus_time(30), "0m")
        self.assertEqual(format_start("13:14"), "1:14pm")
        self.assertEqual(format_start("00:05"), "12:05am")
        self.assertEqual(format_date(date(2026, 10, 31)), "31 OCT 2026")
        self.assertEqual([part_of_day(hour) for hour in (2, 9, 12, 15, 19, 22)],
                         ["Late Night", "Morning", "Lunch", "Afternoon", "Evening", "Late Night"])

    def test_record_names_say_this_year_or_month_only_while_it_is_current(self):
        today = date.today()
        self.assertEqual(record_name("month", today, "Krita"), "Longest session this month")
        self.assertEqual(record_name("year", date(2001, 3, 4), "Krita"), "Longest session of 2001")
        self.assertEqual(record_name("month", date(2001, 3, 4), "Krita"), "Longest session of March 2001")
        self.assertEqual(record_name("program", today, "Krita"), "Longest Krita session")

    def test_the_card_text_for_a_day(self):
        self.assertIsNone(story_text(self.store, date(2026, 10, 31)))
        self.record("2026-10-30", 1800)
        self.record("2026-10-31", 3600, "Photoshop", slot=13)
        self.record("2026-10-31", 1200, "Krita", slot=14)
        with self.store.connection:
            self.store.connection.execute("INSERT INTO session_starts (day, application, started_at) VALUES ('2026-10-31', 'Photoshop', '13:14')")
        text = story_text(self.store, date(2026, 10, 31))
        self.assertEqual(text.date, "31 OCT 2026")
        # Saturday, started at 1:14 pm
        self.assertEqual(text.title, "Sat Lunch Session")
        self.assertEqual(text.programs, "Photoshop · Krita")
        self.assertEqual(text.focus_time, "1h 20m")
        self.assertEqual(text.started, "1:14pm")
        self.assertEqual(text.record_count, 2)


def sample_text(records: tuple[str, ...] = ("Longest session ever",)) -> StoryText:
    return StoryText("31 OCT 2026", "Sat Lunch Session", "Photoshop", "1h 52m", "1:14pm", records)


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class StoryImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def photo(self, name: str = "photo.png") -> Path:
        from PySide6.QtGui import QColor, QImage

        image = QImage(300, 600, QImage.Format.Format_RGB32)
        image.fill(QColor("#4a7a5a"))
        path = self.folder / name
        image.save(str(path))
        return path

    def test_the_card_uses_the_apps_typeface(self):
        from qt.story_card import FAMILY

        self.assertEqual(FAMILY, "Segoe UI")

    def test_stories_are_story_sized_with_or_without_a_photo(self):
        from PySide6.QtGui import QImage
        from qt.story_card import STORY_SIZE, render_card, render_story

        photo = QImage(str(self.photo()))
        for image in (render_story(photo, sample_text()), render_story(None, sample_text(()))):
            self.assertEqual(image.size(), STORY_SIZE)
        card = render_card(450, photo, sample_text())
        self.assertEqual((card.width(), card.height()), (450, 711))

    def test_framed_story_shows_the_blurred_photo_around_the_card(self):
        from PySide6.QtGui import QColor, QImage
        from qt.story_card import render_story

        photo = QImage(str(self.photo()))
        framed = render_story(photo, sample_text())
        # The corner is outside the card: the photo's green, darkened, not the no-photo near-black
        corner = framed.pixelColor(10, 960)
        self.assertGreater(corner.green(), corner.red())
        self.assertGreater(corner.green(), 40)
        # The numbers are white, the text light grey: somewhere in the bottom left there is white
        bottom_left = [framed.pixelColor(x, y) for x in range(140, 600, 4) for y in range(1500, 1700, 4)]
        self.assertTrue(any(pixel == QColor("#ffffff") for pixel in bottom_left))

    def test_a_higher_dim_darkens_the_card_photo_and_leaves_the_text_alone(self):
        from PySide6.QtGui import QColor, QImage
        from qt.story_card import DIM, render_card

        photo = QImage(str(self.photo()))
        light, default, dark = (render_card(450, photo, sample_text(), dim) for dim in (0.0, DIM, 0.5))
        # Part of the photo that no text covers, on the right of the middle of the card
        spot = (400, 330)
        self.assertGreater(light.pixelColor(*spot).lightness(), default.pixelColor(*spot).lightness())
        self.assertGreater(default.pixelColor(*spot).lightness(), dark.pixelColor(*spot).lightness())
        self.assertEqual(DIM, 0.18)
        self.assertTrue(any(dark.pixelColor(x, y) == QColor("#ffffff") for x in range(60, 300, 3) for y in range(500, 650, 3)))

    def test_the_blurred_backdrop_is_kept_for_the_same_photo_and_remade_for_another(self):
        from PySide6.QtGui import QColor, QImage
        import qt.story_card as story_card

        photo = QImage(str(self.photo()))
        first = story_card.render_story(photo, sample_text(), 0.1)
        kept = story_card._kept_backdrop[1]
        before = kept.copy()
        second = story_card.render_story(photo, sample_text(), 0.4)
        # The same picture was reused, and painting a card on a copy of it left it as it was
        self.assertIs(story_card._kept_backdrop[1], kept)
        self.assertEqual(kept, before)
        self.assertNotEqual(first.pixelColor(540, 1000), second.pixelColor(540, 1000))
        # Another photo, or none, makes a new one
        other = QImage(200, 200, QImage.Format.Format_RGB32)
        other.fill(QColor("#c03030"))
        story_card.render_story(other, sample_text())
        self.assertIsNot(story_card._kept_backdrop[1], kept)

    def test_a_long_title_shrinks_to_stay_on_one_line(self):
        from PySide6.QtGui import QFontMetricsF
        from qt.story_card import TITLE_FONT, _fitted_font

        title = "A very long title for a session that would never fit on one line of the card"
        font = _fitted_font(10.8, TITLE_FONT, title, 800)
        # The headless test platform has no fonts installed, so its stand-in font does not scale smoothly: allow a little over
        self.assertLessEqual(QFontMetricsF(font).horizontalAdvance(title), 800 * 1.05)


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class StoryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        from qt.story_dialog import StoryDialog
        from qt.theme import Fonts

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.dialog = StoryDialog(None, Fonts(), date(2026, 10, 31), sample_text())
        self.addCleanup(self.dialog.deleteLater)

    def test_the_text_is_not_editable(self):
        from PySide6.QtWidgets import QLineEdit

        self.assertEqual(self.dialog.findChildren(QLineEdit), [])

    def test_a_photo_goes_behind_the_card_and_a_bad_file_says_so(self):
        from PySide6.QtGui import QColor, QImage

        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("#c03030"))
        image.save(str(self.folder / "red.jpg"))
        self.assertTrue(self.dialog.choose_photo(str(self.folder / "red.jpg")))
        self.assertEqual(self.dialog.photo_name, "red.jpg")
        # The photo's name is shown in the title bar
        self.assertEqual(self.dialog.windowTitle(), "Share session - red.jpg")
        corner = self.dialog.story.pixelColor(10, 960)
        self.assertGreater(corner.red(), corner.green())
        (self.folder / "broken.jpg").write_bytes(b"not a picture")
        self.assertFalse(self.dialog.choose_photo(str(self.folder / "broken.jpg")))
        self.assertEqual(self.dialog.status[1], "red")
        # The photo already chosen stays
        self.assertEqual(self.dialog.photo_name, "red.jpg")

    def test_the_dim_slider_darkens_the_story_and_a_click_on_its_button_opens_it(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor, QImage
        from qt.story_card import DIM
        from qt.story_dialog import MAX_DIM
        from qt.transparency_popup import SLIDER_KNOB, SLIDER_WIDTH, TransparencyPopup

        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("#c0c0c0"))
        image.save(str(self.folder / "grey.jpg"))
        self.dialog.choose_photo(str(self.folder / "grey.jpg"))
        self.assertEqual(self.dialog.dim, DIM)
        before = self.dialog.story.pixelColor(540, 960).lightness()
        # The button is in the preview's top left corner, and opens a slider that grows towards the right
        button = self.dialog.dim_button
        self.assertLess(button.left, self.dialog.preview.center().x())
        button.command()
        popup = next(widget for widget in QApplication.topLevelWidgets() if isinstance(widget, TransparencyPopup) and widget.isVisible())
        self.addCleanup(popup.close)
        self.assertEqual(popup.transparency(), round(DIM / MAX_DIM * 100))
        popup._slide_to(QPoint(popup.slider_left + SLIDER_WIDTH, popup.slider_top), True)
        self.assertAlmostEqual(self.dialog.dim, MAX_DIM)
        self.assertLess(self.dialog.story.pixelColor(540, 960).lightness(), before)
        popup._slide_to(QPoint(popup.slider_left - SLIDER_KNOB, popup.slider_top), True)
        self.assertEqual(self.dialog.dim, 0)
        self.assertGreater(self.dialog.story.pixelColor(540, 960).lightness(), before)

    def test_a_quick_drag_of_the_dim_slider_draws_the_preview_once(self):
        from unittest.mock import patch

        with patch.object(self.dialog, "render") as render:
            for position in (10, 20, 30):
                self.dialog._dim_chosen(position, False)
            self.assertEqual(render.call_count, 0)
            QApplication.processEvents()
            self.assertEqual(render.call_count, 1)
            self.assertAlmostEqual(self.dialog.dim, 0.15)
            # Letting go draws at once
            self.dialog._dim_chosen(40, True)
            self.assertEqual(render.call_count, 2)

    def test_saving_writes_a_story_sized_png(self):
        from PySide6.QtGui import QImage

        self.assertTrue(self.dialog.save_image(str(self.folder / "story")))
        saved = QImage(str(self.folder / "story.png"))
        self.assertEqual((saved.width(), saved.height()), (1080, 1920))
        self.assertEqual(self.dialog.status, ("Saved story.png", "accent"))

    def test_saving_to_icloud_puts_a_png_in_the_upload_folder_without_overwriting(self):
        from PySide6.QtGui import QImage

        uploads = self.folder / "iCloudPhotos" / "Photos"
        self.assertTrue(self.dialog.save_to_icloud(uploads))
        self.assertTrue(self.dialog.save_to_icloud(uploads))
        names = sorted(path.name for path in uploads.iterdir())
        self.assertEqual(names, ["PS Focus session 2026-10-31 (2).png", "PS Focus session 2026-10-31.png"])
        self.assertEqual(QImage(str(uploads / names[1])).size().width(), 1080)
        self.assertEqual(self.dialog.status[1], "accent")

    def test_saving_to_icloud_says_so_when_icloud_is_not_set_up(self):
        from unittest.mock import patch

        with patch("qt.story_dialog.icloud_uploads_folder", return_value=None):
            self.assertFalse(self.dialog.save_to_icloud())
        self.assertEqual(self.dialog.status[1], "red")

    def test_the_enlarge_button_opens_a_larger_preview_that_a_click_closes(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from qt.story_dialog import LargePreview

        def click(widget, point):
            QApplication.sendEvent(widget, QMouseEvent(QEvent.Type.MouseButtonPress, point, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

        button = self.dialog.enlarge_button
        click(self.dialog, QPointF(button.left + button.width / 2, button.top + button.height / 2))
        QApplication.sendEvent(self.dialog, QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(button.left + 5, button.top + 5), QPointF(button.left + 5, button.top + 5), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        large = self.dialog.findChildren(LargePreview)
        self.assertEqual(len(large), 1)
        # Larger than the small preview, in the story's 9:16 shape
        self.assertGreater(large[0].height(), self.dialog.preview.height())
        self.assertAlmostEqual(large[0].width() / large[0].height(), 9 / 16, places=2)
        click(large[0], large[0].rect().center().toPointF())
        self.assertFalse(large[0].isVisible())

    def test_clicking_the_preview_asks_for_a_photo_and_does_not_enlarge_it(self):
        from unittest.mock import patch
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        from qt.story_dialog import LargePreview

        centre = self.dialog.preview.center()
        with patch.object(self.dialog, "choose_photo") as chosen:
            QApplication.sendEvent(self.dialog, QMouseEvent(QEvent.Type.MouseButtonPress, centre, centre, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        chosen.assert_called_once()
        self.assertEqual(self.dialog.findChildren(LargePreview), [])

    def test_hovering_the_preview_and_the_expand_button_shows_what_each_does(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        def hover(point):
            QApplication.sendEvent(self.dialog, QMouseEvent(QEvent.Type.MouseMove, point, point, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

        button = self.dialog.enlarge_button
        hover(self.dialog.preview.center())
        self.assertEqual(self.dialog.toolTip(), "Choose a photo…")
        hover(QPointF(button.left + button.width / 2, button.top + button.height / 2))
        self.assertEqual(self.dialog.toolTip(), "Expand")
        hover(QPointF(self.dialog.width() / 2, self.dialog.height() - 1))
        self.assertEqual(self.dialog.toolTip(), "")

    def test_the_enlarge_button_sits_over_the_previews_top_right_corner(self):
        button, preview = self.dialog.enlarge_button, self.dialog.preview
        self.assertLessEqual(button.right, preview.right())
        self.assertGreaterEqual(button.top, preview.top())
        self.assertLess(preview.right() - button.right, 12)
        self.assertLess(button.top - preview.top(), 12)

    def test_saving_to_google_drive_puts_a_png_in_the_folder_without_overwriting(self):
        from PySide6.QtGui import QImage

        folder = self.folder / "My Drive" / "PS Focus Stories"
        self.assertTrue(self.dialog.save_to_google_drive(folder))
        self.assertTrue(self.dialog.save_to_google_drive(folder))
        names = sorted(path.name for path in folder.iterdir())
        self.assertEqual(names, ["PS Focus session 2026-10-31 (2).png", "PS Focus session 2026-10-31.png"])
        self.assertEqual(QImage(str(folder / names[1])).size().width(), 1080)
        self.assertEqual(self.dialog.status[1], "accent")

    def test_saving_to_google_drive_says_so_when_drive_is_not_set_up(self):
        from unittest.mock import patch

        with patch("qt.story_dialog.google_drive_folder", return_value=None):
            self.assertFalse(self.dialog.save_to_google_drive())
        self.assertEqual(self.dialog.status[1], "red")

    def test_the_google_drive_folder_is_found_inside_my_drive(self):
        from unittest.mock import patch
        from qt.story_dialog import google_drive_folder

        # Only G:\My Drive exists, and only C and G are drives of the PC
        with patch("qt.story_dialog.fixed_drive_letters", return_value="CG"), patch.object(Path, "is_dir", lambda path: path == Path("G:/My Drive")):
            self.assertEqual(google_drive_folder(), Path("G:/My Drive/PS Focus Stories"))
        with patch("qt.story_dialog.fixed_drive_letters", return_value="CG"), patch.object(Path, "is_dir", lambda path: False):
            self.assertIsNone(google_drive_folder())
        # A My Drive on a drive that is not a fixed one, such as a network drive, is not looked at
        with patch("qt.story_dialog.fixed_drive_letters", return_value="C"), patch.object(Path, "is_dir", lambda path: path == Path("G:/My Drive")):
            self.assertIsNone(google_drive_folder())

    def test_only_the_pcs_own_drives_are_looked_for_google_drive(self):
        from qt.story_dialog import fixed_drive_letters

        letters = fixed_drive_letters()
        if os.name == "nt":
            self.assertIn("C", letters)
        self.assertEqual(letters, "".join(sorted(set(letters))))

    def test_a_save_message_makes_the_window_taller_and_clearing_it_makes_it_shorter_again(self):
        resting = self.dialog.height()
        self.dialog.status = ("Saved to iCloud Photos. It reaches your devices once iCloud syncs", "accent")
        self.assertGreater(self.dialog.height(), resting)
        self.dialog.status = ("", "muted")
        self.assertEqual(self.dialog.height(), resting)

    def test_a_very_long_save_message_takes_no_more_than_the_lines_it_is_given(self):
        from qt.story_dialog import STATUS_LINES
        from qt.theme import line_height

        resting = self.dialog.height()
        self.dialog.status = ("word " * 200, "red")
        self.assertLessEqual(self.dialog.height() - resting, 3 + STATUS_LINES * line_height(self.dialog.fonts.small))

    def test_dragging_the_share_windows_title_row_moves_it(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        dialog = self.dialog
        dialog.move(100, 100)
        start = dialog.pos()
        grab = QPoint(60, 10)
        QApplication.sendEvent(dialog, QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(grab), QPointF(dialog.mapToGlobal(grab)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(dialog, QMouseEvent(QEvent.Type.MouseMove, QPointF(grab), QPointF(dialog.mapToGlobal(grab) + QPoint(30, 20)), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(dialog.pos(), start + QPoint(30, 20))

    def test_escape_closes_the_share_window(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent

        self.dialog.show()
        QApplication.sendEvent(self.dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(self.dialog.isVisible())

    def test_the_photo_button_in_the_title_row_is_pressed_and_not_dragged(self):
        from unittest.mock import patch
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        dialog = self.dialog
        point = dialog.photo_button.left + dialog.photo_button.width // 2, dialog.photo_button.top + dialog.photo_button.height // 2
        local = QPointF(*point)
        with patch.object(dialog, "choose_photo") as chosen:
            dialog.photo_button.command = dialog.choose_photo
            for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                QApplication.sendEvent(dialog, QMouseEvent(kind, local, QPointF(dialog.mapToGlobal(local.toPoint())), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        chosen.assert_called_once()
        self.assertIsNone(dialog.drag_offset)

    def test_the_four_buttons_under_the_preview_fill_its_width_exactly(self):
        dialog = self.dialog
        row = [dialog.icloud_button, dialog.drive_button, dialog.copy_button, dialog.save_button]
        self.assertEqual(row[0].left, dialog.preview.left())
        self.assertEqual(row[-1].right, dialog.preview.right())

    def test_rounding_a_window_needs_a_handle_and_does_nothing_without_one(self):
        from windows_startup import round_window_corners

        round_window_corners(None)
        round_window_corners(0)

    def test_the_logo_is_made_hollow_once(self):
        from qt.story_card import hollow_logo

        self.assertIs(hollow_logo(), hollow_logo())

    def test_copying_puts_the_story_on_the_clipboard(self):
        self.dialog.copy_image()
        self.assertEqual(QApplication.clipboard().image().size(), self.dialog.story.size())


if __name__ == "__main__":
    unittest.main()
