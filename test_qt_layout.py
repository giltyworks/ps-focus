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
        self.top = 26 + 2 + 18
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
        self.assertEqual(self.window.viewport.offset, 0)
        self.assertTrue(self.window.clip_margin.isVisible())
        # At the least height the first block has slid up under the header, the anchor's gap still in view
        self.assertEqual(self.window.minimumHeight(), self.top + COMPACT_BOTTOM_SPACE + MODULE_GAP + 140)
        self.window.resize(TODAY_PANEL_WIDTH, self.window.minimumHeight())
        self.assertEqual(self.window.viewport.offset, 100 + MODULE_GAP)

    def test_window_without_blocks_keeps_the_compact_space(self):
        self.window.show_blocks([], None, modules_shown=False)
        self.assertEqual(self.window.height(), self.top + COMPACT_BOTTOM_SPACE)

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


if __name__ == "__main__":
    unittest.main()
