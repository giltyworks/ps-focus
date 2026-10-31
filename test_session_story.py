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
        self.assertEqual(format_date(date(2026, 10, 31)), "31 OCTOBER 2026")
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
        self.assertEqual(text.date, "31 OCTOBER 2026")
        # Saturday, started at 1:14 pm
        self.assertEqual(text.title, "Sat Lunch Session")
        self.assertEqual(text.programs, "Photoshop · Krita")
        self.assertEqual(text.focus_time, "1h 20m")
        self.assertEqual(text.started, "1:14pm")
        self.assertEqual(text.record_count, 2)
        self.assertEqual(text.edited(title="Gun pose study").title, "Gun pose study")


def sample_text(records: tuple[str, ...] = ("Longest session ever",)) -> StoryText:
    return StoryText("31 OCTOBER 2026", "Sat Lunch Session", "Photoshop", "1h 52m", "1:14pm", records)


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

    def test_the_card_uses_its_own_typeface(self):
        from qt.story_card import story_family

        self.assertEqual(story_family(), "Archivo")

    def test_stories_are_story_sized_with_or_without_a_photo(self):
        from PySide6.QtGui import QImage
        from qt.story_card import STORY_SIZE, render_card, render_story

        photo = QImage(str(self.photo()))
        for image in (render_story(photo, sample_text()), render_story(photo, sample_text(), framed=False), render_story(None, sample_text(()))):
            self.assertEqual(image.size(), STORY_SIZE)
        card = render_card(450, photo, sample_text())
        self.assertEqual((card.width(), card.height()), (450, 800))

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

    def test_a_long_title_shrinks_to_stay_on_one_line(self):
        from PySide6.QtGui import QFontMetricsF
        from qt.story_card import TITLE_FONT, _fitted_font

        title = "A very long title for a session that would never fit on one line of the card"
        font = _fitted_font(10.8, TITLE_FONT, title, 800)
        self.assertLessEqual(QFontMetricsF(font).horizontalAdvance(title), 800 * 1.02)


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

    def test_every_piece_of_text_can_be_changed(self):
        self.dialog.fields["title"].setText("Gun pose study")
        self.dialog.fields["title"].textEdited.emit("Gun pose study")
        self.dialog.fields["started"].setText("7:00pm")
        self.dialog.fields["started"].textEdited.emit("7:00pm")
        self.assertEqual(self.dialog.text.title, "Gun pose study")
        self.assertEqual(self.dialog.text.started, "7:00pm")
        self.assertEqual(set(self.dialog.fields), {"title", "date", "programs", "focus_time", "started"})

    def test_a_photo_goes_behind_the_card_and_a_bad_file_says_so(self):
        from PySide6.QtGui import QColor, QImage

        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("#c03030"))
        image.save(str(self.folder / "red.jpg"))
        self.assertTrue(self.dialog.choose_photo(str(self.folder / "red.jpg")))
        self.assertEqual(self.dialog.photo_name, "red.jpg")
        corner = self.dialog.story.pixelColor(10, 960)
        self.assertGreater(corner.red(), corner.green())
        (self.folder / "broken.jpg").write_bytes(b"not a picture")
        self.assertFalse(self.dialog.choose_photo(str(self.folder / "broken.jpg")))
        self.assertEqual(self.dialog.status[1], "red")
        # The photo already chosen stays
        self.assertEqual(self.dialog.photo_name, "red.jpg")

    def test_saving_writes_a_story_sized_png(self):
        from PySide6.QtGui import QImage

        self.assertTrue(self.dialog.save_image(str(self.folder / "story")))
        saved = QImage(str(self.folder / "story.png"))
        self.assertEqual((saved.width(), saved.height()), (1080, 1920))
        self.assertEqual(self.dialog.status, ("Saved story.png", "accent"))

    def test_copying_puts_the_story_on_the_clipboard(self):
        self.dialog.copy_image()
        self.assertEqual(QApplication.clipboard().image().size(), self.dialog.story.size())

    def test_the_card_can_fill_the_story_without_the_blurred_frame(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent

        left, top, right, bottom = self.dialog.option_area
        point = QPointF((left + right) / 2, (top + bottom) / 2)
        QApplication.sendEvent(self.dialog, QMouseEvent(QEvent.Type.MouseButtonPress, point, point, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(self.dialog.framed)


if __name__ == "__main__":
    unittest.main()
