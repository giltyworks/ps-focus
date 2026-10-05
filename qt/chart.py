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
from app_config import CHART_FILL_OPACITY, CHART_PERIOD_CAPTIONS, CHART_PERIODS, EDGE_PADDING, MODULE_CANVAS_WIDTH, format_duration
from tracker import ActivityStore

from .module import ModuleBlock, PaintedButton
from .theme import Fonts, color, draw_anchored, draw_text, line_height, tk_round

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
            name: PaintedButton(label, lambda value=name: self._set_period(value), fonts, 8, 6, width_in_digits=3) for name, label in PERIOD_LABELS.items()
        }
        self.buttons = list(self.period_buttons.values())
        button_height = self.buttons[0].height
        # Lined up against the right edge, as in the Tk graph
        right = 1 + MODULE_CANVAS_WIDTH - EDGE_PADDING
        for index, button in enumerate(reversed(self.buttons)):
            button.left = right - button.width - index * (button.width + PERIOD_BUTTON_GAP)
            button.top = self.content_top
        self.chart_top = self.content_top + button_height + CONTROLS_GAP
        self.set_content_height(button_height + CONTROLS_GAP + app_config.CHART_HEIGHT)
        self.month_text = ""
        self.plot: Plot | None = None
        self.hover_index: int | None = None
        # The chart without the readout, drawn when the data changes, so following the mouse only redraws the readout
        self.picture: QPixmap | None = None

    def _set_period(self, period: str) -> None:
        self.period = period
        self.on_period(period)
        self.refresh()

    def refresh(self) -> None:
        """Read the period's data again and redraw the chart"""
        today = date.today()
        self.month_text = today.strftime("%B %Y")
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
        for name, button in self.period_buttons.items():
            button.selected = name == self.period
        width, height = MODULE_CANVAS_WIDTH, app_config.CHART_HEIGHT
        max_hours = max(1, math.ceil(max(max(values, default=0), 60) / 60))
        tick_step = max(1, math.ceil(max_hours / 4))
        max_hours = math.ceil(max_hours / tick_step) * tick_step
        tick_hours = range(0, max_hours + 1, tick_step)
        left, right, top, bottom = PLOT_LEFT, width - PLOT_RIGHT_MARGIN, CHART_TEXT_SPACE, height - PLOT_BOTTOM_MARGIN
        if not count:
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
        picture.fill(color("panel"))
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
        button_height = self.buttons[0].height
        draw_text(
            painter, 1 + EDGE_PADDING, self.content_top + (button_height - line_height(self.fonts.small)) // 2,
            self.month_text, color("muted"), self.fonts.small,
        )
        for button in self.buttons:
            button.paint(painter)
        painter.translate(1, self.chart_top)
        if self.picture is not None:
            painter.drawPixmap(0, 0, self.picture)
        self._paint_readout(painter)
        painter.end()

    def _paint_readout(self, painter: QPainter) -> None:
        """The total and its caption, or with the mouse over the chart, that hour or day's time and a marker on it"""
        plot = self.plot
        if plot is None:
            return
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
        draw_text(painter, *HEADLINE_AT, format_duration(round(minutes * 60)), color("text"), self.fonts.headline)
        draw_text(painter, *CAPTION_AT, caption, color("muted"), self.fonts.caption)

    def _chart_point(self, point: QPoint) -> QPoint | None:
        """The point on the chart under the mouse, or None off the chart"""
        local = point - QPoint(1, self.chart_top)
        if 0 <= local.x() < MODULE_CANVAS_WIDTH and 0 <= local.y() < app_config.CHART_HEIGHT:
            return local
        return None

    def _set_hover(self, index: int | None) -> None:
        if index != self.hover_index:
            self.hover_index = index
            self.update(1, self.chart_top, MODULE_CANVAS_WIDTH, app_config.CHART_HEIGHT)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        plot, local = self.plot, self._chart_point(event.position().toPoint())
        if plot is None or local is None:
            self._set_hover(None)
            return
        index = round((local.x() - plot.left) / plot.step) if plot.step else 0
        self._set_hover(max(0, min(len(plot.points) - 1, index)))

    def leaveEvent(self, _event) -> None:
        self._set_hover(None)
