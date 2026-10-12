"""The Qt window's layout: sliding blocks as the window gets shorter, and dragging blocks into a new order"""

from __future__ import annotations

import os
import unittest

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:
    QApplication = None

from app_config import COMPACT_BOTTOM_SPACE, MODULE_GAP, TODAY_PANEL_WIDTH


def _block(height: int) -> "QWidget":
    block = QWidget()
    block.setFixedSize(TODAY_PANEL_WIDTH, height)
    block.border_color = "border"
    # A test block is title all over, so pressing anywhere on it puts it in a new order
    block.control_at = lambda _point: "title"
    return block


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        from qt.window import MainWindow

        self.window = MainWindow(on_close=lambda: None)
        self.header, self.controls = _block(26), _block(18)
        self.window.set_top(self.header, self.controls)
        from qt.title_bar import TITLE_BAR_HEIGHT

        # The header and checkboxes, and with the window's own title bar above them, where the blocks start
        self.header_rows = 26 + 2 + 18
        self.title = TITLE_BAR_HEIGHT
        self.top = self.title + self.header_rows
        self.first, self.anchor, self.last = _block(100), _block(140), _block(200)
        self.window.show_blocks([self.first, self.anchor, self.last], self.anchor, modules_shown=True)
        self.window.show()

    def tearDown(self):
        self.window.hide()

    def test_window_starts_as_tall_as_every_block(self):
        full = self.top + 3 * MODULE_GAP + 100 + 140 + 200
        self.assertEqual(self.window.height(), full)
        self.assertEqual(self.window.maximumHeight(), full)
        self.assertFalse(self.window.clip_margin.isVisible())

    def test_shortening_hides_later_blocks_then_slides_to_keep_the_anchor_in_view(self):
        # Shorter, but the anchor panel still fits: the blocks stay put and the margin shows
        self.window.resize(TODAY_PANEL_WIDTH, self.top + 2 * MODULE_GAP + 100 + 140 + COMPACT_BOTTOM_SPACE)
        self.assertEqual(self.window.offset, 0)
        self.assertTrue(self.window.clip_margin.isVisible())
        # At the least height the first block has slid up under the header, the anchor's gap still in view
        self.assertEqual(self.window.minimumHeight(), self.top + COMPACT_BOTTOM_SPACE + MODULE_GAP + 140)
        self.window.resize(TODAY_PANEL_WIDTH, self.window.minimumHeight())
        self.assertEqual(self.window.offset, 100 + MODULE_GAP)

    def test_window_without_blocks_keeps_the_compact_space(self):
        self.window.show_blocks([], None, modules_shown=False)
        self.assertEqual(self.window.height(), self.top + COMPACT_BOTTOM_SPACE)

    def test_landscape_puts_blocks_side_by_side_with_the_header_on_the_anchor(self):
        self.window.show_blocks([self.first, self.anchor, self.last], self.anchor, modules_shown=True, landscape=True)
        self.assertEqual((self.first.x(), self.anchor.x(), self.last.x()), (0, TODAY_PANEL_WIDTH + MODULE_GAP, 2 * (TODAY_PANEL_WIDTH + MODULE_GAP)))
        self.assertEqual((self.header.x(), self.header.y()), (TODAY_PANEL_WIDTH + MODULE_GAP, 0))
        self.assertEqual(self.anchor.y(), self.header_rows + MODULE_GAP)
        full_width = 3 * TODAY_PANEL_WIDTH + 2 * MODULE_GAP
        self.assertEqual(self.window.width(), full_width)
        self.assertEqual(self.window.height(), self.title + max(200, self.header_rows + MODULE_GAP + 140))
        # Narrower than everything the last block goes behind the right edge; narrower still the row slides left,
        # the anchor staying whole
        self.window.resize(2 * TODAY_PANEL_WIDTH + MODULE_GAP, self.window.height())
        self.assertEqual(self.window.offset, 0)
        self.window.resize(TODAY_PANEL_WIDTH, self.window.height())
        self.assertEqual(self.window.offset, TODAY_PANEL_WIDTH + MODULE_GAP)

    def test_landscape_without_a_program_panel_puts_the_header_first(self):
        self.window.show_blocks([self.first, self.last], None, modules_shown=True, landscape=True)
        self.assertEqual((self.header.x(), self.first.x()), (0, TODAY_PANEL_WIDTH + MODULE_GAP))

    def test_back_to_portrait_the_header_heads_the_window_again(self):
        self.window.show_blocks([self.first, self.anchor, self.last], self.anchor, modules_shown=True, landscape=True)
        self.window.show_blocks([self.first, self.anchor, self.last], self.anchor, modules_shown=True)
        self.assertIs(self.header.parent(), self.window)
        self.assertEqual((self.header.y(), self.first.mapTo(self.window, QPoint(0, 0)).y()), (self.title, self.top + MODULE_GAP))

    def _mouse(self, widget, kind, point, buttons):
        local = QPointF(widget.mapFromGlobal(point))
        event = QMouseEvent(kind, local, QPointF(point), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget, event)

    def test_dragging_a_block_past_another_reorders_them(self):
        from qt.block_drag import BlockDrag

        order = ["first", "anchor", "last"]
        blocks = {"first": self.first, "anchor": self.anchor, "last": self.last}
        saved = []

        def reordered(new_order):
            order[:] = new_order
            self.window.reorder_blocks([blocks[name] for name in order])

        drag = BlockDrag(blocks, lambda: order, reordered, lambda: saved.append(list(order)))
        start = self.first.mapToGlobal(QPoint(50, 50))
        held = Qt.MouseButton.LeftButton
        self._mouse(self.first, QEvent.Type.MouseButtonPress, start, held)
        self.assertEqual(self.first.border_color, "border")
        # Over the lower half of the last block: the first block moves after it
        below = self.last.mapToGlobal(QPoint(50, 150))
        self._mouse(self.first, QEvent.Type.MouseMove, start + QPoint(0, 10), held)
        self.assertEqual(self.first.border_color, "calendar_blue")
        self._mouse(self.first, QEvent.Type.MouseMove, below, held)
        self.assertEqual(order, ["anchor", "last", "first"])
        self._mouse(self.first, QEvent.Type.MouseButtonRelease, below, Qt.MouseButton.NoButton)
        self.assertEqual(saved, [["anchor", "last", "first"]])
        self.assertEqual(self.first.border_color, "border")
        self.assertEqual(self.first.y(), MODULE_GAP + 140 + MODULE_GAP + 200 + MODULE_GAP)
        del drag

    def test_a_short_press_is_not_a_drag(self):
        from qt.block_drag import BlockDrag

        order = ["first", "anchor", "last"]
        saved = []
        drag = BlockDrag({"first": self.first, "anchor": self.anchor, "last": self.last}, lambda: order, lambda new: None, lambda: saved.append(1))
        start = self.first.mapToGlobal(QPoint(50, 50))
        self._mouse(self.first, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        self._mouse(self.first, QEvent.Type.MouseMove, start + QPoint(2, 2), Qt.MouseButton.LeftButton)
        self._mouse(self.first, QEvent.Type.MouseButtonRelease, start, Qt.MouseButton.NoButton)
        self.assertEqual((order, saved, self.first.border_color), (["first", "anchor", "last"], [], "border"))
        del drag

    def test_hiding_a_dragged_block_restores_cursor_and_clears_drag(self):
        from qt.block_drag import BlockDrag

        order = ["first", "anchor", "last"]
        drag = BlockDrag({"first": self.first, "anchor": self.anchor, "last": self.last}, lambda: order, lambda new: None, lambda: None)
        start = self.first.mapToGlobal(QPoint(50, 50))
        self._mouse(self.first, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
        self._mouse(self.first, QEvent.Type.MouseMove, start + QPoint(0, 10), Qt.MouseButton.LeftButton)
        self.assertIsNotNone(QApplication.overrideCursor())
        self.first.hide()
        self.assertIsNone(QApplication.overrideCursor())
        self.assertEqual(self.first.border_color, "border")
        self.assertIsNone(drag.candidate)
        self.assertIsNone(drag.mode)
        self.assertFalse(drag.dragged)
        del drag


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class CalendarDayTipTests(unittest.TestCase):
    def test_a_day_under_the_mouse_shows_its_date_and_time(self):
        from datetime import date

        from qt.calendar_module import CalendarModule

        class Store:
            def total_for_range(self, start, end):
                return 4800 if start == date(2026, 10, 8) else 0

        calendar = CalendarModule.__new__(CalendarModule)
        calendar.store = Store()
        self.assertEqual(calendar.day_summary(date(2026, 10, 8)), "Thu 8 Oct · 1h 20m")
        self.assertEqual(calendar.day_summary(date(2026, 10, 9)), "Fri 9 Oct")


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class PopupMenuToggleTests(unittest.TestCase):
    def test_clicking_the_opener_of_an_open_menu_closes_it_only(self):
        import time

        from qt.status_menu import PopupMenu

        PopupMenu.dismissed = ("status", time.monotonic())
        self.assertFalse(PopupMenu.opens("status"))
        # The next click opens it again, as does a click on something else
        self.assertTrue(PopupMenu.opens("status"))
        PopupMenu.dismissed = (("person", "A"), time.monotonic())
        self.assertTrue(PopupMenu.opens(("person", "B")))


class TimeAgoTests(unittest.TestCase):
    def test_largest_whole_unit(self):
        from qt.friends_module import time_ago

        self.assertEqual(time_ago(30), "just now")
        self.assertEqual(time_ago(60), "1 minute ago")
        self.assertEqual(time_ago(11 * 3600 + 59 * 60), "11 hours ago")
        self.assertEqual(time_ago(3 * 86400), "3 days ago")


class ExperienceTests(unittest.TestCase):
    def test_whole_years_and_when_reached(self):
        from datetime import datetime

        from qt.settings_page import experience, experience_text

        first = datetime(2024, 7, 31, 14, 5)
        self.assertEqual(experience(None, datetime(2026, 1, 1)), None)
        self.assertEqual(experience(first, datetime(2025, 7, 31, 14, 4)), (0, datetime(2025, 7, 31, 14, 5)))
        self.assertEqual(experience(first, datetime(2026, 10, 12)), (2, datetime(2026, 7, 31, 14, 5)))
        self.assertEqual(experience_text(datetime(2026, 7, 31, 14, 5), True), "Unlocked 31 July 2026, 2:05 PM")
        self.assertEqual(experience_text(datetime(2025, 7, 31, 14, 5), False), "Unlocks 31 July 2025")
