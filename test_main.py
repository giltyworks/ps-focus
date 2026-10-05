import importlib.util
import json
import math
import os
import queue
import re
import tempfile
import unittest
import uuid
import wave
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import main
from app_config import COLORS, DEFAULT_SETTINGS, FEEDBACK_UNLOCK_SECONDS, LEVEL_ANCHORS, LEVEL_CAP, LEVEL_HOURS, load_settings, user_level
from main import PSFocusApp
from rendering import render_award_badge, render_crescent_icon, render_flame_icon, render_level_badge, render_line_chart
from stat_lines import format_change, format_hours_minutes, medal_for_rank
from ui_celebration import FIREWORK_BURST_TIMES, FIREWORK_SPARKS
from windows_startup import SingleInstance, SizeLimits, apply_first_run_startup, migrate_legacy_app_data, refresh_startup_entry


class UserLevelTests(unittest.TestCase):
    ANCHORS = {1: 0, 10: 40, 25: 180, 50: 650, 75: 1350, 80: 1550, 85: 1800, 90: 2100, 92: 2250, 95: 2500, 97: 2725, 98: 2850, 99: 3000}

    def test_every_anchor_level_is_reached_at_exactly_its_hours(self):
        self.assertEqual(dict(LEVEL_ANCHORS), self.ANCHORS)
        for level, hours in self.ANCHORS.items():
            with self.subTest(level=level):
                self.assertEqual(LEVEL_HOURS[level - 1], hours)
                self.assertEqual(user_level(hours * 3600), level)
                if level > 1:
                    self.assertEqual(user_level(hours * 3600 - 1), level - 1)

    def test_hours_needed_rise_with_every_level(self):
        self.assertEqual(len(LEVEL_HOURS), 99)
        for lower, higher in zip(LEVEL_HOURS, LEVEL_HOURS[1:]):
            self.assertLess(lower, higher)
        levels = [user_level(hours * 3600) for hours in range(0, 3200)]
        self.assertEqual(levels, sorted(levels))
        self.assertEqual(set(levels), set(range(1, 100)))

    def test_level_starts_at_one_and_is_capped_at_ninety_nine(self):
        self.assertEqual(user_level(0), 1)
        self.assertEqual(user_level(-50), 1)
        self.assertEqual(user_level(3000 * 3600), 99)
        self.assertEqual(user_level(50000 * 3600), 99)
        self.assertEqual(LEVEL_CAP, 99)

    def test_level_curve_cannot_be_changed_from_the_settings_file(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            settings_path.write_text(json.dumps({"LEVEL_ANCHORS": [[1, 0], [99, 1]], "level": 99, "LEVEL_HOURS": [0]}), encoding="utf-8")
            with patch("app_config.SETTINGS_PATH", settings_path):
                load_settings()
                self.assertEqual(user_level(1 * 3600), 1)
                self.assertEqual(user_level(40 * 3600), 10)
        self.assertIsInstance(LEVEL_ANCHORS, tuple)
        self.assertIsInstance(LEVEL_HOURS, tuple)

    def test_settings_file_that_is_damaged_or_not_a_set_of_settings_gives_the_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            with patch("app_config.SETTINGS_PATH", settings_path):
                self.assertEqual(load_settings(), DEFAULT_SETTINGS)
                for content in ("", "{broken", "[1, 2, 3]", '"text"', "null", "7"):
                    with self.subTest(content=content):
                        settings_path.write_text(content, encoding="utf-8")
                        self.assertEqual(load_settings(), DEFAULT_SETTINGS)
                settings_path.write_text(json.dumps({"period": "Week"}), encoding="utf-8")
                self.assertEqual(load_settings()["period"], "Week")

    def test_calendar_cannot_be_stepped_past_the_years_it_can_show(self):
        app = PSFocusApp.__new__(PSFocusApp)
        for view, start, offset in (("Month", date(1, 1, 1), -1), ("Year", date(1, 6, 1), -1), ("Month", date(9998, 12, 1), 1), ("Year", date(9998, 3, 1), 1)):
            with self.subTest(view=view, start=start), patch.object(app, "_calendar_period_changed") as changed:
                app.calendar_view, app.calendar_month = view, start
                app._shift_calendar_month(offset)
                self.assertEqual(app.calendar_month, start)
                changed.assert_not_called()
        with patch.object(app, "_calendar_period_changed") as changed:
            app.calendar_view, app.calendar_month = "Month", date(2026, 12, 1)
            app._shift_calendar_month(1)
            self.assertEqual(app.calendar_month, date(2027, 1, 1))
            changed.assert_called_once()

class FirstRunStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app_data = Path(self.temporary_directory.name) / "PS Focus"
        self.settings_path = self.app_data / "settings.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _apply(self, **set_startup_behaviour):
        settings = DEFAULT_SETTINGS.copy()
        with patch("app_config.APP_DATA", self.app_data), patch("app_config.SETTINGS_PATH", self.settings_path), patch(
            "windows_startup.set_startup", **set_startup_behaviour
        ) as set_startup:
            apply_first_run_startup(settings)
        return set_startup, json.loads(self.settings_path.read_text(encoding="utf-8"))

    def test_new_installation_starts_with_windows_minimized(self):
        set_startup, saved = self._apply()

        set_startup.assert_called_once_with(True, True)
        self.assertTrue(saved["launch_on_startup"])
        self.assertTrue(saved["start_minimized"])

    def test_installer_choice_not_to_start_with_windows_is_kept(self):
        # The settings file the installer writes when its Start with Windows box is unticked
        script = (Path(__file__).resolve().parent / "installer" / "PS Focus.iss").read_text(encoding="utf-8")
        written = re.search(r"settings\.json'\), '([^']+)'", script).group(1)
        self.app_data.mkdir(parents=True)
        self.settings_path.write_text(written, encoding="utf-8")
        with patch("app_config.SETTINGS_PATH", self.settings_path):
            settings = load_settings()

        self.assertFalse(settings["launch_on_startup"])
        self.assertEqual({key: value for key, value in settings.items() if key != "launch_on_startup"},
                         {key: value for key, value in DEFAULT_SETTINGS.items() if key != "launch_on_startup"})
        with patch("windows_startup.sys.frozen", True, create=True), patch("windows_startup.set_startup") as set_startup:
            refresh_startup_entry(settings)
        set_startup.assert_not_called()

    def test_startup_setting_is_left_off_when_windows_refuses_the_entry(self):
        _, saved = self._apply(side_effect=OSError("registry unavailable"))

        self.assertFalse(saved["launch_on_startup"])


class HeaderTextTests(unittest.TestCase):
    def test_account_text_is_kept_to_one_line_by_shortening_it(self):
        # A stand-in font in which every character is seven pixels wide
        font = Mock()
        font.measure.side_effect = lambda text: 7 * len(text)

        self.assertEqual(PSFocusApp._fit_header_text("Local only", font, 70), "Local only")
        shortened = PSFocusApp._fit_header_text("Settings backed up to Google Drive", font, 140)
        self.assertEqual(shortened, "Settings backed up…")
        self.assertLessEqual(font.measure(shortened), 140)
        self.assertEqual(PSFocusApp._fit_header_text("anything", font, 0), "…")

    def test_header_height_does_not_depend_on_what_it_shows(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.font_account = Mock()
        app.font_account.metrics.return_value = 20
        self.assertEqual(app._header_height(), 28)


class StartupRefreshTests(unittest.TestCase):
    def test_packaged_app_points_an_enabled_entry_at_itself(self):
        settings = {"launch_on_startup": True, "start_minimized": False}
        with patch("windows_startup.sys.frozen", True, create=True), patch("windows_startup.set_startup") as set_startup:
            refresh_startup_entry(settings)
        set_startup.assert_called_once_with(True, False)

    def test_source_runs_and_disabled_entries_are_left_alone(self):
        with patch("windows_startup.set_startup") as set_startup:
            refresh_startup_entry({"launch_on_startup": True})
            with patch("windows_startup.sys.frozen", True, create=True):
                refresh_startup_entry({"launch_on_startup": False})
        set_startup.assert_not_called()


class CelebrationTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.root = Mock()
        self.app.fireworks_window = None
        self.app.fireworks_geometry = ""
        self.app.settings = {"disable_fanfare_sound": False}

    def _place_window(self, x, y, width=376, height=215):
        self.app.root.winfo_rootx.return_value = x
        self.app.root.winfo_rooty.return_value = y
        self.app.root.winfo_width.return_value = width
        self.app.root.winfo_height.return_value = height

    def test_fireworks_follow_the_window_when_it_is_moved_or_resized(self):
        overlay = self.app.fireworks_window = Mock()
        self._place_window(3062, 31)
        self.app._fit_fireworks_to_window()
        self.app._fit_fireworks_to_window()
        overlay.geometry.assert_called_once_with("376x215+3062+31")

        self._place_window(1200, 400)
        self.app._fit_fireworks_to_window()
        overlay.geometry.assert_called_with("376x215+1200+400")

        self._place_window(1200, 400, height=504)
        self.app._fit_fireworks_to_window()
        overlay.geometry.assert_called_with("376x504+1200+400")

    def test_fireworks_stop_if_the_window_is_hidden_mid_show(self):
        overlay = self.app.fireworks_window = Mock()
        self._place_window(0, 0)
        self.app.root.winfo_viewable.return_value = False
        with patch("ui_celebration.time.monotonic", return_value=100.1):
            self.app._animate_fireworks(Mock(), [], 100.0, 100.08)

        overlay.destroy.assert_called_once()
        self.assertIsNone(self.app.fireworks_window)
        self.app.root.after.assert_not_called()

    def test_fanfare_sound_can_be_disabled_while_fireworks_still_play(self):
        self.app.settings["disable_fanfare_sound"] = True
        with patch("winsound.PlaySound") as play, patch.object(self.app, "_launch_fireworks") as launch:
            self.app._celebrate()

        play.assert_not_called()
        launch.assert_called_once()

    def test_celebration_plays_the_fanfare_and_launches_fireworks(self):
        with patch("winsound.PlaySound") as play, patch.object(self.app, "_launch_fireworks") as launch:
            self.app._celebrate()

        launch.assert_called_once()
        sound_path = Path(play.call_args.args[0])
        self.assertEqual(sound_path.name, "celebration.wav")
        with wave.open(str(sound_path)) as sound:
            self.assertGreater(sound.getnframes() / sound.getframerate(), 1.0)

    def test_firework_sounds_are_timed_to_the_bursts_on_screen(self):
        generator_path = Path(__file__).resolve().parent / "assets" / "sounds" / "make_celebration.py"
        specification = importlib.util.spec_from_file_location("make_celebration", generator_path)
        generator = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(generator)

        self.assertEqual(generator.FIREWORK_BURST_TIMES, FIREWORK_BURST_TIMES)

    def test_sound_starts_after_the_fireworks_and_is_not_restarted_mid_show(self):
        order = []
        with patch("winsound.PlaySound", side_effect=lambda *_arguments: order.append("sound")) as play, patch.object(
            self.app, "_launch_fireworks", side_effect=lambda: order.append("fireworks")
        ):
            self.app._celebrate()
            self.assertEqual(order, ["fireworks", "sound"])

            self.app.fireworks_window = Mock()
            self.app._celebrate()

        play.assert_called_once()

    def test_celebration_plays_by_itself_when_the_level_goes_up(self):
        self.app.celebrated_level = None
        with patch.object(self.app, "_celebrate") as celebrate:
            # The level found at launch is only the starting point
            self.app._celebrate_level_up(4)
            self.app._celebrate_level_up(4)
            celebrate.assert_not_called()

            self.app._celebrate_level_up(5)
            celebrate.assert_called_once()

            # Staying level, or dropping after history is removed, is nothing to celebrate
            self.app._celebrate_level_up(5)
            self.app._celebrate_level_up(3)
            celebrate.assert_called_once()

            self.app._celebrate_level_up(4)
            self.assertEqual(celebrate.call_count, 2)

    def test_only_the_sound_plays_while_the_window_is_hidden(self):
        self.app.root.winfo_viewable.return_value = False
        with patch("winsound.PlaySound") as play, patch.object(self.app, "_launch_fireworks") as launch:
            self.app._celebrate()

        launch.assert_not_called()
        play.assert_called_once()

    def test_fireworks_still_play_when_sound_is_unavailable(self):
        with patch("winsound.PlaySound", side_effect=RuntimeError("no audio device")), patch.object(self.app, "_launch_fireworks") as launch:
            self.app._celebrate()

        launch.assert_called_once()

    def test_a_second_press_does_not_stack_another_fireworks_overlay(self):
        self.app.fireworks_window = Mock()
        with patch("ui_celebration.tk.Toplevel") as create_overlay:
            self.app._launch_fireworks()

        create_overlay.assert_not_called()

    def test_fireworks_overlay_covers_exactly_the_window(self):
        self.app.root.winfo_width.return_value = 376
        self.app.root.winfo_height.return_value = 61
        self.app.root.winfo_rootx.return_value = 3062
        self.app.root.winfo_rooty.return_value = 31
        self.app.level_badge = Mock()
        self.app.level_badge.winfo_rootx.return_value = 3100
        self.app.level_badge.winfo_rooty.return_value = 33
        self.app.level_badge.winfo_width.return_value = 26
        self.app.level_badge.winfo_height.return_value = 26
        with patch("ui_celebration.tk.Toplevel") as create_overlay, patch("ui_celebration.tk.Canvas"), patch.object(
            self.app, "_animate_fireworks"
        ) as animate:
            self.app._launch_fireworks()

        create_overlay.return_value.geometry.assert_called_once_with("376x61+3062+31")
        sparks = animate.call_args.args[1]
        self.assertEqual(len(sparks), len(FIREWORK_BURST_TIMES) * FIREWORK_SPARKS)
        # The first burst starts on the level badge, and every burst starts inside the window
        self.assertEqual((sparks[0]["x"], sparks[0]["y"]), (51.0, 15.0))
        for spark in sparks:
            self.assertTrue(0 <= spark["x"] <= 376 and 0 <= spark["y"] <= 61)

    def test_bursts_are_placed_apart_from_each_other(self):
        self.app.root.winfo_width.return_value = 376
        self.app.root.winfo_height.return_value = 600
        self.app.root.winfo_rootx.return_value = 0
        self.app.root.winfo_rooty.return_value = 0
        self.app.level_badge = Mock()
        self.app.level_badge.winfo_rootx.return_value = 38
        self.app.level_badge.winfo_rooty.return_value = 2
        self.app.level_badge.winfo_width.return_value = 26
        self.app.level_badge.winfo_height.return_value = 26
        closest = []
        for _ in range(30):
            self.app.fireworks_window = None
            with patch("ui_celebration.tk.Toplevel"), patch("ui_celebration.tk.Canvas"), patch.object(
                self.app, "_animate_fireworks"
            ) as animate:
                self.app._launch_fireworks()
            sparks = animate.call_args.args[1]
            centers = [(sparks[index]["x"], sparks[index]["y"]) for index in range(0, len(sparks), FIREWORK_SPARKS)]
            closest.append(min(math.dist(a, b) for index, a in enumerate(centers) for b in centers[index + 1:]))

        # Measured over 1,500 shows of seven bursts: purely random placement averages 42 px between the closest
        # pair and sometimes puts two on the same spot, while this placement averages 113 px and never fell below 69
        self.assertGreater(min(closest), 50)
        self.assertGreater(sum(closest) / len(closest), 90)

    def test_sparks_wait_for_their_burst_and_the_overlay_closes_when_the_show_ends(self):
        overlay = self.app.fireworks_window = Mock()
        canvas = Mock()
        early = {"born": 0.0, "x": 10.0, "y": 10.0, "vx": 50.0, "vy": 0.0, "color": "#f94144", "item": 1}
        late = {"born": 0.5, "x": 80.0, "y": 20.0, "vx": 50.0, "vy": 0.0, "color": "#4d96ff", "item": 2}
        with patch("ui_celebration.time.monotonic", return_value=100.1):
            self.app._animate_fireworks(canvas, [early, late], 100.0, 100.08)
            self.assertGreater(early["x"], 10.0)
            self.assertEqual(late["x"], 80.0)
            self.assertIsNotNone(self.app.fireworks_window)
            self.app.root.after.assert_called_once()
            self.app._animate_fireworks(canvas, [early, late], 90.0, 100.08)

        overlay.destroy.assert_called_once()
        self.assertIsNone(self.app.fireworks_window)


class AwardBadgeTests(unittest.TestCase):
    def test_award_badge_is_one_flat_gold_with_a_disc_above_two_ribbon_tails(self):
        background, gold = (16, 19, 21), (240, 195, 60)
        badge = render_award_badge(16, "#101315")
        self.assertEqual(badge.size, (16, 16))
        self.assertEqual(badge.getpixel((0, 0)), background)

        # The disc and both ribbons are exactly the same gold
        for x, y in ((8, 4), (5, 5), (10, 2), (7, 8), (4, 12), (11, 13)):
            self.assertEqual(badge.getpixel((x, y)), gold, (x, y))
        # A darker strip separates the disc from the ribbons, and the ribbons have space between them
        self.assertLess(badge.getpixel((7, 10))[0], 200)
        self.assertEqual(badge.getpixel((8, 12)), background)
        # The disc is wider than both ribbons together are tall: it is the larger part of the badge
        disc_width = sum(1 for x in range(16) if badge.getpixel((x, 5)) == gold)
        ribbon_height = sum(1 for y in range(10, 16) if badge.getpixel((4, y)) == gold)
        self.assertGreater(disc_width, 2 * ribbon_height)

        # No second colour anywhere: every pixel lies on the straight blend from background to the one gold
        for x in range(16):
            for y in range(16):
                red, green, blue = badge.getpixel((x, y))
                share = (red - background[0]) / (gold[0] - background[0])
                self.assertTrue(0 <= share <= 1, (x, y))
                self.assertLessEqual(abs(background[1] + share * (gold[1] - background[1]) - green), 2, (x, y))
                self.assertLessEqual(abs(background[2] + share * (gold[2] - background[2]) - blue), 2, (x, y))


class StreakIconTests(unittest.TestCase):
    BACKGROUND = (25, 30, 32)

    def _only_one_colour(self, icon, color):
        # Every pixel lies on the straight blend from the background to the one colour: flat, like the award badge
        for x in range(icon.width):
            for y in range(icon.height):
                pixel = icon.getpixel((x, y))
                # Measured on the channel that changes most, where whole-number rounding matters least
                widest = max(range(3), key=lambda channel: abs(color[channel] - self.BACKGROUND[channel]))
                share = (pixel[widest] - self.BACKGROUND[widest]) / (color[widest] - self.BACKGROUND[widest])
                self.assertTrue(-0.02 <= share <= 1.02, (x, y))
                for channel in range(3):
                    expected = self.BACKGROUND[channel] + share * (color[channel] - self.BACKGROUND[channel])
                    self.assertLessEqual(abs(expected - pixel[channel]), 2, (x, y))

    def test_flame_is_one_flat_orange_and_comes_to_a_point(self):
        orange = (242, 140, 40)
        flame = render_flame_icon(14, "#191e20")
        self.assertEqual(flame.size, (14, 14))
        self._only_one_colour(flame, orange)
        widths = [sum(1 for x in range(14) if flame.getpixel((x, y)) == orange) for y in range(14)]
        # Narrow at the tip, wide in the body
        self.assertLess(max(widths[:3]), 3)
        self.assertGreaterEqual(max(widths[7:12]), 8)

    def test_crescent_is_one_flat_blue_with_its_inside_cut_away(self):
        blue = tuple(int(COLORS["calendar_blue"][index:index + 2], 16) for index in (1, 3, 5))
        crescent = render_crescent_icon(14, "#191e20")
        self.assertEqual(crescent.size, (14, 14))
        self._only_one_colour(crescent, blue)
        # Solid on the left, hollowed out towards the upper right where a full disc would be filled
        self.assertEqual(crescent.getpixel((2, 7)), blue)
        self.assertEqual(crescent.getpixel((9, 5)), self.BACKGROUND)


class CalendarDayClickTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        # Two days that can be opened, as the calendar records them when it draws: left, top, right, bottom, day
        self.app.calendar_day_boxes = [(30, 20, 45, 30, date(2026, 3, 17)), (45, 20, 60, 30, date(2026, 3, 18))]

    def _click(self, x, y):
        with patch.object(self.app, "_open_day_overview") as open_overview:
            self.app._calendar_day_clicked(Mock(x=x, y=y))
        return open_overview

    def test_clicking_a_day_opens_that_day(self):
        self._click(40, 25).assert_called_once_with(date(2026, 3, 17))
        self._click(45, 20).assert_called_once_with(date(2026, 3, 18))

    def test_clicking_elsewhere_or_on_a_future_day_opens_nothing(self):
        # Future days are drawn but not recorded as openable; the title, legend and gaps are not days at all
        for point in ((10, 25), (40, 31), (60, 25), (40, 5)):
            with self.subTest(point=point):
                self._click(*point).assert_not_called()

    def test_year_view_squares_can_be_hit_a_pixel_outside_their_edge(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.calendar_surface = Mock()
        # Rounded cells are pictures, which need a window; only where the squares go matters here
        app._draw_cell = Mock()
        app.calendar_day_boxes = []
        with patch("ui_calendar.calendar.monthcalendar", return_value=[[1, 2, 0, 0, 0, 0, 0]]):
            app._draw_year(top=64, width=350, year=2026, active_days=(frozenset(),) * 12, today=date(2026, 1, 1))

        # January is centred in the first third of the width; its first square is 13 by 8, 24 down from the top
        self.assertEqual(app.calendar_day_boxes, [(5, 87, 20, 97, date(2026, 1, 1))])
        self.assertEqual(app._calendar_day_at(Mock(x=5, y=87)), date(2026, 1, 1))
        self.assertIsNone(app._calendar_day_at(Mock(x=20, y=90)))


class WindowRefitTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.root = Mock()
        self.app.view = "Overview"
        self.app.fitted_content_height = None

    def test_window_is_refitted_only_when_the_content_height_changes(self):
        with patch.object(self.app, "_resize_to_content") as resize:
            self.app.root.winfo_reqheight.return_value = 781
            self.app._refit_if_content_changed()
            self.app._refit_if_content_changed()
            # The first reading is only a starting point, and an unchanged height leaves a hand-sized window alone
            resize.assert_not_called()

            self.app.root.winfo_reqheight.return_value = 827
            self.app._refit_if_content_changed()
            resize.assert_called_once_with(fit=True)

            self.app._refit_if_content_changed()
            resize.assert_called_once()

    def test_settings_page_is_not_refitted(self):
        self.app.view = "Settings"
        self.app.fitted_content_height = 781
        self.app.root.winfo_reqheight.return_value = 900
        with patch.object(self.app, "_resize_to_content") as resize:
            self.app._refit_if_content_changed()

        resize.assert_not_called()
        self.assertEqual(self.app.fitted_content_height, 781)


class StatsSessionSummaryTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.store = Mock()
        self.app.calendar_view = "Month"

    def test_no_sessions_message_is_shown_only_when_nothing_was_tracked(self):
        self.app.store.total_for_range.return_value = 0
        self.assertEqual(self.app._no_sessions_text(date(2026, 10, 1), date(2026, 10, 31)), "No sessions for this period")

    def test_tracked_time_without_a_full_session_is_reported_instead(self):
        self.app.store.total_for_range.return_value = 4 * 60 + 12
        self.assertEqual(
            self.app._no_sessions_text(date(2026, 10, 1), date(2026, 10, 31)),
            "4m tracked in October · no day reached 15m",
        )
        self.app.calendar_view = "Year"
        self.assertEqual(
            self.app._no_sessions_text(date(2026, 1, 1), date(2026, 12, 31)),
            "4m tracked in 2026 · no day reached 15m",
        )


class AverageChangeTests(unittest.TestCase):
    def test_change_in_an_average_is_signed_and_rounded_to_minutes(self):
        self.assertEqual(format_change(24 * 60), "+24m")
        self.assertEqual(format_change(-12 * 60 - 20), "-12m")
        self.assertEqual(format_change(65 * 60), "+1h 05m")
        self.assertEqual(format_change(-2 * 3600), "-2h 00m")
        self.assertEqual(format_change(20), "same")
        self.assertEqual(format_change(0), "same")

    def test_medal_follows_the_weeks_rank(self):
        for rank, medal in ((1, "gold"), (10, "gold"), (11, "silver"), (25, "silver"), (26, "bronze"), (50, "bronze"), (51, ""), (None, "")):
            with self.subTest(rank=rank):
                self.assertEqual(medal_for_rank(rank), medal)

    def test_stats_rows_show_a_medal_and_rank_only_for_a_top_week(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.store = Mock()
        app.store.total_for_range.return_value = 5 * 3600
        app.store.rolling_daily_average.return_value = 3600
        app.store.best_weekday_average.return_value = None
        app.store.longest_session.return_value = None
        app.store.best_start_time.return_value = ("20:30", 9)
        app.store.week_rank.return_value = 8

        lines = app._stat_figure_lines()
        self.assertEqual((lines[0].label, lines[0].value, lines[0].medal), ("This week", "5h 00m", "gold"))
        self.assertEqual(lines[1].value, "top 8% of your weeks")
        self.assertEqual((lines[-1].label, lines[-1].value, lines[-1].note), ("Best start time", "8:30 PM", "⭐ 9"))

        app.store.week_rank.return_value = 70
        lines = app._stat_figure_lines()
        self.assertEqual(lines[0].medal, "")
        self.assertNotIn("your weeks", " ".join(line.value for line in lines))

    def test_session_summary_names_the_period_the_calendar_shows(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.store = Mock()
        app.calendar_view, app.calendar_month = "Month", date(2026, 9, 1)
        app.store.qualifying_sessions.return_value = [(date(2026, 9, 30), "10:20", 3000), (date(2026, 9, 29), "20:30", 2100)]

        (line,) = app._session_summary_lines()
        self.assertEqual((line.label, line.value), ("2 sessions in September", "avg start 3:25 PM"))

    def test_week_total_and_best_day_durations_leave_out_seconds(self):
        self.assertEqual(format_hours_minutes(14 * 3600 + 32 * 60 + 20), "14h 32m")
        self.assertEqual(format_hours_minutes(2 * 3600 + 5 * 60), "2h 05m")
        self.assertEqual(format_hours_minutes(32 * 60), "32m")
        self.assertEqual(format_hours_minutes(0), "0m")


class TickTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.root = Mock()
        self.app.store = Mock()
        self.app.results = queue.Queue()
        self.app.last_tick_time = 0.0
        self.app.unrecorded_active_seconds = 0.0
        self.app.active = True
        self.app.instance = None
        self.app.tray_icon = None
        self.app.tray_thread = None

    def test_tracked_time_follows_real_time_when_ticks_run_late(self):
        # Fifty ticks arriving every 1.02 seconds span 51 seconds of real time
        tick_times = [round(1.02 * tick, 2) for tick in range(1, 51)]
        with patch("time.monotonic", side_effect=tick_times):
            for _ in tick_times:
                self.app._credit_active_time("Photoshop")

        self.assertEqual(self.app.store.record_active_second.call_count, 51)
        self.assertEqual(self.app.store.record_active_second.call_args.args[1], "Photoshop")

    def test_a_long_gap_such_as_sleep_is_not_counted_as_activity(self):
        with patch("time.monotonic", return_value=3600.0):
            self.app._credit_active_time("Photoshop")

        self.assertEqual(self.app.store.record_active_second.call_count, 2)

    def test_inactive_ticks_record_nothing(self):
        self.app.active = False
        with patch("time.monotonic", side_effect=[1.0, 2.0, 3.0]):
            for _ in range(3):
                self.app._credit_active_time(None)

        self.app.store.record_active_second.assert_not_called()
        self.assertEqual(self.app.last_tick_time, 3.0)

    def test_tick_is_rescheduled_even_when_an_update_fails(self):
        with patch.object(self.app, "_track_and_refresh", side_effect=RuntimeError("database is locked")):
            with self.assertRaises(RuntimeError):
                self.app._tick()

        self.app.root.after.assert_called_once_with(1000, self.app._tick)

    def test_result_polling_continues_after_a_handler_fails(self):
        self.app.results.put(("drive_backup", True, ""))
        with patch.object(self.app, "_backup_activity_now", side_effect=RuntimeError("backup failed")):
            with self.assertRaises(RuntimeError):
                self.app._poll_results()

        self.app.root.after.assert_called_once_with(150, self.app._poll_results)

    def test_starting_the_app_again_brings_up_the_running_copys_window(self):
        self.app.instance = Mock()
        self.app.instance.show_requested.side_effect = [True, False]
        with patch.object(self.app, "_restore_from_tray") as restore:
            self.app._poll_results()
            self.app._poll_results()

        restore.assert_called_once_with()

    def test_the_installers_request_to_close_closes_the_app(self):
        self.app.instance = Mock()
        self.app.instance.show_requested.return_value = False
        self.app.instance.exit_requested.return_value = True
        self.app._poll_results()

        self.app.root.after.assert_any_call(0, self.app._close)

    def test_exit_chosen_in_the_tray_is_carried_out_on_the_main_thread(self):
        # The tray calls this on its own thread, where the database may not be touched
        self.app._exit(Mock(), Mock())

        self.app.root.after.assert_called_once_with(0, self.app._close)
        self.app.store.close.assert_not_called()

    def test_closing_takes_a_final_backup_and_ends_even_if_the_backup_fails(self):
        self.app.store.create_local_backups.side_effect = OSError("folder unavailable")
        with patch("main.threading.Timer") as watchdog:
            self.app._close()

        self.app.store.create_local_backups.assert_called_once_with()
        self.app.store.close.assert_called_once_with()
        self.app.root.destroy.assert_called_once_with()
        # A stalled close is cut short rather than leaving a hidden copy running
        self.assertEqual(watchdog.call_args.args[0], main.EXIT_TIMEOUT_SECONDS)
        watchdog.return_value.start.assert_called_once_with()

    def test_closing_twice_closes_once(self):
        with patch("main.threading.Timer"):
            self.app._close()
            self.app._close()

        self.app.store.close.assert_called_once_with()
        self.app.root.destroy.assert_called_once_with()

    def test_windows_closing_the_app_closes_it_while_the_x_only_hides_it(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.root = Mock()
        with patch.object(app, "_set_title_bar_colors"), patch.object(app, "_set_window_icon"), patch("main.tkfont.Font"):
            app._configure_window()

        protocols = {call.args[0]: call.args[1] for call in app.root.protocol.call_args_list}
        self.assertEqual(protocols["WM_DELETE_WINDOW"], app._hide_to_tray)
        self.assertEqual(protocols["WM_SAVE_YOURSELF"], app._exit)

    def test_modules_are_brought_up_to_date_when_the_window_is_shown_again(self):
        self.app.view = "Overview"
        with patch.object(self.app, "_refresh_activity_views") as refresh:
            self.app._window_shown(Mock(widget=Mock()))
            refresh.assert_not_called()
            self.app._window_shown(Mock(widget=self.app.root))
            refresh.assert_called_once_with()
            self.app.view = "Settings"
            self.app._window_shown(Mock(widget=self.app.root))
            refresh.assert_called_once_with()

    def test_nothing_is_redrawn_while_the_window_is_hidden(self):
        app = self.app
        app.settings = {"tracking_enabled": True}
        app.view = "Overview"
        app.module_vars = {name: Mock(get=Mock(return_value=True)) for name in ("graph", "calendar", "stats")}
        app.calendar_last_refresh = app.stats_last_refresh = app.chart_last_drawn_day = None
        labels = ("application_totals", "application_two_week_labels", "application_session_labels", "application_record_hours_labels")
        for name in labels + ("application_status_labels", "application_last_session_labels"):
            setattr(app, name, {program: Mock() for program in main.PROGRAM_PANEL_SETTINGS})
        for query in ("total_for_day", "total_for_range", "lifetime_sessions", "total_seconds"):
            getattr(app.store, query).return_value = 0
        app.store.last_recorded_day.return_value = None
        redraws = ("_draw_chart", "_draw_stats", "_schedule_calendar_refresh")
        others = ("_draw_progress_indicator", "_draw_level_badge", "_celebrate_level_up", "_set_feedback_unlocked")
        with patch("main.foreground_application", return_value="Photoshop"), patch("main.user_is_active", return_value=True), patch(
            "time.monotonic", side_effect=[1.0, 2.0]
        ):
            patches = {name: patch.object(app, name) for name in redraws + others}
            mocks = {name: patcher.start() for name, patcher in patches.items()}
            try:
                app.root.winfo_viewable.return_value = False
                app._track_and_refresh()
                # Time is still counted
                app.store.record_active_second.assert_called()
                for name in redraws:
                    mocks[name].assert_not_called()
                app.root.winfo_viewable.return_value = True
                app._track_and_refresh()
                for name in redraws:
                    mocks[name].assert_called_once()
            finally:
                for patcher in patches.values():
                    patcher.stop()


class ProgramPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.settings = DEFAULT_SETTINGS.copy()
        self.app.settings["program_panels_chosen"] = []
        self.app.setting_vars = {key: Mock() for key in main.PROGRAM_PANEL_SETTINGS.values()}
        self.app.checkbox_indicators = {key: Mock() for key in main.PROGRAM_PANEL_SETTINGS.values()}
        for name in ("_save_settings", "_update_application_panels", "_draw_square_indicator"):
            setattr(self.app, name, Mock())

    def test_time_is_counted_in_a_program_whose_panel_is_hidden(self):
        app = self.app
        app.root = Mock()
        app.root.winfo_viewable.return_value = False
        app.store = Mock()
        app.last_tick_time = 0.0
        app.unrecorded_active_seconds = 0.0
        app.settings.update(tracking_enabled=False, program_panels_chosen=["Photoshop"])
        for name in ("application_totals", "application_two_week_labels", "application_session_labels", "application_record_hours_labels",
                     "application_status_labels", "application_last_session_labels"):
            setattr(app, name, {program: Mock() for program in main.PROGRAM_PANEL_SETTINGS})
        for query in ("total_for_day", "total_for_range", "lifetime_sessions", "total_seconds"):
            getattr(app.store, query).return_value = 0
        app.store.last_recorded_day.return_value = None
        with patch("main.foreground_application", return_value="Photoshop"), patch("main.user_is_active", return_value=True), patch(
            "time.monotonic", return_value=1.0
        ), patch.multiple(app, _draw_progress_indicator=Mock(), _draw_level_badge=Mock(), _celebrate_level_up=Mock(), _set_feedback_unlocked=Mock()):
            app._track_and_refresh()

        self.assertTrue(app.active)
        self.assertEqual(app.store.record_active_second.call_args.args[1], "Photoshop")
        # The user hid Photoshop's panel, so it stays hidden
        self.assertFalse(app.settings["tracking_enabled"])

    def test_a_programs_panel_switches_on_the_first_time_it_is_used(self):
        self.app._reveal_panel_on_first_use("Krita")

        self.assertTrue(self.app.settings["tracking_krita"])
        self.assertEqual(self.app.settings["program_panels_chosen"], ["Krita"])
        self.app.setting_vars["tracking_krita"].set.assert_called_once_with(True)
        self.app._save_settings.assert_called_once_with()
        self.app._update_application_panels.assert_called_once_with()

    def test_a_panel_hidden_by_hand_is_never_switched_back_on(self):
        self.app.settings["program_panels_chosen"] = ["Krita"]
        self.app._reveal_panel_on_first_use("Krita")
        self.assertFalse(self.app.settings["tracking_krita"])

        # Photoshop's panel is on by default, so if it is off the user turned it off
        self.app.settings["tracking_enabled"] = False
        self.app._reveal_panel_on_first_use("Photoshop")
        self.assertFalse(self.app.settings["tracking_enabled"])
        self.app._save_settings.assert_not_called()

    def test_ticking_or_unticking_a_program_marks_its_panel_as_chosen(self):
        app = self.app
        app.settings["tracking_clip_studio_paint"] = True
        app.setting_vars["tracking_clip_studio_paint"].get.return_value = False
        app._setting_changed("tracking_clip_studio_paint")

        self.assertFalse(app.settings["tracking_clip_studio_paint"])
        self.assertEqual(app.settings["program_panels_chosen"], ["Clip Studio Paint"])
        app._reveal_panel_on_first_use("Clip Studio Paint")
        self.assertFalse(app.settings["tracking_clip_studio_paint"])

    def test_a_damaged_list_of_chosen_panels_is_ignored(self):
        self.app.settings["program_panels_chosen"] = "Krita"
        self.assertEqual(self.app._chosen_panels(), [])
        self.app.settings["program_panels_chosen"] = ["Krita", 7, None]
        self.assertEqual(self.app._chosen_panels(), ["Krita"])


class SingleInstanceTests(unittest.TestCase):
    def _instance(self, suffix):
        class Named(SingleInstance):
            CLAIM_NAME = f"Local\\PSFocusTest.RunningCopy.{suffix}"
            SHOW_NAME = f"Local\\PSFocusTest.ShowWindow.{suffix}"
            EXIT_NAME = f"Local\\PSFocusTest.ExitRequest.{suffix}"

        return Named()

    @unittest.skipUnless(os.name == "nt", "uses Windows named objects")
    def test_second_copy_finds_the_first_and_asks_it_to_show_its_window(self):
        suffix = uuid.uuid4().hex
        first = self._instance(suffix)
        self.assertFalse(first.already_running)
        self.assertFalse(first.show_requested())

        second = self._instance(suffix)
        self.assertTrue(second.already_running)
        second.ask_running_copy_to_show()

        # Heard once, then quiet until asked again
        self.assertTrue(first.show_requested())
        self.assertFalse(first.show_requested())
        # The installer's request to close is a separate signal
        self.assertFalse(first.exit_requested())
        second.ask_running_copy_to_exit()
        self.assertTrue(first.exit_requested())
        self.assertFalse(first.exit_requested())
        self.assertFalse(first.show_requested())
        self.assertFalse(self._instance(uuid.uuid4().hex).already_running)

    def test_second_copy_started_by_hand_shows_the_first_and_never_opens_its_own_window(self):
        for arguments, asked in ((["PS Focus.exe"], True), (["PS Focus.exe", "--minimized"], False)):
            with self.subTest(arguments=arguments), patch("main.sys.argv", arguments), patch("main.set_app_user_model_id"), patch(
                "main.SingleInstance"
            ) as claim, patch("main.migrate_legacy_app_data") as migrate, patch("main.tk.Tk") as create_window:
                claim.return_value.already_running = True
                main.main()

                self.assertEqual(claim.return_value.ask_running_copy_to_show.called, asked)
                migrate.assert_not_called()
                create_window.assert_not_called()


class LegacyDataMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.legacy, self.current = root / "FocusTrace", root / "PS Focus"
        self.legacy.mkdir()
        for name in ("settings.json", "activity.sqlite3", "google-token.json", "unrelated.txt"):
            (self.legacy / name).write_text(name, encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _migrate(self):
        with patch("app_config.LEGACY_APP_DATA", self.legacy), patch("app_config.APP_DATA", self.current):
            migrate_legacy_app_data()

    def test_first_launch_under_the_new_name_carries_the_earlier_data_over(self):
        self._migrate()

        self.assertEqual(sorted(path.name for path in self.current.iterdir()), ["activity.sqlite3", "google-token.json", "settings.json"])

    def test_a_sign_in_removed_by_signing_out_is_not_brought_back_at_the_next_launch(self):
        self._migrate()
        (self.current / "google-token.json").unlink()

        self._migrate()

        self.assertFalse((self.current / "google-token.json").exists())


class MinimumHeightTests(unittest.TestCase):
    def test_settings_page_is_never_cut_short_and_the_overview_shrinks_to_its_panels(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.root = Mock()
        app.root.winfo_reqheight.return_value = 476
        app.settings = {}
        with patch.object(app, "_compact_height", return_value=178), patch.object(app, "_full_height", return_value=900):
            app.view = "Settings"
            app._set_minimum_height()
            self.assertEqual(app.root.minsize.call_args.args[1], 476)
            app.view = "Overview"
            app._set_minimum_height()
            self.assertEqual(app.root.minsize.call_args.args[1], 178)

    def test_the_least_height_is_never_more_than_the_whole_overview(self):
        # With a program panel last, everything down to it may be a little more than the overview's own height;
        # a least height above the most would leave Windows no size to give, and the window would be shoved about
        app = PSFocusApp.__new__(PSFocusApp)
        app.root = Mock()
        app.settings = {}
        app.view = "Overview"
        with patch.object(app, "_compact_height", return_value=984), patch.object(app, "_full_height", return_value=980):
            app._set_minimum_height()
        self.assertEqual(app.root.minsize.call_args.args[1], 980)

    def test_landscape_overview_is_never_cut_short(self):
        # The modules stand beside the panels, so the window stops at the height that shows them whole
        app = PSFocusApp.__new__(PSFocusApp)
        app.root = Mock()
        app.root.winfo_reqheight.return_value = 200
        app.settings = {"landscape": True}
        app.view = "Overview"
        with patch.object(app, "_compact_height", return_value=178):
            app._set_minimum_height()
        self.assertEqual(app.root.minsize.call_args.args[1], 200)


class TodayPanelTests(unittest.TestCase):
    def test_every_program_panel_including_photoshop_follows_its_tracking_setting(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.module_vars = {}
        app.settings = {"tracking_enabled": False, "tracking_krita": True, "tracking_clip_studio_paint": False}
        self.assertFalse(app._block_shown("Photoshop"))
        self.assertTrue(app._block_shown("Krita"))
        self.assertFalse(app._block_shown("Clip Studio Paint"))
        app.settings["tracking_enabled"] = True
        self.assertTrue(app._block_shown("Photoshop"))


class SizeLimitTests(unittest.TestCase):
    def test_dragging_an_edge_past_a_limit_stops_that_edge_and_leaves_the_opposite_one_where_it_is(self):
        limited = SizeLimits.limited_outline
        # Window at 100,100 to 436,1119: a frame of 16 by 39 around contents 320 by 980, the most allowed
        window = (100, 100, 436, 1119)
        top, bottom, left = 3, 6, 1
        self.assertEqual(limited(top, (100, -500, 436, 1119), window, (320, 193), (320, 980), (16, 39)), window)
        self.assertEqual(limited(bottom, (100, 100, 436, 1700), window, (320, 193), (320, 980), (16, 39)), window)
        # Windows may already have held the size by moving the bottom edge up; it is put back where it was
        self.assertEqual(limited(top, (100, 0, 436, 1019), window, (320, 193), (320, 980), (16, 39)), window)
        # Past the least height, dragging the top edge down stops it 193 above the bottom, plus the frame
        self.assertEqual(limited(top, (100, 1000, 436, 1119), window, (320, 193), (320, 980), (16, 39)), (100, 887, 436, 1119))
        # Sideways the same: dragging the left edge too far keeps the right edge
        wide = (0, 0, 1000, 239)
        self.assertEqual(limited(left, (-900, 0, 1000, 239), wide, (320, 200), (1600, 200), (16, 39)), (-616, 0, 1000, 239))
        # Within the limits the dragged edge simply follows the pointer
        self.assertEqual(limited(top, (100, 300, 436, 1119), window, (320, 193), (320, 980), (16, 39)), (100, 300, 436, 1119))


class ProgramPanelRuleTests(unittest.TestCase):
    def test_the_last_program_panel_shown_cannot_be_hidden(self):
        class Variable:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        app = PSFocusApp.__new__(PSFocusApp)
        app.settings = {"tracking_enabled": True, "tracking_krita": False, "tracking_clip_studio_paint": False}
        app.setting_vars = {"tracking_enabled": Variable(False)}
        with patch.object(app, "_save_settings") as save, patch.object(app, "_update_application_panels"):
            app._setting_changed("tracking_enabled")
        self.assertTrue(app.settings["tracking_enabled"])
        self.assertTrue(app.setting_vars["tracking_enabled"].get())
        save.assert_not_called()

        # With Krita's panel shown too, Photoshop's can go
        app.settings["tracking_krita"] = True
        app.setting_vars["tracking_enabled"].set(False)
        with patch.object(app, "_save_settings"), patch.object(app, "_update_application_panels"), patch.object(app, "_note_panel_chosen"):
            app._setting_changed("tracking_enabled")
        self.assertFalse(app.settings["tracking_enabled"])


class BlockOrderTests(unittest.TestCase):
    def _app(self, settings: dict) -> PSFocusApp:
        app = PSFocusApp.__new__(PSFocusApp)
        app.settings = settings
        return app

    def test_an_earlier_arrangement_is_carried_over_with_the_program_panels_kept_together(self):
        # Before 1.0.6 the modules had their own order, and some could stand before the program panels
        app = self._app({"module_order": ["calendar", "graph", "stats"], "modules_left": ["calendar"]})
        self.assertEqual(app._read_block_order(), ["calendar", "Photoshop", "Krita", "Clip Studio Paint", "graph", "stats"])

    def test_a_saved_order_is_kept_and_anything_missing_or_unknown_is_put_right(self):
        app = self._app({"block_order": ["stats", "Krita", "stats", "unknown", "Photoshop"]})
        self.assertEqual(app._read_block_order(), ["stats", "Krita", "Photoshop", "Clip Studio Paint", "graph", "calendar"])


class ChartPeriodTests(unittest.TestCase):
    def test_selected_chart_period_is_always_saved_for_the_next_launch(self):
        app = PSFocusApp.__new__(PSFocusApp)
        app.settings = {"period": "Day"}
        with patch.object(app, "_save_settings") as save, patch.object(app, "_draw_chart"):
            app._set_period("6 Months")

        self.assertEqual(app.period, "6 Months")
        self.assertEqual(app.settings["period"], "6 Months")
        save.assert_called_once()


class LineChartTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.chart = Mock()
        # The total is written on the chart itself outside the landscape layout
        self.app.chart_text_canvas = self.app.chart
        self.app.chart_headline = "headline"
        self.app.chart_caption = "caption"
        self.app.chart_hover_index = None
        self.app.chart_state = {
            "left": 34,
            "step": 10.0,
            "top": 64,
            "bottom": 184,
            "points": [(34.0, 184.0), (44.0, 124.0), (54.0, 154.0)],
            "values": [0.0, 90.0, 45.0, 0.0, 0.0],
            "start": date(2026, 9, 28),
            "total": 135.0,
            "caption": "This week",
        }

    def _headline(self):
        texts = {call.args[0]: call.kwargs["text"] for call in self.app.chart.itemconfigure.call_args_list}
        return texts["headline"], texts["caption"]

    def test_line_and_fill_are_drawn_only_between_the_given_points(self):
        image = render_line_chart(100, 60, [(10, 50), (40, 10), (70, 30)], 50, [(10, 90, 50)])
        self.assertEqual(image.size, (100, 60))
        panel = image.getpixel((95, 5))
        self.assertNotEqual(image.getpixel((40, 10)), panel)
        self.assertNotEqual(image.getpixel((40, 40)), panel)
        self.assertEqual(image.getpixel((85, 30)), panel)

    def test_headline_shows_period_total_until_a_point_is_hovered(self):
        self.app._update_chart_hover()
        self.assertEqual(self._headline(), ("2h 15m 00s", "This week"))

        event = Mock()
        event.x = 46
        self.app._chart_hovered(event)
        self.assertEqual(self.app.chart_hover_index, 1)
        self.assertEqual(self._headline(), ("1h 30m 00s", "Tue 29 Sep"))

        # Days that have not happened yet are not on the line, so hovering there stays on the latest point
        event.x = 300
        self.app._chart_hovered(event)
        self.assertEqual(self.app.chart_hover_index, 2)

        self.app._chart_left(event)
        self.assertEqual(self._headline(), ("2h 15m 00s", "This week"))


class LevelBadgeTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.level_revealed = False
        self.app.displayed_level = (21, False)
        self.app.level_widgets = (Mock(), Mock())
        self.app.feedback_unlocked = True
        self.app.feedback_button = Mock()
        self.app.settings = {"feedback_submitted": False}

    def test_feedback_stays_locked_until_two_hours_of_art_time_are_tracked(self):
        self.app.feedback_unlocked = False
        with patch.object(self.app, "_open_feedback_dialog") as open_dialog:
            self.app._level_clicked()
            open_dialog.assert_not_called()
            self.app.feedback_button.pack.assert_not_called()

            self.app._set_feedback_unlocked(True)
            self.app._level_clicked()

        open_dialog.assert_called_once_with(reveal_prompt=True)
        self.app.feedback_button.pack.assert_called_once()
        for widget in self.app.level_widgets:
            widget.configure.assert_called_with(cursor="hand2")
        self.assertEqual(FEEDBACK_UNLOCK_SECONDS, 2 * 60 * 60)

    def test_hidden_badge_is_blurred(self):
        revealed = render_level_badge(21, True)
        hidden = render_level_badge(21, False)
        self.assertEqual(revealed.size, hidden.size)
        self.assertNotEqual(revealed.tobytes(), hidden.tobytes())
        # Blurring spreads the number into its surroundings, so the brightest pixel dims
        self.assertLess(hidden.convert("L").getextrema()[1], revealed.convert("L").getextrema()[1])

    def test_clicking_blurred_level_asks_for_feedback_without_revealing_it(self):
        with patch.object(self.app, "_open_feedback_dialog") as open_dialog, patch.object(self.app, "_draw_level_badge") as draw:
            self.app._level_clicked()
            self.app._level_clicked()

        self.assertEqual(open_dialog.call_count, 2)
        open_dialog.assert_called_with(reveal_prompt=True)
        self.assertFalse(self.app.level_revealed)
        draw.assert_not_called()

    def test_level_is_revealed_and_remembered_once_feedback_is_submitted(self):
        with patch.object(self.app, "_send_pending_feedback") as send, patch.object(
            self.app, "_save_settings"
        ) as save, patch.object(self.app, "_draw_level_badge") as draw, patch.object(
            self.app, "_open_feedback_dialog"
        ) as open_dialog:
            self.app._feedback_submitted()
            self.app._level_clicked()

        send.assert_called_once()
        save.assert_called_once()
        self.assertTrue(self.app.settings["feedback_submitted"])
        self.assertTrue(self.app.level_revealed)
        draw.assert_called_once_with(21)
        open_dialog.assert_not_called()

    def test_cooldown_starts_after_the_second_feedback_and_every_one_after(self):
        with patch.object(self.app, "_send_pending_feedback"), patch.object(self.app, "_save_settings"), patch.object(
            self.app, "_draw_level_badge"
        ):
            self.app._feedback_submitted()
            self.assertEqual(self.app.settings["feedback_count"], 1)
            self.assertIsNone(self.app._feedback_cooldown_remaining())

            for count in (2, 3):
                self.app._feedback_submitted()
                self.assertEqual(self.app.settings["feedback_count"], count)
                remaining = self.app._feedback_cooldown_remaining()
                self.assertGreater(remaining, timedelta(minutes=29))
                self.assertLessEqual(remaining, timedelta(minutes=30))
                # Once the half hour has passed, feedback can be sent again
                self.app.settings["feedback_cooldown_until"] = (datetime.now() - timedelta(seconds=1)).isoformat()
                self.assertIsNone(self.app._feedback_cooldown_remaining())

    def test_feedback_sent_before_counting_began_is_treated_as_the_first(self):
        self.app.settings = {"feedback_submitted": True}
        with patch.object(self.app, "_send_pending_feedback"), patch.object(self.app, "_save_settings"), patch.object(
            self.app, "_draw_level_badge"
        ):
            self.app._feedback_submitted()

        self.assertEqual(self.app.settings["feedback_count"], 2)
        self.assertIsNotNone(self.app._feedback_cooldown_remaining())


class ActivityBackupFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.google = Mock()
        self.app.google.connected = True
        self.app.results = queue.Queue()
        self.app.remote_backup_payloads = queue.Queue()
        self.app.backup_in_progress = False
        self.app.drive_backup_path = None
        self.app.store = Mock()
        self.app.activity_backup_status = Mock()
        self.backup_path = Mock()
        self.backup_path.read_bytes.return_value = b"local database"

    def test_backup_uploads_local_history_when_drive_is_empty(self):
        self.app.google.download_activity_backup.return_value = None

        self.app._drive_backup_worker(self.backup_path)

        self.app.google.upload_activity_backup.assert_called_once_with(b"local database")
        self.assertEqual(self.app.results.get_nowait()[:2], ("backup", True))

    def test_backup_queues_drive_merge_when_both_histories_have_activity(self):
        self.app.google.download_activity_backup.return_value = b"remote database"

        with patch("tracker.ActivityStore.database_has_user_data", return_value=True):
            self.app._drive_backup_worker(self.backup_path)

        self.app.google.upload_activity_backup.assert_not_called()
        self.assertEqual(self.app.remote_backup_payloads.get_nowait(), b"remote database")
        self.assertEqual(self.app.results.get_nowait()[0], "merge_backup")

    def test_backup_queues_drive_restore_for_empty_local_database(self):
        self.app.google.download_activity_backup.return_value = b"remote database"

        with patch("tracker.ActivityStore.database_has_user_data", return_value=False):
            self.app._drive_backup_worker(self.backup_path)

        self.assertEqual(self.app.remote_backup_payloads.get_nowait(), b"remote database")
        self.assertEqual(self.app.results.get_nowait()[0], "restore_backup")

    def test_restore_merges_instead_if_local_data_arrived_after_drive_check(self):
        with patch("tracker.ActivityStore.database_has_user_data", return_value=True), patch(
            "tracker.ActivityStore.restore_backup_bytes"
        ) as restore, patch.object(self.app, "_merge_downloaded_activity_backup") as merge:
            self.app._restore_downloaded_activity_backup(b"remote database")

        restore.assert_not_called()
        self.app.store.close.assert_not_called()
        merge.assert_called_once_with(b"remote database")

    def test_merge_uploads_existing_snapshot_when_drive_added_nothing(self):
        self.app.drive_backup_path = self.backup_path
        self.app.store.merge_backup_bytes.return_value = 0

        with patch("threading.Thread") as thread:
            self.app._merge_downloaded_activity_backup(b"remote database")

        self.app.store.create_local_backups.assert_not_called()
        self.assertEqual(thread.call_args.kwargs["args"], (self.backup_path,))

    def test_merge_uploads_fresh_snapshot_when_drive_added_history(self):
        merged_path = Path("merged-activity-backup.sqlite3")
        self.app.drive_backup_path = self.backup_path
        self.app.store.merge_backup_bytes.return_value = 3
        self.app.store.create_local_backups.return_value = [merged_path]

        with patch("threading.Thread") as thread, patch.object(self.app, "_refresh_activity_views") as refresh:
            self.app._merge_downloaded_activity_backup(b"remote database")

        refresh.assert_called_once()
        self.assertEqual(thread.call_args.kwargs["args"], (merged_path,))

    def test_failed_merge_releases_backup_for_the_next_attempt(self):
        self.app.backup_in_progress = True
        self.app.store.merge_backup_bytes.side_effect = OSError("disk full")

        with patch("threading.Thread") as thread:
            self.app._merge_downloaded_activity_backup(b"remote database")

        thread.assert_not_called()
        self.assertFalse(self.app.backup_in_progress)

    def test_backup_starts_drive_sync_automatically_when_connected(self):
        backup_path = Path("local-activity-backup.sqlite3")
        self.app.store.create_local_backups.return_value = [backup_path]

        with patch("threading.Thread") as thread:
            self.app._backup_activity_now()
            self.app._backup_activity_now()

        thread.assert_called_once()
        self.assertEqual(thread.call_args.kwargs["args"], (backup_path,))
        self.assertTrue(self.app.backup_in_progress)


class GoogleDisplayNameTests(unittest.TestCase):
    def setUp(self):
        self.app = PSFocusApp.__new__(PSFocusApp)
        self.app.root = Mock()
        self.app.google = Mock()
        self.app.google.connected = True
        self.app.results = queue.Queue()
        self.app.settings = {"google_display_name": "Artist"}
        self.app._save_settings = Mock()
        self.app.google_account_email = "artist@example.com"
        self.app.google_reauthentication_required = False
        self.app.settings_resync_in_progress = False
        for widget in (
            "font_small",
            "font_account",
            "account_label",
            "google_settings_status",
            "google_connect_button",
            "google_reconnect_button",
            "google_switch_button",
            "google_logout_button",
        ):
            setattr(self.app, widget, Mock())

    def test_chosen_username_survives_logout_and_shows_after_reconnecting(self):
        self.app.google.connected = False
        self.app.results.put(("logout", True, "Signed out of Google"))
        self.app._poll_results()
        self.assertEqual(self.app.settings["google_display_name"], "Artist")
        self.assertIsNone(self.app.google_account_email)

        self.app.google.connected = True
        for kind in ("connect", "switch", "account"):
            with self.subTest(kind=kind):
                self.app.results.put((kind, True, "artist@example.com"))
                self.app._poll_results()
                self.assertEqual(self.app.account_label.configure.call_args.kwargs["text"], "Artist")
                self.assertIs(self.app.account_label.configure.call_args.kwargs["font"], self.app.font_account)
                self.assertEqual(self.app.google_settings_status.configure.call_args.kwargs["text"], "artist@example.com")

    def test_each_google_account_keeps_its_own_username(self):
        # The single name saved by earlier versions goes to the account connected when the app is upgraded
        self.app._update_google_status("Artist@Example.com")
        self.assertEqual(self.app.settings["google_display_names"], {"artist@example.com": "Artist"})
        self.assertEqual(self.app.settings["google_display_name"], "")
        self.app._save_settings.assert_called_once()

        self.app.results.put(("switch", True, "second@example.com"))
        self.app._poll_results()
        self.assertEqual(self.app.account_label.configure.call_args.kwargs["text"], "second@example.com")

        self.app.editing_display_name = True
        self.app.account_name_entry = Mock()
        self.app.account_name_entry.get.return_value = "  Second  "
        self.app._finish_display_name_edit(save=True)
        self.assertEqual(self.app.account_label.configure.call_args.kwargs["text"], "Second")

        self.app.results.put(("switch", True, "artist@example.com"))
        self.app._poll_results()
        self.assertEqual(self.app.account_label.configure.call_args.kwargs["text"], "Artist")
        self.assertEqual(self.app.settings["google_display_names"], {"artist@example.com": "Artist", "second@example.com": "Second"})

    def test_google_failure_messages_are_not_replaced_by_the_raw_error(self):
        for kind, expected in (
            ("switch", "Could not switch Google accounts: offline"),
            ("account", "Could not load Google account: offline"),
        ):
            with self.subTest(kind=kind):
                self.app.account_label.reset_mock()
                self.app.results.put((kind, False, "offline"))
                self.app._poll_results()
                self.assertEqual(self.app.account_label.configure.call_args.kwargs["text"], expected)

    def test_clicking_settings_email_resyncs_and_reports_in_settings_status(self):
        self.app.account_label.cget.return_value = "normal"
        with patch("threading.Thread") as thread:
            self.app._resync_google()
            self.app._resync_google()

        thread.assert_called_once()
        self.assertEqual(self.app.google_settings_status.configure.call_args.kwargs["text"], "Syncing…")

        self.app.account_label.reset_mock()
        self.app.results.put(("resync", True, "Settings backed up to Google Drive"))
        self.app._poll_results()
        self.assertFalse(self.app.settings_resync_in_progress)
        self.assertEqual(
            self.app.google_settings_status.configure.call_args.kwargs["text"],
            "Settings backed up to Google Drive",
        )
        self.app.account_label.configure.assert_not_called()

    def test_clicking_settings_email_does_nothing_while_disconnected_or_busy(self):
        with patch("threading.Thread") as thread:
            self.app.account_label.cget.return_value = "disabled"
            self.app._resync_google()
            self.app.account_label.cget.return_value = "normal"
            self.app.google.connected = False
            self.app._resync_google()

        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
