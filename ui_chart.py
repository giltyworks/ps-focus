"""Usage line chart: period buttons, drawing, and hover readout"""

from __future__ import annotations

import base64
import io
import math
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta

import app_config
from app_config import (
    CHART_PERIODS,
    CHART_PERIOD_CAPTIONS,
    COLORS,
    EDGE_PADDING,
    MODULE_CANVAS_WIDTH,
    MODULE_MARGIN,
    format_duration,
)
from rendering import render_line_chart
from widgets import CONTROL_TAG, CanvasButton, CanvasText

# Pixels between one period button and the next
PERIOD_BUTTON_GAP = 4
HEADLINE_FONT = ("Segoe UI Semibold", 16)
CAPTION_FONT = ("Segoe UI", 8)
# Space the chart keeps above its plot for the total and its caption, and, in the landscape layout where
# those sit in the side strip, just for the top gridline's label
CHART_TEXT_SPACE = 64
CHART_TOP_SPACE = 14
# Landscape layout's side strip: how far the module's name sits from the top, the space between the
# strip's rows, and how many period buttons share a row
SIDE_TITLE_TOP = 5
SIDE_STRIP_GAP = 6
# In the landscape strip the period buttons stand in a column at the right, this far from the total, and
# the chart's hour labels start this far after them: as far as the strip's text is from the module's edge
SIDE_BUTTON_GAP = MODULE_MARGIN
SIDE_CHART_GAP = MODULE_MARGIN
AXIS_FONT = ("Segoe UI", 8)
# Space between an hour label and the plot it marks
AXIS_LABEL_GAP = 8
# In the landscape strip the total's hours, minutes and seconds stand one under another, so the strip need
# only be as wide as the module's name or the widest of these
SIDE_HEADLINE_SAMPLE = "000h"


class ChartMixin:
    def _build_chart(self) -> None:
        self.chart_panel, graph_content = self._create_module_frame("graph", "Usage over time")
        # The month and the period buttons share one canvas, see widgets.CanvasText
        self.chart_controls = tk.Canvas(graph_content, bg=COLORS["panel"], highlightthickness=0, width=MODULE_CANVAS_WIDTH, height=1)
        self.chart_controls.pack(fill="x", pady=(0, 6))
        self.period_buttons = {}
        for period in CHART_PERIODS:
            label = {"Day": "1D", "Week": "1W", "Month": "1M", "3 Months": "3M", "6 Months": "6M", "1 Year": "1Y"}[period]
            self.period_buttons[period] = CanvasButton(
                self.chart_controls,
                text=label,
                command=lambda value=period: self._set_period(value),
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                width=3,
                padx=8,
                pady=6,
                font=self.font_small,
            )
        button_height = self.period_buttons["Day"].height
        self.chart_controls.configure(height=button_height)
        self.current_month_label = CanvasText(
            self.chart_controls,
            EDGE_PADDING,
            (button_height - self.font_small.metrics("linespace")) // 2,
            "nw",
            "",
            COLORS["muted"],
            self.font_small,
        )
        self.chart_controls.bind("<Configure>", lambda event: self._place_period_buttons(event.width))
        self.chart = tk.Canvas(graph_content, bg=COLORS["panel"], highlightthickness=0, width=MODULE_CANVAS_WIDTH, height=app_config.CHART_HEIGHT)
        self.chart.pack(fill="both", expand=True)
        self.chart_drawn_width = 0
        # Only a new width, or more height than the chart asks for, changes the drawing; being cut short does not
        self.chart.bind(
            "<Configure>",
            lambda event: self._schedule_chart_redraw()
            if event.width != self.chart_drawn_width or event.height > self.chart.winfo_reqheight()
            else None,
        )
        self.chart.bind("<Motion>", self._chart_hovered)
        self.chart.bind("<Leave>", self._chart_left)
        # The canvas holding the total and its caption: the chart, or in landscape the side strip
        self.chart_text_canvas = self.chart
        self._lay_out_chart()

    def _side_strip_rows(self) -> tuple[int, int, int, int, int]:
        """Where the landscape strip's rows start: the month, the total, the caption and the button column, and
        where the strip ends"""
        headline_font, caption_font = tkfont.Font(font=HEADLINE_FONT), tkfont.Font(font=CAPTION_FONT)
        month_top = SIDE_TITLE_TOP + self.font_bold.metrics("linespace") + SIDE_STRIP_GAP
        headline_top = month_top + self.font_small.metrics("linespace") + 2
        # Room for the three lines of the stacked total; a shorter total has its caption moved up under it
        caption_top = headline_top + 3 * headline_font.metrics("linespace")
        text_bottom = caption_top + caption_font.metrics("linespace") + SIDE_STRIP_GAP
        buttons_top = SIDE_TITLE_TOP - 1
        count = len(self.period_buttons)
        buttons_bottom = buttons_top + count * self.period_buttons["Day"].height + (count - 1) * PERIOD_BUTTON_GAP + SIDE_STRIP_GAP
        return month_top, headline_top, caption_top, buttons_top, max(text_bottom, buttons_bottom)

    def _side_headline_room(self) -> int:
        return max(self.font_bold.measure("Usage over time"), tkfont.Font(font=HEADLINE_FONT).measure(SIDE_HEADLINE_SAMPLE))

    def _graph_side_width(self) -> int:
        """Width of the landscape strip: the name and total, then the column of period buttons"""
        return MODULE_MARGIN + self._side_headline_room() + SIDE_BUTTON_GAP + self.period_buttons["Day"].width

    def _graph_needed_height(self) -> int:
        """Height the graph needs in landscape: its strip, or its chart, which without the total above it is shorter
        by that space so that its plot stays the same size"""
        return max(self._side_strip_rows()[4], app_config.CHART_HEIGHT - CHART_TEXT_SPACE + CHART_TOP_SPACE)

    def _lay_out_chart(self) -> None:
        """Put the month and period buttons above the chart, or in the landscape layout in a strip beside it
        together with the module's name, the total and its caption"""
        controls, chart = self.chart_controls, self.chart
        controls.pack_forget()
        chart.pack_forget()
        controls.delete("side-title")
        if self._landscape():
            month_top, _headline, _caption, _buttons, bottom = self._side_strip_rows()
            controls.configure(width=self._graph_side_width(), height=bottom)
            controls.pack(side="left", fill="y")
            controls.create_text(MODULE_MARGIN, SIDE_TITLE_TOP, anchor="nw", text="Usage over time", fill=COLORS["text"], font=self.font_bold, tags="side-title")
            controls.coords(self.current_month_label.item, MODULE_MARGIN, month_top)
            chart.pack(side="left", fill="both", expand=True)
            self.chart_text_canvas = controls
            # As tall as the other modules beside it, see _match_landscape_heights
            self._match_landscape_heights()
        else:
            button_height = self.period_buttons["Day"].height
            controls.configure(width=MODULE_CANVAS_WIDTH, height=button_height)
            controls.pack(fill="x", pady=(0, 6))
            controls.coords(self.current_month_label.item, EDGE_PADDING, (button_height - self.font_small.metrics("linespace")) // 2)
            chart.configure(height=app_config.CHART_HEIGHT)
            chart.pack(fill="both", expand=True)
            self.chart_text_canvas = chart
        controls.delete("chart-text")
        self._place_period_buttons(int(controls.cget("width")))
        self.chart_drawn_width = 0

    def _place_period_buttons(self, width: int) -> None:
        """Line the period buttons up against the right edge, PERIOD_BUTTON_GAP apart as the calendar's buttons are.
        In the landscape layout they stand in a column, top to bottom, at the right of the side strip"""
        self.chart_controls.delete(CONTROL_TAG)
        pitch = self.period_buttons["Day"].width + PERIOD_BUTTON_GAP
        if self._landscape():
            buttons_top = self._side_strip_rows()[3]
            row_pitch = self.period_buttons["Day"].height + PERIOD_BUTTON_GAP
            for index, button in enumerate(self.period_buttons.values()):
                button.place(width - button.width, buttons_top + index * row_pitch)
            return
        right = width - EDGE_PADDING
        for index, button in enumerate(reversed(self.period_buttons.values())):
            button.place(right - button.width - index * pitch, 0)

    def _schedule_chart_redraw(self) -> None:
        if self.chart_redraw_after_id is not None:
            self.root.after_cancel(self.chart_redraw_after_id)
        self.chart_redraw_after_id = self.root.after(100, self._redraw_chart_if_needed)

    def _redraw_chart_if_needed(self) -> None:
        self.chart_redraw_after_id = None
        self._draw_chart()

    def _set_period(self, period: str) -> None:
        self.period = period
        self.settings["period"] = period
        self._save_settings()
        self._draw_chart()

    def _draw_chart(self) -> None:
        if not hasattr(self, "chart") or not self.chart.winfo_exists() or not self.module_vars["graph"].get():
            return
        canvas = self.chart
        canvas.delete("all")
        width = canvas.winfo_width()
        # Always drawn at its full height. A window dragged short cuts the chart off at its edge,
        # rather than the chart being squeezed into what is left and then vanishing
        height = max(canvas.winfo_height(), canvas.winfo_reqheight())
        self.chart_drawn_width = width
        if width <= 0 or height <= 0:
            return
        today = date.today()
        self.current_month_label.configure(text=today.strftime("%B %Y"))
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
        landscape = self._landscape()
        max_minutes = max(max(values, default=0), 60)
        max_hours = max(1, math.ceil(max_minutes / 60))
        tick_step = max(1, math.ceil(max_hours / 4))
        max_hours = math.ceil(max_hours / tick_step) * tick_step
        tick_hours = range(0, max_hours + 1, tick_step)
        if landscape:
            # Beside the strip the plot starts just after its widest hour label
            axis_font = tkfont.Font(font=AXIS_FONT)
            left = SIDE_CHART_GAP + max(axis_font.measure(f"{hour}h") for hour in tick_hours) + AXIS_LABEL_GAP
        else:
            left = 34
        right, top, bottom = width - 18, CHART_TOP_SPACE if landscape else CHART_TEXT_SPACE, height - 26
        if right <= left or bottom <= top or not count:
            self.chart_state = None
            return
        plot_height = bottom - top
        max_value = max_hours * 60
        step = (right - left) / max(count - 1, 1)
        points = [
            (left + index * step, bottom - min(plot_height, value / max_value * plot_height))
            for index, value in enumerate(values[:last_index + 1])
        ]
        gridlines = [bottom - plot_height * hour / max_hours for hour in tick_hours]

        image_top = top - 8
        buffer = io.BytesIO()
        render_line_chart(
            width,
            bottom + 6 - image_top,
            [(x, y - image_top) for x, y in points],
            bottom - image_top,
            [(left, right, y - image_top) for y in gridlines],
        ).save(buffer, format="PNG")
        self.chart_image = tk.PhotoImage(data=base64.b64encode(buffer.getvalue()))
        canvas.create_image(0, image_top, image=self.chart_image, anchor="nw")
        for hour, y in zip(tick_hours, gridlines):
            canvas.create_text(left - AXIS_LABEL_GAP, y, text=f"{hour}h", anchor="e", fill=COLORS["muted"], font=AXIS_FONT)
        label_font = ("Segoe UI", 7) if self.period == "Month" else ("Segoe UI", 8)
        for index, label in enumerate(labels):
            if label:
                canvas.create_text(left + index * step, bottom + 15, text=label, fill=COLORS["muted"], font=label_font)
        if not any(values):
            canvas.create_text((left + right) / 2, top + plot_height / 2, text="No activity recorded for this period", fill=COLORS["muted"], font=("Segoe UI", 10))

        text_canvas = self.chart_text_canvas
        if landscape:
            _month, headline_top, caption_top, _buttons, _bottom = self._side_strip_rows()
            text_canvas.delete("chart-text")
            headline_at, caption_at = (MODULE_MARGIN - 1, headline_top), (MODULE_MARGIN, caption_top)
        else:
            headline_at, caption_at = (EDGE_PADDING - 1, 2), (EDGE_PADDING, 34)
        self.chart_headline = text_canvas.create_text(*headline_at, anchor="nw", fill=COLORS["text"], font=HEADLINE_FONT, tags="chart-text")
        self.chart_caption = text_canvas.create_text(*caption_at, anchor="nw", fill=COLORS["muted"], font=CAPTION_FONT, tags="chart-text")
        self.chart_state = {
            "left": left,
            "step": step,
            "top": top,
            "bottom": bottom,
            "points": points,
            "values": values,
            "start": start,
            "total": sum(values),
            "caption": CHART_PERIOD_CAPTIONS.get(self.period, str(today.year)),
        }
        self._update_chart_hover()
        for period, button in self.period_buttons.items():
            # The selected period is marked by a white outline rather than a different fill
            selected = period == self.period
            button.configure(fg=COLORS["text"] if selected else COLORS["muted"])
            button.set_selected(selected)

    def _chart_hovered(self, event: tk.Event) -> None:
        state = self.chart_state
        if state is None:
            return
        index = round((event.x - state["left"]) / state["step"]) if state["step"] else 0
        index = max(0, min(len(state["points"]) - 1, index))
        if index != self.chart_hover_index:
            self.chart_hover_index = index
            self._update_chart_hover()

    def _chart_left(self, _event: tk.Event) -> None:
        if self.chart_hover_index is not None:
            self.chart_hover_index = None
            self._update_chart_hover()

    def _update_chart_hover(self) -> None:
        canvas = self.chart
        canvas.delete("hover")
        state = self.chart_state
        if state is None:
            return
        if self.chart_hover_index is None:
            minutes = state["total"]
            caption = state["caption"]
        else:
            index = min(self.chart_hover_index, len(state["points"]) - 1)
            x, y = state["points"][index]
            canvas.create_line(x, state["top"] - 6, x, state["bottom"], fill=COLORS["muted"], dash=(2, 3), tags="hover")
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=COLORS["calendar_blue"], outline=COLORS["text"], width=2, tags="hover")
            minutes = state["values"][index]
            if state["start"] is None:
                hour_start = datetime(2000, 1, 1, index).strftime("%I %p").lstrip("0")
                hour_end = datetime(2000, 1, 1, (index + 1) % 24).strftime("%I %p").lstrip("0")
                caption = f"{hour_start} to {hour_end}"
            else:
                caption = (state["start"] + timedelta(days=index)).strftime("%a %d %b").replace(" 0", " ")
        headline = format_duration(round(minutes * 60))
        text_canvas = self.chart_text_canvas
        if text_canvas is not self.chart:
            # In the landscape strip the hours, minutes and seconds stand one under another, the caption just below
            text_canvas.itemconfigure(self.chart_headline, text=headline.replace(" ", "\n"))
            caption_left = text_canvas.coords(self.chart_caption)[0]
            text_canvas.coords(self.chart_caption, caption_left, text_canvas.bbox(self.chart_headline)[3])
        else:
            text_canvas.itemconfigure(self.chart_headline, text=headline)
        text_canvas.itemconfigure(self.chart_caption, text=caption)
