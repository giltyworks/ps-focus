"""Floating modules in the Qt app: dragging them out by the grip, snapping, moving together, docking back, overlapping,
and keeping their places between runs. Runs on Qt's offscreen platform with temporary data"""

from __future__ import annotations

import os
from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:
    QApplication = None

from qt.docking import attached_panels, snap_position, snap_motion


class DockingRulesTests(unittest.TestCase):
    def test_panel_slides_along_side_without_jumping_between_corners(self):
        ys = [snap_position(115, y, 50, 40, [(0, 50, 100, 200)])[1] for y in range(80, 141)]
        self.assertEqual(ys, list(range(80, 141)))

    def test_snap_retains_edge_until_pulled_past_release_margin(self):
        neighbours = [(0, 50, 100, 200)]
        x, y, held = snap_motion(119, 90, 50, 40, neighbours)
        self.assertEqual((x, y), (100, 90))
        x, y, held = snap_motion(124, 91, 50, 40, neighbours, held=held)
        self.assertEqual((x, y), (100, 91))
        x, y, held = snap_motion(127, 92, 50, 40, neighbours, held=held)
        self.assertEqual((x, y), (127, 92))
        self.assertEqual(held, (None, None))

    def test_side_alignment_supports_top_bottom_and_internal_edges(self):
        neighbours = [(0, 0, 200, 600)]
        anchors = [(0, 200, 200, 400)]
        for y, expected in ((204, 200), (344, 340), (250, 250)):
            self.assertEqual(snap_position(210, y, 100, 60, neighbours, side_targets=anchors), (200, expected))

    def test_panel_slides_horizontally_below_an_edge(self):
        self.assertEqual(snap_position(70, 205, 50, 40, [(0, 0, 200, 200)]), (70, 200))

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
        for timer in (app.tick_timer, app.focus_timer, app.poll_timer, app.backup_timer):
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
        return block.mapToGlobal(block.title_rect().center())

    def _float(self, name, to):
        start = self._grip(name)
        self._drag(self.app.modules[name], start, start + QPoint(0, 10), to)
        self.assertTrue(self.app.docking.is_floating(name))
        return self.app.docking.floating[name]

    def test_grip_dragged_out_floats_the_module_and_the_window_closes_up(self):
        height = self.app.window.height()
        block = self.app.modules["stats"]
        grabbed = self._grip("stats") - block.mapToGlobal(QPoint(0, 0))
        panel = self._float("stats", QPoint(300, 400))
        self.assertTrue(panel.isVisible())
        self.assertTrue(self.app.stats.floating)
        self.assertIs(self.app.stats.parent(), panel)
        self.assertEqual(panel.pos(), QPoint(300, 400) - grabbed)
        self.assertNotIn(self.app.stats, self.app._shown_blocks())
        self.assertLess(self.app.window.height(), height)
        self.assertEqual(self.app.settings["floating_modules"], {"stats": [panel.x(), panel.y()]})

    def test_undocking_keeps_grab_point_and_next_move_is_continuous_for_every_block(self):
        for landscape in (False, True):
            for name in self.app.blocks_by_name():
                self.app.docking.dock_all()
                self.app.landscape = landscape
                self.app._arrange_blocks()
                self.application.processEvents()
                block = self.app.blocks_by_name()[name]
                offset = QPoint(100, block.title_rect().center().y())
                start = block.mapToGlobal(offset)
                self.app.docking.press(name, True, start)
                point = QPoint(2400, 1800)
                self.app.docking.drag(point)
                self.application.processEvents()
                panel = self.app.docking.floating[name]
                self.assertEqual(panel.pos()+offset, point, (landscape, name))
                before = panel.pos()
                self.app.docking.drag(point+QPoint(1, 1))
                self.application.processEvents()
                self.assertEqual(panel.pos(), before+QPoint(1, 1), (landscape, name))
                self.app.docking.release(point+QPoint(1, 1))

    def test_real_drag_slides_along_neighbour_in_both_orientations(self):
        for landscape in (False, True):
            self.app.docking.dock_all()
            self.app.landscape = landscape
            self.app._arrange_blocks()
            self.app.docking.float_module("calendar", QPoint(1000, 500))
            self.app.docking.float_module("graph", QPoint(1500, 600))
            target = self.app.docking.floating["calendar"]
            source = self.app.docking.floating["graph"]
            self.application.processEvents()
            start = source.pos() + QPoint(15, 15)
            with patch.object(self.app.docking, "_main_shown", return_value=False):
                self.app.docking.press("graph", True, start)
                for offset in range(60, 101):
                    raw = QPoint(target.x()+target.width()+15, target.y()+offset)
                    self.app.docking.drag(raw+QPoint(15, 15))
                    self.application.processEvents()
                    self.assertEqual(source.x(), target.x()+target.width())
                    self.assertEqual(source.y(), target.y()+offset)
                self.app.docking.release(raw+QPoint(15, 15))
                self.assertEqual(self.app.docking.snap_held, (None, None))

    def test_every_floating_block_highlights_during_drag_and_clears_on_release(self):
        for landscape in (False, True):
            self.app.docking.dock_all()
            self.app.landscape = landscape
            self.app._arrange_blocks()
            for name, block in self.app.blocks_by_name().items():
                self.app.docking.float_module(name, QPoint(1500, 800))
                self.application.processEvents()
                start = block.mapToGlobal(block.title_rect().center())
                with patch.object(self.app.docking, "_main_shown", return_value=False):
                    self._mouse(block, QEvent.Type.MouseButtonPress, start)
                    self._mouse(block, QEvent.Type.MouseMove, start+QPoint(40, 40))
                    self.assertEqual(block.border_color, "calendar_blue", name)
                    self._mouse(block, QEvent.Type.MouseButtonRelease, start+QPoint(40, 40))
                    self.assertEqual(block.border_color, "border", name)
                self.app.docking.dock_module(name)

    def test_grip_drag_inside_the_window_reorders_instead(self):
        calendar = self.app.modules["calendar"]
        target = self.app.today
        above = target.mapToGlobal(QPoint(target.width() // 2, 2))
        self._drag(calendar, self._grip("calendar"), self._grip("calendar") + QPoint(0, 10), above)
        self.assertFalse(self.app.docking.is_floating("calendar"))
        self.assertLess(self.app.block_order.index("calendar"), self.app.block_order.index("today"))

    def test_dropped_back_in_the_window_by_its_grip_docks_where_let_go(self):
        panel = self._float("graph", QPoint(300, 400))
        stats = self.app.modules["stats"]
        drop = stats.mapToGlobal(QPoint(stats.width() // 2, stats.height() - 2))
        block = self.app.modules["graph"]
        grip = block.mapToGlobal(block.title_rect().center())
        self._drag(block, grip, grip + QPoint(10, 0), drop)
        self.assertFalse(self.app.docking.is_floating("graph"))
        self.assertFalse(self.app.chart.floating)
        self.assertIn(self.app.chart, self.app._shown_blocks())
        # Dropped on the last module shown, the stats, it goes after them
        self.assertEqual(self.app.block_order.index("graph"), self.app.block_order.index("stats") + 1)
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
        grip = block.mapToGlobal(block.title_rect().center())
        offset = grip - panel.pos()
        # Let go with the panel's right edge 12 pixels short of the window's left edge
        aim = QPoint(left - panel.width() - 12, panel.y()) + offset
        self._drag(block, grip, grip + QPoint(10, 0), aim)
        self.assertEqual(panel.x() + panel.width(), left)

    def test_dragging_a_module_body_moves_the_window_with_the_panels_touching_it(self):
        panel = self._float("stats", QPoint(300, 400))
        left, top, _right, _bottom = self.app.docking.main_bounds()
        panel.move(left - panel.width(), top)
        loose = self._float("graph", QPoint(100, 700))
        loose_position = loose.pos()
        self.app.docking.main_last_bounds = self.app.docking.main_bounds()
        calendar = self.app.modules["calendar"]
        # The month's name under the title: neither the title nor anything to click
        start = calendar.mapToGlobal(QPoint(30, calendar.content_top + 8))
        self.assertIsNone(calendar.control_at(calendar.mapFromGlobal(start)))
        self.assertFalse(calendar.interactive_at(calendar.mapFromGlobal(start)))
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

    def test_body_drag_on_a_floating_panel_moves_its_group(self):
        # Floated apart first, then placed edge to edge to form a group.
        first = self._float("stats", QPoint(100, 50))
        second = self._float("graph", QPoint(700, 50))
        second.move(first.x() + first.width(), first.y())
        block = self.app.modules["stats"]
        # A line of the stats, under the title
        start = block.mapToGlobal(QPoint(20, block.content_top + 10))
        first_position = first.pos()
        self._drag(block, start, start + QPoint(0, 50))
        self.assertEqual(first.pos(), first_position + QPoint(0, 50))
        self.assertEqual(second.pos(), QPoint(first.x() + first.width(), first.y()))

    def test_grip_drag_pulls_one_panel_from_its_group_and_the_gap_closes(self):
        first = self._float("stats", QPoint(100, 500))
        first_position = first.pos()
        second = self._float("graph", QPoint(100, 100))
        third = self._float("calendar", QPoint(100, 700))
        second.move(first.x() + first.width(), first.y())
        third.move(second.x() + second.width(), first.y())
        block = self.app.modules["graph"]
        grip = block.mapToGlobal(block.title_rect().center())
        self._drag(block, grip, grip + QPoint(0, 10), grip + QPoint(0, 900))
        # The calendar slides left into the graph's slot; the stats stay
        self.assertEqual(third.x(), first.x() + first.width())
        self.assertEqual(first.pos(), first_position)

    def test_grip_drop_on_another_floating_panel_allows_overlap(self):
        first = self._float("stats", QPoint(200, 600))
        # Clear of the window's far end, where a panel let go would dock
        second = self._float("graph", QPoint(200, 1300))
        first_position, second_position = first.pos(), second.pos()
        block = self.app.modules["stats"]
        grip = block.mapToGlobal(block.title_rect().center())
        self._drag(block, grip, grip + QPoint(10, 0), grip + (second_position - first_position))
        self.assertEqual(first.pos(), second_position)
        self.assertEqual(second.pos(), second_position)

    def test_all_floating_blocks_can_overlap_without_swapping_or_reordering(self):
        for landscape in (False, True):
            for name in self.app.blocks_by_name():
                for target_name in self.app.blocks_by_name():
                    if name == target_name:
                        continue
                    self.app.docking.dock_all()
                    self.app.landscape = landscape
                    self.app._arrange_blocks()
                    self.app.docking.float_module(target_name, QPoint(1200, 800))
                    self.app.docking.float_module(name, QPoint(1700, 800))
                    self.application.processEvents()
                    source = self.app.docking.floating[name]
                    target = self.app.docking.floating[target_name]
                    target_position = target.pos()
                    order = self.app.block_order.copy()
                    block = self.app.blocks_by_name()[name]
                    grip = block.mapToGlobal(block.title_rect().center())
                    destination = grip + target_position - source.pos()
                    with patch.object(self.app.docking, "_main_shown", return_value=False):
                        self._drag(block, grip, destination)
                    self.assertEqual(source.pos(), target_position, (landscape, name, target_name))
                    self.assertEqual(target.pos(), target_position, (landscape, name, target_name))
                    self.assertEqual(self.app.block_order, order)

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
        original = self._float("stats", QPoint(300, 400)).pos()
        # Inside the offscreen platform's 800 by 600 screen, so the place is not pulled back onto it
        self.app.window.move(0, 0)
        self.application.processEvents()
        self.app.docking.save_positions()
        self.saved_settings = dict(self.app.settings)
        self.app.window_hidden()
        restarted = self._start()
        restarted.docking.restore()
        self.assertEqual(restarted.window.pos(), QPoint(0, 0))
        self.assertTrue(restarted.docking.is_floating("stats"))
        self.assertEqual(restarted.docking.floating["stats"].pos(), original)


    def _press_move(self, widget, start, *points):
        """Press and move without letting go, to look at the drag midway"""
        self._mouse(widget, QEvent.Type.MouseButtonPress, start)
        for point in points:
            self._mouse(widget, QEvent.Type.MouseMove, point)
        self.application.processEvents()

    def test_dragging_a_program_panel_moves_the_window_and_attached_panels(self):
        panel = self._float("stats", QPoint(300, 400))
        left, top, _right, _bottom = self.app.docking.main_bounds()
        panel.move(left - panel.width(), top)
        photoshop = self.app.today
        start = photoshop.mapToGlobal(QPoint(60, 40))
        window_position, panel_position = self.app.window.pos(), panel.pos()
        self._drag(photoshop, start, start + QPoint(-30, 25))
        self.assertEqual(self.app.window.pos(), window_position + QPoint(-30, 25))
        self.assertEqual(panel.pos(), panel_position + QPoint(-30, 25))

    def test_a_drag_whose_release_never_arrives_lets_go_of_the_mouse(self):
        graph = self.app.modules["graph"]
        start = graph.mapToGlobal(QPoint(60, graph.height() - 20))
        self._mouse(graph, QEvent.Type.MouseButtonPress, start)
        self._mouse(graph, QEvent.Type.MouseMove, start + QPoint(20, 0))
        self.assertIs(QWidget.mouseGrabber(), self.app.window)
        # Windows gave the release to another window; the mouse then moves on with the button up
        point = self.app.window.mapToGlobal(QPoint(30, 30))
        QApplication.sendEvent(self.app.window, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(QPoint(30, 30)), QPointF(point), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        self.assertIsNone(self.app.block_drag.mode)
        self.assertIsNone(QWidget.mouseGrabber())
        self.assertFalse(self.app.window.hasMouseTracking())

    def test_header_moves_the_window_except_where_it_is_clicked(self):
        header = self.app.header
        position = self.app.window.pos()
        # A spot on the row that is not the level, the account or the settings button
        spot = next(x for x in range(header.width() - 30, 0, -1) if not header.interactive_at(QPoint(x, header.height() // 2)))
        empty = header.mapToGlobal(QPoint(spot, header.height() // 2))
        self._drag(header, empty, empty + QPoint(20, 10))
        self.assertEqual(self.app.window.pos(), position + QPoint(20, 10))
        dots = header.mapToGlobal(QPoint(header.settings_area[0] + 5, header.settings_area[1] + 5))
        self._drag(header, dots, dots + QPoint(20, 10))
        self.assertEqual(self.app.window.pos(), position + QPoint(20, 10))

    def test_program_panel_title_reorders_inside_the_window(self):
        self.application.processEvents()
        photoshop = self.app.today
        title = photoshop.mapToGlobal(photoshop.title_rect().center())
        graph = self.app.modules["graph"]
        # Let go on the top of the graph, which comes after Friends
        self._drag(photoshop, title, title + QPoint(0, 10), graph.mapToGlobal(QPoint(50, 3)))
        self.assertEqual(self.app.docking.floating, {})
        self.assertLess(self.app.block_order.index("friends"), self.app.block_order.index("today"))

    def test_program_panel_floats_and_docks_like_a_module(self):
        photoshop = self.app.today
        title = photoshop.mapToGlobal(photoshop.title_rect().center())
        self._drag(photoshop, title, title + QPoint(0, 10), QPoint(300, 400))
        self.assertTrue(self.app.docking.is_floating("today"))
        self.assertTrue(photoshop.floating)
        self.assertIsNotNone(photoshop.dock_rect())
        self.assertNotIn(photoshop, self.app._shown_blocks())
        # The header stands alone now
        self.assertIsNone(self.app._anchor_panel())
        # Its figures keep counting while it floats
        self.app._track_and_refresh()
        self.assertIn("SESSIONS", photoshop.texts["sessions"].text)
        # Another program in front, its window takes that program's name
        with patch("qt.app.foreground_application", return_value="Krita"):
            self.app._track_and_refresh()
        self.assertEqual(self.app.docking.floating["today"].windowTitle(), "PS Focus - Krita")
        # The dock icon puts it back
        icon = photoshop.mapToGlobal(photoshop.dock_rect().center())
        self._mouse(photoshop, QEvent.Type.MouseButtonPress, icon)
        self._mouse(photoshop, QEvent.Type.MouseButtonRelease, icon)
        self.assertFalse(self.app.docking.is_floating("today"))
        self.assertIs(self.app._anchor_panel(), photoshop)

    def test_floating_program_panels_are_restored(self):
        self.app.docking.float_module("today", QPoint(150, 300))
        self.app.docking.save_positions()
        self.saved_settings = dict(self.app.settings)
        self.app.window_hidden()
        restarted = self._start()
        restarted.docking.restore()
        self.assertTrue(restarted.docking.is_floating("today"))
        self.assertEqual(restarted.docking.floating["today"].pos(), QPoint(150, 300))

    def test_a_lone_panel_over_the_window_makes_room_for_itself_and_docks_there(self):
        panel = self._float("stats", QPoint(200, 300))
        block = self.app.modules["stats"]
        start = block.mapToGlobal(QPoint(40, 60))
        photoshop = self.app.today
        photoshop_top = photoshop.mapTo(self.app.window, QPoint(0, 0)).y()
        over = photoshop.mapToGlobal(QPoint(100, 5))
        self._press_move(block, start, start + QPoint(10, 0), over)
        preview = self.app.docking.preview
        self.assertTrue(preview.isVisible())
        self.assertEqual(self.app.docking.dock_slot, self.app.docking._shown_names().index("today"))
        # The space is the module's own size, where the Photoshop panel was, which has moved down past it
        self.assertEqual(preview.size(), panel.size())
        self.assertEqual(preview.mapTo(self.app.window, QPoint(0, 0)).y(), photoshop_top)
        self.assertGreater(photoshop.mapTo(self.app.window, QPoint(0, 0)).y(), photoshop_top + preview.height())
        self.assertLess(panel.windowOpacity(), 1)
        # Moving within the space keeps it where it is
        self._mouse(block, QEvent.Type.MouseMove, preview.mapToGlobal(QPoint(50, preview.height() // 2)))
        self.assertEqual(self.app.docking.dock_slot, self.app.docking._shown_names().index("today"))
        self._mouse(block, QEvent.Type.MouseButtonRelease, preview.mapToGlobal(QPoint(50, preview.height() // 2)))
        self.assertFalse(preview.isVisible())
        self.assertFalse(self.app.docking.is_floating("stats"))
        self.assertEqual(self.app.block_order.index("stats") + 1, self.app.block_order.index("today"))
        self.assertEqual(self.app.stats.mapTo(self.app.window, QPoint(0, 0)).y(), photoshop_top)

    def test_moving_away_from_the_window_takes_the_space_back(self):
        self._float("stats", QPoint(200, 300))
        block = self.app.modules["stats"]
        height = self.app.window.height()
        start = block.mapToGlobal(QPoint(40, 60))
        over = self.app.today.mapToGlobal(QPoint(100, 5))
        self._press_move(block, start, start + QPoint(10, 0), over)
        self.assertGreater(self.app.window.height(), height)
        self._mouse(block, QEvent.Type.MouseMove, QPoint(100, 1300))
        self.assertFalse(self.app.docking.preview.isVisible())
        self.assertEqual(self.app.window.height(), height)
        self._mouse(block, QEvent.Type.MouseButtonRelease, QPoint(100, 1300))
        self.assertTrue(self.app.docking.is_floating("stats"))

    def test_let_go_just_below_the_window_docks_at_the_end(self):
        self._float("graph", QPoint(200, 300))
        block = self.app.modules["graph"]
        left, _top, _right, bottom = self.app.docking.main_bounds()
        start = block.mapToGlobal(QPoint(40, 60))
        offset = start - self.app.docking.floating["graph"].pos()
        # The panel's top 15 pixels under the window's bottom edge, lined up with it
        aim = QPoint(left, bottom + 15) + offset
        self._press_move(block, start, start + QPoint(10, 0), aim)
        self.assertEqual(self.app.docking.dock_slot, len(self.app.docking._shown_names()))
        self._mouse(block, QEvent.Type.MouseButtonRelease, aim)
        self.assertFalse(self.app.docking.is_floating("graph"))
        self.assertEqual(self.app._shown_blocks()[-1], self.app.chart)

    def test_in_landscape_let_go_just_right_of_the_window_docks_at_the_end(self):
        self.app.landscape = True
        self.app._arrange_blocks()
        self.application.processEvents()
        self._float("stats", QPoint(100, 1200))
        block = self.app.modules["stats"]
        _left, top, right, _bottom = self.app.docking.main_bounds()
        start = block.mapToGlobal(QPoint(40, 60))
        aim = QPoint(right + 10, top) + (start - self.app.docking.floating["stats"].pos())
        self._drag(block, start, start + QPoint(10, 0), aim)
        self.assertFalse(self.app.docking.is_floating("stats"))
        self.assertEqual(self.app._shown_blocks()[-1], self.app.stats)

    def test_a_group_of_panels_dragged_over_the_window_does_not_dock(self):
        first = self._float("stats", QPoint(100, 50))
        second = self._float("graph", QPoint(700, 50))
        second.move(first.x() + first.width(), first.y())
        block = self.app.modules["stats"]
        start = block.mapToGlobal(QPoint(40, 60))
        over = self.app.today.mapToGlobal(QPoint(100, 20))
        self._press_move(block, start, start + QPoint(10, 0), over)
        self.assertIsNone(self.app.docking.dock_slot)
        self.assertFalse(self.app.docking.preview.isVisible())
        self._mouse(block, QEvent.Type.MouseButtonRelease, over)
        self.assertTrue(self.app.docking.is_floating("stats"))
        self.assertTrue(self.app.docking.is_floating("graph"))

    def test_switching_to_landscape_keeps_the_full_width_on_later_layouts(self):
        self.app.landscape = True
        self.app._arrange_blocks()
        self.app._arrange_blocks()
        self.assertIsNone(self.app.landscape_width)
        self.assertEqual(self.app.window.width(), self.app.window.full_size()[0])

    def test_only_a_drag_of_the_edge_chooses_the_landscape_width(self):
        self.app.landscape = True
        self.app._arrange_blocks()
        window = self.app.window
        # A resize Windows applies late, as the Settings page's after leaving it, is not the user's choice
        window.resize(320, window.height())
        self.assertIsNone(self.app.landscape_width)
        window.user_resizing = True
        window.resize(400, window.height())
        self.assertEqual(self.app.landscape_width, 400)

    def test_floating_panels_turn_to_glass_away_from_the_mouse(self):
        from qt.docking import GLASS_MIN_ALPHA, glass_alpha

        self.assertEqual((glass_alpha(0), glass_alpha(100), glass_alpha("bad")), (255, GLASS_MIN_ALPHA, 255))
        self.app.settings["panel_transparency"] = 50
        with patch("qt.docking.QCursor.pos", return_value=QPoint(5, 5)):
            panel = self._float("stats", QPoint(300, 400))
            self.assertEqual(self.app.stats.glass_alpha, glass_alpha(50))
            self.assertTrue(panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertFalse(self.app.stats.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent))
        # The mouse on the panel makes it solid
        with patch("qt.docking.QCursor.pos", return_value=panel.geometry().center()):
            self.app.docking.update_glass("stats")
        self.assertEqual(self.app.stats.glass_alpha, 255)
        with patch("qt.docking.QCursor.pos", return_value=QPoint(5, 5)):
            # The slider sets how see-through, live; 0 is solid
            self.app._transparency_chosen(100, False)
            self.assertEqual(self.app.stats.glass_alpha, GLASS_MIN_ALPHA)
            self.app._transparency_chosen(0, True)
            self.assertEqual(self.app.stats.glass_alpha, 255)
            self.app._transparency_chosen(60, True)
        self.assertEqual(self.app.settings["panel_transparency"], 60)
        # Docked, a module takes the window's glass
        self.app.docking.dock_module("stats")
        self.assertEqual(self.app.stats.glass_alpha, self.app.window.glass_alpha)

    def test_main_window_turns_to_glass_away_from_the_mouse(self):
        from qt.docking import glass_alpha

        self.app.window.show()
        self.app.settings["panel_transparency"] = 100
        faded = glass_alpha(100)
        parts = lambda: (self.app.window.glass_alpha, self.app.header.glass_alpha, self.app.module_controls.glass_alpha,
                         self.app.window.title_bar.glass_alpha, self.app.calendar.glass_alpha)
        with patch("qt.docking.QCursor.pos", return_value=QPoint(5, 5)):
            self.app.update_glass()
            # Every background fades, the blocks' included; the window itself, and so its text, stays solid
            self.assertEqual(parts(), (faded,) * 5)
            self.assertEqual(self.app.window.windowOpacity(), 1.0)
            self.assertTrue(self.app.window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            # Settings open, it is solid
            self.app._toggle_settings()
            self.assertEqual(self.app.window.glass_alpha, 255)
            self.app._toggle_settings()
            self.assertEqual(self.app.window.glass_alpha, faded)
        with patch("qt.docking.QCursor.pos", return_value=self.app.window.frameGeometry().center()):
            self.app.update_glass()
        self.assertEqual(parts(), (255,) * 5)

    def test_glass_pictures_match_the_background_and_icons_have_no_square(self):
        from PySide6.QtGui import QColor
        from qt.icons import icon

        self.app.calendar.set_glass(100)
        self.app.calendar.refresh()
        # Pictures start from the panel as see-through as the module, and replace the background when drawn
        self.assertEqual(self.app.calendar.picture_fill().alpha(), 100)
        clear = icon("moon", 16, "")
        self.assertEqual(clear.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(icon("moon", 16, "#000000").pixelColor(0, 0), QColor("#000000"))
        self.app.calendar.set_glass(255)

    def test_title_shows_an_open_hand_and_program_names_brighten(self):
        calendar = self.app.modules["calendar"]
        calendar.update_cursor(calendar.title_rect().center())
        self.assertEqual(calendar.cursor().shape(), Qt.CursorShape.OpenHandCursor)
        photoshop = self.app.today
        photoshop._hover("title")
        self.assertTrue(photoshop.title_hovered)
        self.assertEqual(photoshop.cursor().shape(), Qt.CursorShape.OpenHandCursor)

    def test_snapped_windows_turn_solid_and_see_through_together(self):
        from qt.docking import glass_alpha

        self.app.window.show()
        self.app.settings["panel_transparency"] = 100
        attached = self._float("stats", QPoint(300, 400))
        left, top, _right, _bottom = self.app.docking.main_bounds()
        attached.move(left - attached.width(), top)
        apart = self._float("graph", QPoint(100, 1300))
        partner = self._float("calendar", QPoint(700, 1300))
        partner.move(apart.x() + apart.width(), apart.y())
        faded = glass_alpha(100)
        with patch("qt.docking.QCursor.pos", return_value=QPoint(5, 5)):
            self.app.update_glass()
        self.assertEqual((self.app.stats.glass_alpha, self.app.chart.glass_alpha, self.app.calendar.glass_alpha), (faded, faded, faded))
        # The mouse on the panel snapped to the window: the window turns solid with it; the other group stays glass
        with patch("qt.docking.QCursor.pos", return_value=attached.geometry().center()):
            self.app.update_glass()
        self.assertEqual(self.app.stats.glass_alpha, 255)
        self.assertEqual(self.app.window.glass_alpha, 255)
        self.assertEqual(self.app.chart.glass_alpha, faded)
        # The mouse on the window: the panel snapped to it turns solid too
        with patch("qt.docking.QCursor.pos", return_value=self.app.window.frameGeometry().center()):
            self.app.update_glass()
        self.assertEqual(self.app.stats.glass_alpha, 255)
        # The mouse on one of two snapped floating panels: both turn solid, the window fades
        with patch("qt.docking.QCursor.pos", return_value=apart.geometry().center()):
            self.app.update_glass()
        self.assertEqual((self.app.chart.glass_alpha, self.app.calendar.glass_alpha), (255, 255))
        self.assertEqual(self.app.window.glass_alpha, faded)
        self.assertEqual(self.app.stats.glass_alpha, faded)

    def test_window_positions_are_saved_without_a_google_upload(self):
        self.app.google_sync = unittest.mock.Mock()
        self.app.window.move(120, 0)
        self.app.docking.save_positions()
        self.app.google_sync.settings_changed.assert_not_called()
        self.assertEqual(self.app.settings["main_window_position"], [120, 0])
        self.app._period_chosen("Week")
        self.app.google_sync.settings_changed.assert_called_once()

    def test_floating_modules_keep_up_while_settings_is_open(self):
        self._float("graph", QPoint(100, 1300))
        self.app._toggle_settings()
        self.app.active = True
        with patch.object(self.app.chart, "refresh") as refresh, patch("qt.app.foreground_application", return_value="Photoshop"),                 patch("qt.app.user_is_active", return_value=True):
            self.app._track_and_refresh()
        refresh.assert_called()
        self.app._toggle_settings()

    def test_hovering_calendar_days_does_not_read_the_database(self):
        calendar = self.app.calendar
        calendar.refresh(force=True)
        with patch.object(self.app.store, "month_totals") as month_totals, patch.object(self.app.store, "calendar_streaks") as streaks:
            calendar._hover_day(date.today().replace(day=1))
            calendar._hover_day(None)
        month_totals.assert_not_called()
        streaks.assert_not_called()

    def test_resizing_the_window_leaves_snapped_panels_where_they_are(self):
        panel = self._float("stats", QPoint(300, 400))
        left, top, _right, bottom = self.app.docking.main_bounds()
        panel.move(left, bottom)
        self.app.docking.main_last_bounds = self.app.docking.main_bounds()
        position = panel.pos()
        # Dragged shorter from its top edge: the window's top moves, its size changes
        self.app.window.setGeometry(self.app.window.geometry().adjusted(0, 40, 0, 0))
        self.application.processEvents()
        self.assertEqual(panel.pos(), position)


if __name__ == "__main__":
    unittest.main()
