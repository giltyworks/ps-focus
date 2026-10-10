"""The graph module: time per hour or day over a period, with period buttons and a readout that follows the mouse"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

import app_config
from app_config import CHART_FILL_OPACITY, CHART_PERIOD_CAPTIONS, EDGE_PADDING, MODULE_CANVAS_WIDTH, MODULE_MARGIN, format_duration
from tracker import ActivityStore

from .module import STRIP_GAP, ModuleBlock, PaintedButton
from .theme import Fonts, color, draw_anchored, draw_text, line_height, text_width, tk_round

# The same measurements as the Tk graph, see ui_chart.py: the gap between period buttons; the space below the
# buttons; the space above the plot kept for the total and its caption; the plot's margins at the left, right and
# bottom; the gap between an hour label and the plot; where the total and its caption sit
PERIOD_BUTTON_GAP = 4
CONTROLS_GAP = 6
CHART_TEXT_SPACE = 64
PLOT_LEFT = 34
PLOT_RIGHT_MARGIN = 18
PLOT_BOTTOM_MARGIN = 26
AXIS_LABEL_GAP = 8
HEADLINE_AT = (EDGE_PADDING - 1, 2)
CAPTION_AT = (EDGE_PADDING, 34)
# The landscape layout's side strip, see ui_chart.py: how far the module's name sits from the top, the space
# between the strip's rows, and the gaps either side of the column of period buttons; the space the chart keeps
# above its plot there, for the top hour label alone; and the widest stacked total the strip makes room for
SIDE_TITLE_TOP = 5
SIDE_STRIP_GAP = 6
SIDE_BUTTON_GAP = MODULE_MARGIN
# How far the name strip runs on past the module's name in landscape
SIDE_TITLE_ROOM = 12
SIDE_CHART_GAP = MODULE_MARGIN
CHART_TOP_SPACE = 14
SIDE_HEADLINE_SAMPLE = "000h"
PERIOD_LABELS = {"Day": "1D", "Week": "1W", "Month": "1M", "3 Months": "3M", "6 Months": "6M", "1 Year": "1Y"}


@dataclass
class Plot:
    """The drawn chart's measurements, which the readout under the mouse is worked out from"""

    left: float
    step: float
    top: float
    bottom: float
    points: list[tuple[float, float]]
    values: list[float]
    # The first day shown, or None for the hours of today
    start: date | None
    total: float
    caption: str


class ChartModule(ModuleBlock):
    def __init__(self, fonts: Fonts, store: ActivityStore, period: str, on_period: Callable[[str], None]) -> None:
        super().__init__("Usage over time", fonts)
        self.store = store
        self.period = period
        self.on_period = on_period
        self.period_buttons = {
            name: PaintedButton(label, lambda value=name: self._set_period(value), fonts, 6, 6, width_in_digits=2) for name, label in PERIOD_LABELS.items()
        }
        self.buttons = list(self.period_buttons.values())
        self.month_text = ""
        self.plot: Plot | None = None
        self.drawn_state: tuple | None = None
        self.hover_index: int | None = None
        # The chart without the readout, drawn when the data changes, so following the mouse only redraws the readout
        self.picture: QPixmap | None = None
        self.set_layout(False)

    def side_rows(self) -> tuple[int, int, int, int, int]:
        """Where the landscape strip's rows start, inside the border: the month, the total, the caption and the
        button column, and where the strip ends"""
        fonts = self.fonts
        # Clear of the line under the name strip
        month_top = SIDE_TITLE_TOP + line_height(fonts.bold) + SIDE_STRIP_GAP + STRIP_GAP
        headline_top = month_top + line_height(fonts.small) + 2
        # Room for the three lines of the stacked total; a shorter total has its caption moved up under it
        caption_top = headline_top + 3 * line_height(fonts.headline)
        text_bottom = caption_top + line_height(fonts.caption) + SIDE_STRIP_GAP
        buttons_top = SIDE_TITLE_TOP - 1
        count, height = len(self.buttons), self.buttons[0].height
        buttons_bottom = buttons_top + count * height + (count - 1) * PERIOD_BUTTON_GAP + SIDE_STRIP_GAP
        return month_top, headline_top, caption_top, buttons_top, max(text_bottom, buttons_bottom)

    def side_width(self) -> int:
        """Width of the landscape strip: the name, with room for its strip to run on past it, and the total; then the
        column of period buttons"""
        room = max(text_width(self.fonts.bold, self.title) + SIDE_TITLE_ROOM, text_width(self.fonts.headline, SIDE_HEADLINE_SAMPLE))
        return MODULE_MARGIN + room + SIDE_BUTTON_GAP + self.buttons[0].width

    def glass_changed(self) -> None:
        self.drawn_state = None

    def side_title_width(self) -> int:
        # The column up to the period buttons, which stand at its right from the top, a couple of pixels clear of them
        return self.side_width() - self.buttons[0].width - 2

    def docked_width(self) -> int:
        return 2 + self.side_width() + MODULE_CANVAS_WIDTH

    def landscape_height(self) -> int:
        """Height the graph needs in landscape, inside its border: its strip, or its chart, which without the total
        above it is shorter by that space so that its plot stays the same size"""
        return max(self.side_rows()[4], app_config.CHART_HEIGHT - CHART_TEXT_SPACE + CHART_TOP_SPACE)

    def set_layout(self, landscape: bool, height: int = 0) -> None:
        """Put the month and period buttons above the chart, or in landscape in a strip beside it together with the
        total and its caption, the module's height then being this much inside its border"""
        self.landscape = landscape
        width = MODULE_CANVAS_WIDTH
        if landscape:
            side = self.side_width()
            buttons_top = self.side_rows()[3]
            for index, button in enumerate(self.buttons):
                button.place(1 + side - button.width, 1 + buttons_top + index * (button.height + PERIOD_BUTTON_GAP))
            self.chart_origin = QPoint(1 + side, 1)
            self.chart_size = (width, height)
            self.setFixedSize(2 + side + width, 2 + height)
        else:
            # Lined up against the right edge, as in the Tk graph
            right = 1 + width - EDGE_PADDING
            for index, button in enumerate(reversed(self.buttons)):
                button.place(right - button.width - index * (button.width + PERIOD_BUTTON_GAP), self.content_top)
            button_height = self.buttons[0].height
            self.chart_origin = QPoint(1, self.content_top + button_height + CONTROLS_GAP)
            self.chart_size = (width, app_config.CHART_HEIGHT)
            self.set_content_height(button_height + CONTROLS_GAP + app_config.CHART_HEIGHT)
        self.picture = None
        self.drawn_state = None

    def _set_period(self, period: str) -> None:
        self.period = period
        self.on_period(period)
        self.refresh()

    def refresh(self) -> None:
        """Read the period's data again and redraw the chart"""
        today = date.today()
        # The short month name, so it fits beside the period buttons however long the month's name
        self.month_text = today.strftime("%b %Y")
        values, labels = self.store.period_data(self.period)
        count = len(values)
        # The line stops at the present, so hours and days still to come are left empty
        if self.period == "Day":
            start = None
            last_index = datetime.now().hour
        else:
            if self.period == "Week":
                start = today - timedelta(days=today.weekday())
            elif self.period == "1 Year":
                start = date(today.year, 1, 1)
            else:
                start = today - timedelta(days=count - 1)
            last_index = min(count - 1, (today - start).days)
        state = (
            self.period, today, last_index, tuple(values), tuple(labels),
            self.chart_size, self.landscape, self.devicePixelRatioF(),
        )
        if state == self.drawn_state:
            return
        for name, button in self.period_buttons.items():
            button.selected = name == self.period
        width, height = self.chart_size
        max_hours = max(1, math.ceil(max(max(values, default=0), 60) / 60))
        tick_step = max(1, math.ceil(max_hours / 4))
        max_hours = math.ceil(max_hours / tick_step) * tick_step
        tick_hours = range(0, max_hours + 1, tick_step)
        if self.landscape:
            # Beside the strip the plot starts just after its widest hour label
            left = SIDE_CHART_GAP + max(text_width(self.fonts.caption, f"{hour}h") for hour in tick_hours) + AXIS_LABEL_GAP
            top = CHART_TOP_SPACE
        else:
            left, top = PLOT_LEFT, CHART_TEXT_SPACE
        right, bottom = width - PLOT_RIGHT_MARGIN, height - PLOT_BOTTOM_MARGIN
        if right <= left or bottom <= top or not count:
            self.plot, self.picture = None, None
            self.update()
            return
        plot_height = bottom - top
        max_minutes = max_hours * 60
        step = (right - left) / max(count - 1, 1)
        points = [
            (left + index * step, bottom - min(plot_height, value / max_minutes * plot_height))
            for index, value in enumerate(values[:last_index + 1])
        ]
        gridlines = [bottom - plot_height * hour / max_hours for hour in tick_hours]
        self.plot = Plot(left, step, top, bottom, points, values, start, sum(values), CHART_PERIOD_CAPTIONS.get(self.period, str(today.year)))

        ratio = self.devicePixelRatioF()
        picture = QPixmap(round(width * ratio), round(height * ratio))
        picture.setDevicePixelRatio(ratio)
        picture.fill(self.picture_fill())
        painter = QPainter(picture)
        self._paint_plot(painter, points, bottom, [(left, right, y) for y in gridlines])
        muted = color("muted")
        for hour, y in zip(tick_hours, gridlines):
            draw_anchored(painter, left - AXIS_LABEL_GAP, y, "e", f"{hour}h", muted, self.fonts.caption)
        label_font = self.fonts.tiny if self.period == "Month" else self.fonts.caption
        for index, label in enumerate(labels):
            if label:
                draw_anchored(painter, left + index * step, bottom + 15, "center", label, muted, label_font)
        if not any(values):
            draw_anchored(painter, (left + right) / 2, top + plot_height / 2, "center", "No activity recorded for this period", muted, self.fonts.normal)
        painter.end()
        self.picture = picture
        self.drawn_state = state
        self.update()

    @staticmethod
    def _paint_plot(painter: QPainter, points: list[tuple[float, float]], baseline: float, gridlines: list[tuple[float, float, float]]) -> None:
        """The gridlines, the line with the fill fading down from it, and a dot at its end, as rendering.render_line_chart"""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Pillow, which drew the Tk chart, puts a coordinate at the middle of a pixel and Qt at its corner
        painter.translate(0.5, 0.5)
        painter.setPen(QPen(color("border"), 1))
        for left, right, y in gridlines:
            painter.drawLine(QPointF(left, y), QPointF(right, y))
        blue = color("calendar_blue")
        if len(points) >= 2:
            peak = min(y for _, y in points)
            fade = QLinearGradient(0, peak, 0, max(baseline, peak + 1))
            top_color = QColor(blue)
            top_color.setAlphaF(CHART_FILL_OPACITY)
            bottom_color = QColor(blue)
            bottom_color.setAlphaF(0)
            fade.setColorAt(0, top_color)
            fade.setColorAt(1, bottom_color)
            area = QPolygonF([QPointF(x, y) for x, y in points] + [QPointF(points[-1][0], baseline), QPointF(points[0][0], baseline)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fade)
            painter.drawPolygon(area)
            line = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                line.lineTo(QPointF(*point))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(blue, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(line)
        if points:
            x, y = points[-1]
            painter.setPen(Qt.PenStyle.NoPen)
            for radius, dot_color in ((4.5, color("panel")), (3, blue)):
                painter.setBrush(dot_color)
                painter.drawEllipse(QPointF(x, y), radius, radius)
        painter.restore()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        self.paint_frame(painter)
        if self.landscape:
            month_top = 1 + self.side_rows()[0]
        else:
            month_top = self.content_top + (self.buttons[0].height - line_height(self.fonts.small)) // 2
        draw_text(painter, 1 + EDGE_PADDING, month_top, self.month_text, color("muted"), self.fonts.small)
        for button in self.buttons:
            button.paint(painter)
        if self.picture is not None:
            self.draw_picture(painter, self.chart_origin, self.picture)
        self._paint_readout(painter)
        self.paint_dock_controls(painter)
        painter.end()

    def _paint_readout(self, painter: QPainter) -> None:
        """The total and its caption, or with the mouse over the chart, that hour or day's time and a marker on it"""
        plot = self.plot
        if plot is None:
            return
        painter.save()
        painter.translate(self.chart_origin)
        if self.hover_index is None:
            minutes, caption = plot.total, plot.caption
        else:
            index = min(self.hover_index, len(plot.points) - 1)
            x, y = plot.points[index]
            painter.save()
            dashes = QPen(color("muted"), 1)
            dashes.setDashPattern([2, 3])
            painter.setPen(dashes)
            column = tk_round(x) + 0.5
            painter.drawLine(QPointF(column, tk_round(plot.top - 6)), QPointF(column, tk_round(plot.bottom)))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(color("text"), 2))
            painter.setBrush(color("calendar_blue"))
            painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8).adjusted(0.5, 0.5, -0.5, -0.5))
            painter.restore()
            minutes = plot.values[index]
            if plot.start is None:
                hour_start = datetime(2000, 1, 1, index).strftime("%I %p").lstrip("0")
                hour_end = datetime(2000, 1, 1, (index + 1) % 24).strftime("%I %p").lstrip("0")
                caption = f"{hour_start} to {hour_end}"
            else:
                caption = (plot.start + timedelta(days=index)).strftime("%a %d %b").replace(" 0", " ")
        painter.restore()
        headline = format_duration(round(minutes * 60))
        if self.landscape:
            # In the strip the hours, minutes and seconds stand one under another, the caption just below
            headline_top = 1 + self.side_rows()[1]
            lines = headline.split(" ")
            for index, line in enumerate(lines):
                draw_text(painter, MODULE_MARGIN, headline_top + index * line_height(self.fonts.headline), line, color("text"), self.fonts.headline)
            caption_top = headline_top + len(lines) * line_height(self.fonts.headline)
            draw_text(painter, 1 + MODULE_MARGIN, caption_top, caption, color("muted"), self.fonts.caption)
        else:
            origin = self.chart_origin
            draw_text(painter, origin.x() + HEADLINE_AT[0], origin.y() + HEADLINE_AT[1], headline, color("text"), self.fonts.headline)
            draw_text(painter, origin.x() + CAPTION_AT[0], origin.y() + CAPTION_AT[1], caption, color("muted"), self.fonts.caption)

    def _chart_point(self, point: QPoint) -> QPoint | None:
        """The point on the chart under the mouse, or None off the chart"""
        local = point - self.chart_origin
        width, height = self.chart_size
        if 0 <= local.x() < width and 0 <= local.y() < height:
            return local
        return None

    def _set_hover(self, index: int | None) -> None:
        if index != self.hover_index:
            self.hover_index = index
            # In landscape the readout is in the strip, so the whole module is repainted
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        plot, local = self.plot, self._chart_point(event.position().toPoint())
        if plot is None or local is None:
            self._set_hover(None)
            return
        index = round((local.x() - plot.left) / plot.step) if plot.step else 0
        self._set_hover(max(0, min(len(plot.points) - 1, index)))

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._set_hover(None)
