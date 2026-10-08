"""Floating modules in the Qt app: dragging them out by the grip, snapping, moving together, docking back, swapping,
and keeping their places between runs. Runs on Qt's offscreen platform with temporary data"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None

from qt.docking import attached_panels, snap_position


class DockingRulesTests(unittest.TestCase):
    def test_snaps_beside_a_neighbour_with_an_end_aligned(self):
        # 15 pixels right of a panel ending at 100, and 7 below its top: snaps flush, tops level
        self.assertEqual(snap_position(115, 57, 50, 40, [(0, 50, 100, 150)]), (100, 50))

    def test_snaps_under_a_neighbour(self):
        self.assertEqual(snap_position(8, 162, 50, 40, [(0, 50, 100, 150)]), (0, 150))

    def test_does_not_snap_from_afar(self):
        self.assertEqual(snap_position(140, 57, 50, 40, [(0, 50, 100, 150)]), (140, 57))

    def test_side_targets_snap_only_beside(self):
        target = [(0, 50, 100, 80)]
        self.assertEqual(snap_position(110, 42, 50, 40, [], side_targets=target), (100, 80 - 40))
        self.assertEqual(snap_position(10, 92, 50, 40, [], side_targets=target), (10, 92))

    def test_attached_panels_follow_the_chain(self):
        panels = {"a": (100, 0, 200, 50), "b": (200, 0, 300, 50), "c": (500, 0, 600, 50), "d": (100, 52, 200, 90)}
        self.assertEqual(attached_panels((0, 0, 100, 50), panels), {"a", "b", "d"})


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtDockingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        import app_config
        from qt.app import PSFocusQt

        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.saved_settings = {**app_config.DEFAULT_SETTINGS, "show_graph": True, "show_calendar": True, "show_stats": True}
        self.patches = [
            patch.object(app_config, "APP_DATA", folder),
            patch.object(app_config, "DATABASE_PATH", folder / "activity.sqlite3"),
            patch.object(app_config, "SETTINGS_PATH", folder / "settings.json"),
            patch.object(app_config, "BACKUP_DIRECTORIES", [folder / "backups"]),
            patch("qt.app.load_settings", side_effect=lambda: dict(self.saved_settings)),
            patch("qt.app.foreground_application", return_value=None),
            patch.object(PSFocusQt, "_start_tray_icon"),
            patch.object(PSFocusQt, "_check_for_updates"),
            patch("qt.window.MainWindow.place_top_right"),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        for item in self.patches:
            self.addCleanup(item.stop)
        self.app = self._start()

    def _start(self):
        from qt.app import PSFocusQt

        app = PSFocusQt(self.application)
        for timer in (app.tick_timer, app.poll_timer, app.backup_timer):
            timer.stop()
        app.tray_icon = unittest.mock.Mock()
        self.addCleanup(lambda: app.store.close())
        self.addCleanup(lambda: [panel.hide() for panel in list(app.docking.floating.values())])
        self.addCleanup(app.window.hide)
        app.window.move(800, 100)
        self.application.processEvents()
        return app

    def _mouse(self, widget, kind, point, button=None):
        button = Qt.MouseButton.LeftButton if button is None else button
        buttons = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
        local = widget.mapFromGlobal(point)
        QApplication.sendEvent(widget, QMouseEvent(kind, QPointF(local), QPointF(point), button, buttons, Qt.KeyboardModifier.NoModifier))

    def _drag(self, widget, start, *points):
        """Press at start, move through each point, and let go at the last"""
        self._mouse(widget, QEvent.Type.MouseButtonPress, start)
        for point in points:
            # The module may have moved to a window of its own; its events still reach it
            self._mouse(widget, QEvent.Type.MouseMove, point)
        self._mouse(widget, QEvent.Type.MouseButtonRelease, points[-1] if points else start)
        self.application.processEvents()

    def _grip(self, name):
        block = self.app.modules[name]
        return block.mapToGlobal(block.grip_rect().center())

    def _float(self, name, to):
        start = self._grip(name)
        self._drag(self.app.modules[name], start, start + QPoint(0, 10), to)
        self.assertTrue(self.app.docking.is_floating(name))
        return self.app.docking.floating[name]

    def test_grip_dragged_out_floats_the_module_and_the_window_closes_up(self):
        height = self.app.window.height()
        panel = self._float("stats", QPoint(300, 400))
        self.assertTrue(panel.isVisible())
        self.assertTrue(self.app.stats.floating)
        self.assertIs(self.app.stats.parent(), panel)
        self.assertEqual(panel.pos(), QPoint(300, 400) - QPoint(30, 12))
        self.assertNotIn(self.app.stats, self.app._shown_blocks())
        self.assertLess(self.app.window.height(), height)
        self.assertEqual(self.app.settings["floating_modules"], {"stats": [270, 388]})

    def test_grip_drag_inside_the_window_reorders_instead(self):
        calendar = self.app.modules["calendar"]
        target = self.app.panels["Photoshop"]
        above = target.mapToGlobal(QPoint(target.width() // 2, 2))
        self._drag(calendar, self._grip("calendar"), self._grip("calendar") + QPoint(0, 10), above)
        self.assertFalse(self.app.docking.is_floating("calendar"))
        self.assertLess(self.app.block_order.index("calendar"), self.app.block_order.index("Photoshop"))

    def test_dropped_back_in_the_window_by_its_grip_docks_where_let_go(self):
        panel = self._float("graph", QPoint(300, 400))
        stats = self.app.modules["stats"]
        drop = stats.mapToGlobal(QPoint(stats.width() // 2, stats.height() - 2))
        block = self.app.modules["graph"]
        grip = block.mapToGlobal(block.grip_rect().center())
        self._drag(block, grip, grip + QPoint(10, 0), drop)
        self.assertFalse(self.app.docking.is_floating("graph"))
        self.assertFalse(self.app.chart.floating)
        self.assertIn(self.app.chart, self.app._shown_blocks())
        self.assertEqual(self.app.block_order[-1], "graph")
        self.assertEqual(self.app.settings["floating_modules"], {})
        del panel

    def test_dock_icon_docks_the_module(self):
        self._float("calendar", QPoint(300, 400))
        block = self.app.modules["calendar"]
        icon = block.mapToGlobal(block.dock_rect().center())
        self._mouse(block, QEvent.Type.MouseButtonPress, icon)
        self._mouse(block, QEvent.Type.MouseButtonRelease, icon)
        self.assertFalse(self.app.docking.is_floating("calendar"))
        self.assertTrue(self.app.calendar.isVisible())

    def test_a_floating_module_snaps_to_the_window(self):
        panel = self._float("stats", QPoint(300, 400))
        left = self.app.docking.main_bounds()[0]
        block = self.app.modules["stats"]
        grip = block.mapToGlobal(block.grip_rect().center())
        offset = grip - panel.pos()
        # Let go with the panel's right edge 12 pixels short of the window's left edge
        aim = QPoint(left - panel.width() - 12, panel.y()) + offset
        self._drag(block, grip, grip + QPoint(10, 0), aim)
        self.assertEqual(panel.x() + panel.width(), left)

    def test_title_drag_moves_the_window_with_the_panels_touching_it(self):
        panel = self._float("stats", QPoint(300, 400))
        left, top, _right, _bottom = self.app.docking.main_bounds()
        panel.move(left - panel.width(), top)
        loose = self._float("graph", QPoint(100, 700))
        loose_position = loose.pos()
        self.app.docking.main_last_bounds = self.app.docking.main_bounds()
        calendar = self.app.modules["calendar"]
        start = calendar.mapToGlobal(QPoint(20, 8))
        window_position, panel_position = self.app.window.pos(), panel.pos()
        self._drag(calendar, start, start + QPoint(40, 30))
        self.assertEqual(self.app.window.pos(), window_position + QPoint(40, 30))
        self.assertEqual(panel.pos(), panel_position + QPoint(40, 30))
        self.assertEqual(loose.pos(), loose_position)
        self.assertEqual(self.app.settings["main_window_position"], [self.app.window.x(), self.app.window.y()])

    def test_moving_the_window_by_its_title_bar_brings_attached_panels(self):
        panel = self._float("stats", QPoint(300, 400))
        left, top, _right, _bottom = self.app.docking.main_bounds()
        panel.move(left - panel.width(), top + 10)
        self.app.docking.main_last_bounds = self.app.docking.main_bounds()
        with patch("qt.docking.left_button_down", return_value=False):
            self.app.window.move(self.app.window.pos() + QPoint(-50, 20))
            self.application.processEvents()
        self.assertEqual(panel.pos(), QPoint(left - panel.width() - 50, top + 30))

    def test_title_drag_on_a_floating_panel_moves_its_group(self):
        # Floated well apart, as one let go over another would swap with it
        first = self._float("stats", QPoint(100, 50))
        second = self._float("graph", QPoint(700, 50))
        second.move(first.x() + first.width(), first.y())
        block = self.app.modules["stats"]
        start = block.mapToGlobal(QPoint(20, 8))
        self._drag(block, start, start + QPoint(0, 50))
        self.assertEqual(second.pos(), QPoint(first.x() + first.width(), first.y()))

    def test_grip_drag_pulls_one_panel_from_its_group_and_the_gap_closes(self):
        first = self._float("stats", QPoint(100, 500))
        second = self._float("graph", QPoint(100, 100))
        third = self._float("calendar", QPoint(100, 700))
        second.move(first.x() + first.width(), first.y())
        third.move(second.x() + second.width(), first.y())
        block = self.app.modules["graph"]
        grip = block.mapToGlobal(block.grip_rect().center())
        self._drag(block, grip, grip + QPoint(0, 10), grip + QPoint(0, 900))
        # The calendar slides left into the graph's slot; the stats stay
        self.assertEqual(third.x(), first.x() + first.width())
        self.assertEqual(first.pos(), QPoint(70, 488))

    def test_grip_drop_on_another_floating_panel_swaps_them(self):
        first = self._float("stats", QPoint(200, 600))
        second = self._float("graph", QPoint(700, 600))
        first_position, second_position = first.pos(), second.pos()
        block = self.app.modules["stats"]
        grip = block.mapToGlobal(block.grip_rect().center())
        self._drag(block, grip, grip + QPoint(10, 0), grip + (second_position - first_position))
        self.assertEqual(first.pos(), second_position)
        self.assertEqual(second.pos(), first_position)

    def test_unticking_hides_a_floating_panel_and_ticking_shows_it(self):
        panel = self._float("stats", QPoint(300, 400))
        self.app.module_ticked["stats"] = False
        self.app._module_toggled("stats")
        self.assertFalse(panel.isVisible())
        self.app.module_ticked["stats"] = True
        self.app._module_toggled("stats")
        self.assertTrue(panel.isVisible())
        self.assertTrue(self.app.docking.is_floating("stats"))

    def test_hiding_to_the_tray_hides_floating_panels(self):
        panel = self._float("stats", QPoint(300, 400))
        self.app.window_hidden()
        self.assertFalse(panel.isVisible())
        self.app.show_window()
        self.assertTrue(panel.isVisible())

    def test_choosing_an_orientation_docks_everything_and_resets_the_order(self):
        self._float("stats", QPoint(300, 400))
        self.app.block_order.reverse()
        self.app._toggle_settings()
        self.app._set_orientation(False)
        self.app._toggle_settings()
        from qt.app import BLOCK_NAMES

        self.assertEqual(self.app.docking.floating, {})
        self.assertEqual(self.app.block_order, list(BLOCK_NAMES))
        self.assertEqual(self.app.settings["floating_modules"], {})
        self.assertTrue(self.app.stats.isVisible())

    def test_landscape_docked_grip_floats_in_portrait_layout(self):
        self.app.landscape = True
        self.app._arrange_blocks()
        self.application.processEvents()
        self._float("graph", QPoint(300, 900))
        self.assertFalse(self.app.chart.landscape)
        self.app.docking.dock_module("graph")
        self.assertTrue(self.app.chart.landscape)

    def test_places_are_kept_between_runs(self):
        self._float("stats", QPoint(300, 400))
        # Inside the offscreen platform's 800 by 600 screen, so the place is not pulled back onto it
        self.app.window.move(100, 10)
        self.application.processEvents()
        self.app.docking.save_positions()
        self.saved_settings = dict(self.app.settings)
        self.app.window_hidden()
        restarted = self._start()
        restarted.docking.restore()
        self.assertEqual(restarted.window.pos(), QPoint(100, 10))
        self.assertTrue(restarted.docking.is_floating("stats"))
        self.assertEqual(restarted.docking.floating["stats"].pos(), QPoint(270, 388))


if __name__ == "__main__":
    unittest.main()
