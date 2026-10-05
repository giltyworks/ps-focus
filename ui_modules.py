"""Program panels and the graph, calendar, and stats modules: showing, hiding, and dragging them into order"""

from __future__ import annotations

import tkinter as tk

from app_config import (
    COLORS,
    COMPACT_BOTTOM_SPACE,
    EDGE_PADDING,
    MODULE_CANVAS_WIDTH,
    MODULE_CONTENT_MARGIN,
    MODULE_GAP,
    MODULE_MARGIN,
    PROGRAM_PANEL_SETTINGS,
    TODAY_PANEL_WIDTH,
    WINDOW_MARGIN,
)
from widgets import CONTROL_TAG, OutlinedButton

# Pixels between a module's name and its checkbox, the square the checkbox is centred in,
# and the space between one module's control and the next
MODULE_LABEL_GAP = 6
MODULE_CHECKBOX_SIZE = 18
MODULE_CONTROL_GAP = 8
# Height of the blank margin along the bottom of a window too short for its modules. It matches the space
# under the checkboxes when no module is open, so the smallest window looks the same either way
CLIP_MARGIN_HEIGHT = COMPACT_BOTTOM_SPACE
# Space above and below a module's title
MODULE_TITLE_PADDING = 5
# The modules, and every block that can be dragged into order: the program panels and the modules
MODULE_NAMES = ("graph", "calendar", "stats")
BLOCK_NAMES = ("Photoshop", "Krita", "Clip Studio Paint") + MODULE_NAMES
# Modules whose title and controls move into a strip down their left side in the landscape layout
SIDE_STRIP_MODULES = ("calendar", "graph")


class ModulesMixin:
    def _create_module_frame(self, name: str, title: str) -> tuple[tk.Frame, tk.Frame]:
        panel = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
        header = tk.Frame(panel, bg=COLORS["panel"])
        header.pack(fill="x", padx=MODULE_MARGIN, pady=MODULE_TITLE_PADDING)
        title_label = tk.Label(
            header, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=self.font_bold, cursor="hand2", bd=0, padx=0, pady=0
        )
        title_label.pack(side="left")
        self.module_headers[name] = header
        variable = tk.BooleanVar(value=bool(self.settings.get(f"show_{name}", True)))
        self.module_vars[name] = variable
        content = tk.Frame(panel, bg=COLORS["panel"])
        if variable.get():
            content.pack(fill="both", expand=True, padx=MODULE_CONTENT_MARGIN, pady=(0, MODULE_CONTENT_MARGIN))
        self.module_frames[name] = panel
        self.module_contents[name] = content
        return panel, content

    def _build_module_controls(self) -> None:
        """Make the module checkboxes clickable; they are drawn by _draw_module_controls for the layout shown

        Clicking a name or its checkbox toggles the module. They are drawn rather than built from widgets
        to keep the window quick to resize, so they cannot take keyboard focus
        """
        canvas = self.module_control_footer
        # For each module, the area of its control and the middle of its checkbox
        self.module_control_areas: dict[str, tuple[int, int, int, int, tuple[int, int]]] = {}
        canvas.bind("<Button-1>", self._module_control_clicked)
        canvas.bind("<Motion>", lambda event: canvas.configure(cursor="hand2" if self._module_control_at(event) else ""))
        self._draw_module_controls()

    def _draw_module_controls(self) -> None:
        """Draw the three module names and their checkboxes in a row, laid out from the right edge"""
        canvas = self.module_control_footer
        canvas.delete("all")
        text_height = self.font_small.metrics("linespace")
        row_height = max(text_height, MODULE_CHECKBOX_SIZE)
        self.module_control_areas = {}
        right = TODAY_PANEL_WIDTH - EDGE_PADDING
        for name, label in reversed((("graph", "Graph"), ("calendar", "Calendar"), ("stats", "Stats"))):
            left = right - self.font_small.measure(label) - MODULE_LABEL_GAP - MODULE_CHECKBOX_SIZE
            canvas.create_text(left, (row_height - text_height) // 2, anchor="nw", text=label, fill=COLORS["muted"], font=self.font_small)
            self.module_control_areas[name] = (left, 0, right, row_height, (right - MODULE_CHECKBOX_SIZE // 2, row_height // 2))
            self._draw_module_indicator(name)
            right = left - MODULE_CONTROL_GAP
        canvas.configure(width=TODAY_PANEL_WIDTH, height=row_height)

    def _build_clip_margin(self) -> None:
        """Prepare the blank margin kept along the bottom edge while the window is too short for its modules"""
        self.clip_margin = tk.Frame(self.root, bg=COLORS["background"])
        self.clip_margin_shown = False
        self.root.bind("<Configure>", self._window_resized, add="+")

    def _window_resized(self, event: tk.Event) -> None:
        # The window's own resize is the only one of interest; its widgets report theirs through it as well
        if event.widget is self.root:
            self._update_clip_margin(event.height)
            # In landscape a width the app did not ask for is one the user dragged to, kept while blocks come and
            # go until the window is dragged as wide as everything again
            if self._landscape() and self.view == "Overview" and event.width != getattr(self, "requested_width", event.width):
                self.landscape_chosen_width = event.width if event.width < self._landscape_full_width() else None
                self.requested_width = event.width
                self.window_placement = (event.width, self.root.winfo_x())
            # Dragging the left edge in landscape the window's picture moves with that edge, so sliding the row at
            # every step would have it drawn twice a step, flickering; it slides once the edge is let go. In
            # portrait the column slides as the top edge moves, keeping the panel holding the header in view
            limits = getattr(self, "size_limits", None)
            deferred = self._landscape() and limits is not None and limits.dragging_left_or_top
            if self.view == "Overview" and not deferred:
                self._scroll_blocks()

    def _update_clip_margin(self, window_height: int | None = None) -> None:
        """Show the bottom margin while the modules are cut off by the window's edge, and hide it otherwise

        As the window is dragged shorter the modules disappear gradually behind its edge. Without a margin
        they would run right up to that edge, and at the smallest height a few stray pixels of the first
        module's border would be left showing under the checkboxes. The margin is laid over the bottom of
        the window, so the height the window asks for, which other sizing relies on, is unchanged
        """
        if window_height is None:
            window_height = self.root.winfo_height()
        clipped = (
            self.view == "Overview"
            and window_height < self.root.winfo_reqheight()
            and any(variable.get() for variable in self.module_vars.values())
        )
        if clipped == self.clip_margin_shown:
            return
        self.clip_margin_shown = clipped
        if clipped:
            self.clip_margin.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, height=CLIP_MARGIN_HEIGHT)
            self.clip_margin.lift()
        else:
            self.clip_margin.place_forget()

    def _module_control_at(self, event: tk.Event) -> str | None:
        return next(
            (name for name, (left, top, right, bottom, _center) in self.module_control_areas.items() if left <= event.x < right and top <= event.y < bottom),
            None,
        )

    def _module_control_clicked(self, event: tk.Event) -> None:
        name = self._module_control_at(event)
        if name is not None:
            self.module_vars[name].set(not self.module_vars[name].get())
            self._toggle_module(name)

    def _draw_module_indicator(self, name: str) -> None:
        canvas = self.module_control_footer
        canvas.delete(f"checkbox-{name}")
        canvas.create_image(
            *self.module_control_areas[name][4],
            image=self._indicator_image(self.module_vars[name].get(), canvas.cget("bg")),
            tags=f"checkbox-{name}",
        )

    def _landscape(self) -> bool:
        return bool(self.settings.get("landscape", False))

    def _blocks(self) -> dict[str, tk.Widget]:
        """Every block that can be dragged into order, by name: the program panels and the modules"""
        return {**self.application_panels, **self.module_frames}

    def _block_shown(self, name: str) -> bool:
        """Whether a block is shown: a module ticked in the checkboxes, or a program panel ticked in Settings"""
        if name in self.module_vars:
            return self.module_vars[name].get()
        return bool(self.settings.get(PROGRAM_PANEL_SETTINGS[name], False))

    def _anchor_block(self) -> str | None:
        """The program panel the header and module checkboxes sit on in landscape: Photoshop's when it is shown,
        otherwise the first shown, or none when no program panel is shown"""
        if self._block_shown("Photoshop"):
            return "Photoshop"
        return next((name for name in self.block_order if name in self.application_panels and self._block_shown(name)), None)

    def _units(self) -> dict[str, tk.Widget]:
        """What stands in the container for each block: the block itself, or for the anchor panel in landscape the
        overview holding it under the header"""
        units = self._blocks()
        anchor = self._anchor_block()
        if self._landscape() and self.view == "Overview" and anchor is not None:
            units[anchor] = self.overview
        return units

    def _apply_layout(self) -> None:
        """Put the program panels and modules one under another, or side by side for the landscape layout"""
        self._set_window_resizable()
        self._arrange_modules()
        if self.view == "Overview":
            self._show_view()
        self._set_minimum_height()
        # Switching layout keeps the right edge, as the window starts in the screen's top right corner
        self._resize_to_content(fit=True, keep_right=True)
        self._update_clip_margin()

    def _set_window_resizable(self) -> None:
        """Let the window be dragged taller or shorter in portrait, and wider or narrower in landscape, down to the
        width of its first column; landscape's height is always exactly its blocks'"""
        landscape = self._landscape()
        resizable = (landscape, not landscape)
        self.landscape_chosen_width = None
        if tuple(bool(value) for value in self.root.resizable()) != resizable:
            self.root.resizable(*resizable)
            # Windows redraws the frame for the new setting and drops the dark title bar, so it is coloured again,
            # and Tk puts back the maximize button
            self._set_title_bar_colors()
            limits = getattr(self, "size_limits", None)
            if limits is not None:
                limits.remove_maximize_button()

    def _place_module_container(self) -> None:
        """Show the blocks with the overview, in the viewport that slides them: under it, or in landscape side by side
        with the overview among them"""
        container, viewport = self.module_container, self.module_viewport
        container.pack_forget()
        container.place_forget()
        viewport.pack_forget()
        if self.view != "Overview":
            return
        if self._landscape():
            viewport.pack(side="left", anchor="n", padx=(WINDOW_MARGIN, 0))
        elif any(self._block_shown(name) for name in self.block_order):
            # Stretched to any height left below the blocks, so that space is painted: a window dragged taller than
            # its blocks would otherwise show scraps of whatever was last drawn there
            viewport.pack(fill="both", expand=True, padx=WINDOW_MARGIN, after=self.overview)
            # Blocks slid up go under the header and checkboxes rather than over them: a widget is only cut off at
            # its parent's edges, and the blocks' parent is the window, so the header is drawn above them instead.
            # A canvas's own lift raises items drawn on it, so the widget's is called
            tk.Misc.lift(self.overview)
            tk.Misc.lift(self.header_canvas)
        else:
            return
        self._size_viewport()

    def _arrange_modules(self) -> None:
        """Pack the shown program panels and modules into the container in their order"""
        blocks = self._blocks()
        for block in blocks.values():
            block.pack_forget()
        landscape = self._landscape()
        # In landscape the calendar and graph draw their title in their side strip, so their title row goes
        for name in SIDE_STRIP_MODULES:
            header = self.module_headers[name]
            header.pack_forget()
            if not landscape:
                content = self.module_contents[name]
                # The title goes back above the contents, which are packed only while the module is open
                order = {"before": content} if content.winfo_manager() == "pack" else {}
                header.pack(fill="x", padx=MODULE_MARGIN, pady=MODULE_TITLE_PADDING, **order)
        self._lay_out_chart()
        if not landscape:
            self._stretch_today_panels(0)
        self.calendar_canvas.configure(width=MODULE_CANVAS_WIDTH + (self._calendar_side_width() if landscape else 0))
        self.calendar_visual_state = None
        if landscape and self.view == "Overview":
            self._arrange_landscape_units(blocks)
        else:
            for name in self.block_order:
                if self._block_shown(name):
                    blocks[name].pack(in_=self.module_container, fill="x", pady=(MODULE_GAP, 0))
        # While the window is first built the overview is not shown yet; _show_view places the container then
        if self.view == "Overview" and self.overview.winfo_manager():
            self._place_module_container()

    def _landscape_unit_names(self) -> list[str]:
        """The landscape layout's columns in order, by block name; "" is the overview standing on its own, first,
        when no program panel is shown to hold it"""
        names = [name for name in self.block_order if self._block_shown(name)]
        return names if self._anchor_block() is not None else [""] + names

    def _unit_width(self, name: str) -> int:
        units = self._units()
        return (units[name] if name else self.overview).winfo_reqwidth()

    def _landscape_full_width(self) -> int:
        """Width of the landscape window showing every column"""
        names = self._landscape_unit_names()
        return WINDOW_MARGIN + sum(self._unit_width(name) for name in names) + MODULE_GAP * (len(names) - 1)

    def _blocks_resized(self, _event: tk.Event) -> None:
        # A block growing or shrinking, such as the stats gaining a line, changes the size the window needs
        if self.view == "Overview" and self.module_container.winfo_manager() == "place":
            viewport = self.module_viewport
            if self._viewport_size() != (int(viewport.cget("width")), int(viewport.cget("height"))):
                self._size_viewport()
                self.root.after_idle(lambda: self._resize_to_content(fit=True))

    def _viewport_size(self) -> tuple[int, int]:
        """The viewport's size: the whole row of columns in landscape, the whole column of blocks in portrait"""
        height = self.module_container.winfo_reqheight()
        if self._landscape():
            return self._landscape_full_width() - WINDOW_MARGIN, height
        return TODAY_PANEL_WIDTH, height

    def _size_viewport(self) -> None:
        """Make the viewport as big as all the blocks, which the window's size is worked out from, and slide the blocks
        so the program panel holding the header stays in view"""
        viewport = self.module_viewport
        self.root.update_idletasks()
        width, height = self._viewport_size()
        viewport.configure(width=width, height=height)
        viewport.pack_propagate(False)
        self._scroll_blocks()

    def _anchor_span(self) -> tuple[int, int]:
        """Where the program panel holding the header starts and ends among the blocks, across in landscape and down in
        portrait; in portrait without a program panel, nothing need stay in view"""
        if self._landscape():
            names = self._landscape_unit_names()
            anchor = self._anchor_block() or ""
            start = sum(self._unit_width(name) + MODULE_GAP for name in names[: names.index(anchor)])
            return start, start + self._unit_width(anchor)
        anchor = self._anchor_block()
        if anchor is None:
            return 0, 0
        blocks = self._blocks()
        names = [name for name in self.block_order if self._block_shown(name)]
        # In portrait every block has a gap above it
        start = sum(blocks[name].winfo_reqheight() + MODULE_GAP for name in names[: names.index(anchor)]) + MODULE_GAP
        return start, start + blocks[anchor].winfo_reqheight()

    def _scroll_blocks(self) -> None:
        """Slide the blocks so the program panel holding the header stays in view as the window gets smaller

        Shrinking first hides the blocks after that panel, gradually, behind the window's right or bottom edge. Once
        the edge reaches the panel the blocks slide instead, hiding those before it behind the left edge or under the
        header, so the smallest window shows the header with that panel
        """
        viewport, container = self.module_viewport, self.module_container
        if viewport.winfo_manager() != "pack":
            return
        start, end = self._anchor_span()
        landscape = self._landscape()
        if landscape:
            room = max(1, self.root.winfo_width()) - WINDOW_MARGIN
            offset = min(max(0, end - room), start)
            placement = {"x": -offset, "y": 0}
        else:
            room = self.root.winfo_height() - viewport.winfo_y() - COMPACT_BOTTOM_SPACE
            offset = min(max(0, end - room), max(0, start - MODULE_GAP))
            placement = {"x": 0, "y": -offset, "relwidth": 1.0}
        # Most resizes leave the blocks where they are; moving them only when they must keeps resizing smooth
        if container.winfo_manager() == "place" and (landscape, offset) == getattr(self, "blocks_offset", None):
            return
        self.blocks_offset = (landscape, offset)
        container.place(in_=viewport, **placement)

    def _arrange_landscape_units(self, blocks: dict[str, tk.Widget]) -> None:
        """Pack the columns side by side, the overview with the header taking the anchor panel's place and holding it
        under the header and checkboxes; with no program panel shown the overview stands first on its own"""
        overview, container = self.overview, self.module_container
        units = self._units()
        for name in self._landscape_unit_names():
            (units[name] if name else overview).pack_forget()
        # Made before the container, the overview would be drawn behind it, and the header behind the overview;
        # a canvas's own lift raises items drawn on it, so the widget's is called
        tk.Misc.lift(overview, container)
        tk.Misc.lift(self.header_canvas, overview)
        anchor = self._anchor_block()
        for index, name in enumerate(self._landscape_unit_names()):
            unit = units[name] if name else overview
            unit.pack(in_=container, side="left", anchor="n", padx=(MODULE_GAP if index else 0, 0))
            if name and name == anchor:
                blocks[name].pack(in_=overview, anchor="w", pady=(MODULE_GAP, 0))

    def _bind_module_drag(self, name: str, widget: tk.Widget) -> None:
        if not isinstance(widget, OutlinedButton):
            widget.bind("<ButtonPress-1>", lambda event, block=name: self._begin_module_drag(block, event), add="+")
            widget.bind("<B1-Motion>", self._drag_module, add="+")
            widget.bind("<ButtonRelease-1>", self._end_module_drag, add="+")
        for child in widget.winfo_children():
            self._bind_module_drag(name, child)

    def _begin_module_drag(self, name: str, event: tk.Event) -> None:
        # A press on a button drawn on a canvas is a click on that button, not the start of a drag
        if isinstance(event.widget, tk.Canvas) and CONTROL_TAG in event.widget.gettags("current"):
            return
        self.drag_candidate = name
        self.drag_origin = (event.x_root, event.y_root)
        self.dragged_module = None
        self.module_order_changed = False

    def _drag_module(self, event: tk.Event) -> str | None:
        """Move the dragged block past the one under the pointer: by height when stacked, and by width when the
        blocks stand side by side in the landscape layout"""
        if self.drag_candidate is None or self.drag_origin is None:
            return None
        if self.dragged_module is None:
            distance = max(abs(event.x_root - self.drag_origin[0]), abs(event.y_root - self.drag_origin[1]))
            if distance < 5:
                return None
            self.dragged_module = self.drag_candidate
            self._mark_dragged(True)
            self.root.configure(cursor="hand2")

        source = self.dragged_module
        self.root.update_idletasks()
        landscape = self._landscape()
        target = None
        target_midpoint = 0
        for name, block in self._units().items():
            if name == source or not block.winfo_ismapped():
                continue
            top = block.winfo_rooty()
            bottom = top + block.winfo_height()
            left = block.winfo_rootx()
            right = left + block.winfo_width()
            if left <= event.x_root <= right and top <= event.y_root <= bottom:
                target = name
                target_midpoint = left + block.winfo_width() // 2 if landscape else top + block.winfo_height() // 2
                break
        if target is None:
            return None

        source_index = self.block_order.index(source)
        target_index = self.block_order.index(target)
        insert_index = target_index + int((event.x_root if landscape else event.y_root) > target_midpoint)
        if source_index < insert_index:
            insert_index -= 1
        if source_index == insert_index:
            return None
        self.block_order.pop(source_index)
        self.block_order.insert(insert_index, source)
        self.settings["block_order"] = self.block_order.copy()
        self.module_order_changed = True
        self._arrange_modules()
        return "break"

    def _mark_dragged(self, dragged: bool) -> None:
        """Outline the block being dragged in blue, and return it to normal after"""
        self._blocks()[self.dragged_module].configure(highlightbackground=COLORS["calendar_blue"] if dragged else COLORS["border"])

    def _end_module_drag(self, _event: tk.Event) -> str | None:
        was_dragged = self.dragged_module is not None
        if was_dragged:
            self._mark_dragged(False)
        if self.module_order_changed:
            self._save_settings()
            # A program panel moved further down may need the window kept taller, see _compact_height
            self._set_minimum_height()
        self.drag_candidate = None
        self.drag_origin = None
        self.dragged_module = None
        self.module_order_changed = False
        self.root.configure(cursor="")
        return "break" if was_dragged else None

    def _toggle_module(self, name: str) -> None:
        visible = self.module_vars[name].get()
        self._draw_module_indicator(name)
        content = self.module_contents[name]
        if visible:
            content.pack(fill="both", expand=True, padx=MODULE_CONTENT_MARGIN, pady=(0, MODULE_CONTENT_MARGIN))
        else:
            content.pack_forget()
        self._arrange_modules()
        self.settings[f"show_{name}"] = visible
        self._save_settings()
        self._resize_to_content(fit=not visible)
        # The window may keep its height, in which case no resize arrives to bring the margin up to date
        self._update_clip_margin()
        if visible and name == "calendar":
            self._schedule_calendar_refresh()
        elif visible and name == "graph":
            self.root.after_idle(self._draw_chart)
        elif visible and name == "stats":
            self._draw_stats()
