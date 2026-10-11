/* The interactive PS Focus demo on the download page: the app's window rebuilt for the browser with made-up data, so
   visitors can try it. It follows the real app (qt/), which it cannot run: change both together. Nothing is sent
   anywhere; the friends are invented and live only on the page */
(function () {
  "use strict";

  const root = document.querySelector(".psf-demo");
  if (!root) return;
  const PAINTING = root.dataset.painting;
  const LOGO = root.dataset.logo;
  const DAY = 86400000;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const SESSION_MINIMUM = 15 * 60;
  // Fully see-through, a background keeps this much, as in the app (qt/docking.py)
  const GLASS_MIN = 2 / 255;
  const touch = window.matchMedia("(max-width: 760px), (pointer: coarse)");

  // ----- Made-up history: an aspiring artist about ten weeks in, drawing most days, the same on every visit -----

  let seed = 11;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const pick = (list) => list[Math.floor(random() * list.length)];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const key = (date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  const daysAgo = (count) => new Date(today.getTime() - count * DAY);
  // For each day, the seconds in each hour
  const history = new Map();
  const ratings = new Map();
  const STARTED_DAYS_AGO = 72;
  for (let ago = STARTED_DAYS_AGO; ago >= 1; ago--) {
    const day = daysAgo(ago);
    const weekend = day.getDay() === 0 || day.getDay() === 6;
    // Sessions come more often as the habit takes hold
    const skip = (weekend ? 0.3 : 0.45) - (STARTED_DAYS_AGO - ago) / STARTED_DAYS_AGO * 0.15;
    if (random() < skip) continue;
    const hours = new Array(24).fill(0);
    let hour = pick([17, 18, 19, 20, 21, 10, 14]);
    let remaining = pick([25, 35, 45, 60, 75, 90, 120]) * 60;
    while (remaining > 0 && hour < 24) {
      const seconds = Math.min(remaining, 2400 + Math.floor(random() * 1200));
      hours[hour++] = seconds;
      remaining -= seconds;
    }
    history.set(key(day), hours);
    if (random() < 0.3) ratings.set(key(day), 4 + Math.floor(random() * 5));
  }
  const todayHours = new Array(24).fill(0);
  // Today so far: an hour and a bit, in the session going on
  const thisHour = new Date().getHours();
  todayHours[Math.max(0, thisHour - 1)] = 2460; todayHours[thisHour] = 1690;
  history.set(key(today), todayHours);

  const dayTotal = (date) => (history.get(key(date)) || []).reduce((sum, value) => sum + value, 0);
  const rangeTotal = (from, to) => { let sum = 0; for (let t = from.getTime(); t <= to.getTime(); t += DAY) sum += dayTotal(new Date(t)); return sum; };
  let lifetime = 0;
  history.forEach((hours) => hours.forEach((seconds) => (lifetime += seconds)));

  const LEVEL_ANCHORS = [[1, 0], [10, 40], [25, 180], [50, 650], [75, 1350], [80, 1550], [85, 1800], [90, 2100], [92, 2250], [95, 2500], [97, 2725], [98, 2850], [99, 3000]];
  const levelFor = (hours) => {
    for (let i = 1; i < LEVEL_ANCHORS.length; i++) {
      const [level, needed] = LEVEL_ANCHORS[i], [previous, before] = LEVEL_ANCHORS[i - 1];
      if (hours < needed) return previous + Math.floor((hours - before) / (needed - before) * (level - previous));
    }
    return 99;
  };
  const clock = (seconds) => {
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = Math.floor(seconds % 60);
    return h ? `${h}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s` : m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
  };
  const hm = (seconds) => { const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60); return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`; };
  const longDate = (date) => `${WEEKDAYS[(date.getDay() + 6) % 7]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;

  // ----- State -----

  const state = {
    drawing: true,
    transparency: 70,
    period: "Week",
    calendarView: "Month",
    calendarMonth: new Date(today.getFullYear(), today.getMonth(), 1),
    shown: { graph: true, calendar: true, friends: false },
    programs: { Photoshop: true, "Clip Studio Paint": false, Krita: false },
    paused: false,
    settingsOpen: false,
    landscape: false,
    startWithWindows: true,
    startMinimized: true,
    fanfareOff: false,
    // Every block in the window's order, program panels and modules alike, as in the app
    order: ["today", "Clip Studio Paint", "Krita", "graph", "calendar", "friends"],
    floating: {},
    status: "online",
    favourites: new Set(),
    friends: [
      { code: "MIAA", name: "Mia", level: 19, presence: "drawing", program: "Krita", two: 16.4, total: 121.6, today: 1.4 },
      { code: "LEOO", name: "Leo", level: 14, presence: "online", two: 10.2, total: 71.3, today: 0.6 },
      { code: "AVAA", name: "Ava", level: 11, presence: "away", two: 6.8, total: 47.9, today: 0.0 },
      { code: "NOAH", name: "Noah", level: 8, presence: "offline", two: 3.1, total: 28.4, today: 0.0 },
    ],
    request: null,
    requestShown: false,
    requestsOpen: false,
    pointerInside: { main: true },
  };

  // ----- Building blocks -----

  const el = (tag, attributes = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (name === "class") node.className = value;
      else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
      else if (value !== false && value != null) node.setAttribute(name, value === true ? "" : value);
    }
    for (const child of children.flat()) if (child != null && child !== false) node.append(child.nodeType ? child : document.createTextNode(child));
    return node;
  };
  const svg = (markup, size = 14) => {
    const holder = document.createElement("span");
    holder.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${markup}</svg>`;
    return holder.firstChild;
  };
  const ICONS = {
    graph: '<path d="M1 13H13"/><path d="M1.5 10.5L5 6.5L8 8.5L12.5 2.5"/>',
    calendar: '<rect x="1" y="2.5" width="12" height="10.5" rx="2"/><path d="M1 5.5H13M4.2 0.8V3.4M9.8 0.8V3.4"/><circle cx="4" cy="8" r=".5" fill="currentColor"/><circle cx="7" cy="8" r=".5" fill="currentColor"/><circle cx="10" cy="8" r=".5" fill="currentColor"/><circle cx="4" cy="10.8" r=".5" fill="currentColor"/><circle cx="7" cy="10.8" r=".5" fill="currentColor"/><circle cx="10" cy="10.8" r=".5" fill="currentColor"/>',
    friends: '<circle cx="9.5" cy="4" r="1.8"/><path d="M7.4 9.6C8 8 11.6 8 13.3 10.2"/><circle cx="5" cy="4.8" r="2.2"/><path d="M0.8 12.8C1.4 9.4 8.4 9.4 9.2 12.8"/>',
    chevron: '<path d="M4 5.5L7 8.5L10 5.5"/>',
    dock: '<path d="M6 4L3 7L6 10M10 4L7 7L10 10"/>',
  };
  const PERSON = '<circle cx="7" cy="4.2" r="2.6" fill="currentColor" stroke="none"/><path d="M1.6 13C1.6 8 12.4 8 12.4 13Z" fill="currentColor" stroke="none"/>';
  const PERSON_PLUS = '<circle cx="6" cy="4.2" r="2.4" fill="currentColor" stroke="none"/><path d="M1 13C1 8.4 11 8.4 11 13Z" fill="currentColor" stroke="none"/><circle cx="11" cy="10.4" r="3.4" fill="#080808" stroke="none"/><circle cx="11" cy="10.4" r="2.4" stroke-width="1.1"/><path d="M9.8 10.4H12.2M11 9.2V11.6" stroke-width="1.1"/>';

  let toastTimer;
  const toast = (text) => {
    stage.querySelector(".psf-toast")?.remove();
    const note = el("div", { class: "psf-toast" }, text);
    stage.append(note);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => note.remove(), 2600);
  };

  let menu = null;
  const closeMenu = () => { menu?.remove(); menu = null; };
  const openMenu = (anchor, items) => {
    closeMenu();
    menu = el("div", { class: "psf-menu", role: "menu" }, items);
    stage.append(menu);
    const a = anchor.getBoundingClientRect(), s = stage.getBoundingClientRect();
    const left = Math.min(a.left - s.left, stage.clientWidth - menu.offsetWidth - 4);
    menu.style.left = `${Math.max(4, left)}px`;
    menu.style.top = `${a.bottom - s.top + 2}px`;
  };
  document.addEventListener("pointerdown", (event) => { if (menu && !menu.contains(event.target)) closeMenu(); }, true);

  // ----- The page's controls and the scene -----

  const drawingSwitch = el("button", { class: "psf-switch", role: "switch", "aria-checked": "true", type: "button" },
    el("span", { class: "psf-track" }), el("span", {}, "Drawing in Photoshop"));
  // Fully right is fully solid, as the app's slider
  const slider = el("input", { type: "range", min: 0, max: 100, value: 100 - state.transparency, "aria-label": "Transparency, solid at the right" });
  const controls = el("div", { class: "psf-controls" },
    drawingSwitch,
    el("label", { class: "psf-slider" }, "Transparency", slider),
    el("span", { class: "psf-hint" }, touch.matches ? "The icons at the top show and hide each part · tap the painting to let PS Focus fade"
      : "The icons at the top show and hide each part · drag a panel out by its title · move your mouse onto the painting"));
  const stage = el("div", { class: "psf-stage" });
  const canvas = el("div", { class: "psf-canvas", role: "img", "aria-label": "A painting on the art app's canvas" });
  canvas.style.backgroundImage = `url("${PAINTING}")`;
  stage.append(canvas);
  root.append(controls, stage);

  drawingSwitch.addEventListener("click", () => {
    markUsed("timer");
    state.drawing = !state.drawing;
    drawingSwitch.setAttribute("aria-checked", String(state.drawing));
    renderToday();
  });
  const setTransparency = (amount) => {
    state.transparency = amount;
    slider.value = 100 - amount;
    settingsSlider.value = 100 - amount;
    updateGlass();
  };
  slider.addEventListener("input", () => setTransparency(100 - Number(slider.value)));

  // ----- The window -----

  const win = el("div", { class: "psf-window", role: "application", "aria-label": "PS Focus demo" });
  const titlebar = el("div", { class: "psf-titlebar" },
    el("img", { src: LOGO, alt: "" }), "PS Focus", el("span", { class: "psf-spacer" }),
    el("button", { type: "button", title: "Minimise", onclick: () => toast("In the app this minimises PS Focus") }, "–"),
    el("button", { type: "button", class: "psf-close", title: "Close to the tray", onclick: () => toast("PS Focus keeps counting in the tray when closed") }, "✕"));
  const progressDot = el("span", { class: "psf-dot" });
  const levelBadge = el("span", { class: "psf-badge" });
  const accountName = el("span", { class: "psf-account-name", title: "Double-click to change your name" }, "gilty");
  // A double click on the name edits it, as in the app: Enter or clicking away keeps it, Escape leaves it as it was,
  // and an empty name goes back to the first one
  accountName.addEventListener("dblclick", () => {
    markUsed("rename");
    const field = el("input", { class: "psf-name-field", type: "text", maxlength: 32, value: accountName.textContent, "aria-label": "Your name" });
    let done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      if (keep) accountName.textContent = field.value.trim() || "gilty";
      field.replaceWith(accountName);
    };
    field.addEventListener("keydown", (event) => { if (event.key === "Enter") finish(true); if (event.key === "Escape") finish(false); });
    field.addEventListener("blur", () => finish(true));
    accountName.replaceWith(field);
    field.focus();
    field.select();
  });
  const statusButton = el("button", { type: "button", class: "psf-icon-button psf-chevron", title: "Status", onclick: (event) => statusMenu(event.currentTarget) }, svg(ICONS.chevron));
  const account = el("div", { class: "psf-account" }, progressDot, accountName, statusButton);
  const settingsButton = el("button", { type: "button", class: "psf-icon-button psf-settings", title: "Settings", onclick: () => toggleSettings() }, "···");
  const level = el("div", { class: "psf-level" }, "Level", levelBadge);
  // In Settings the header shows the version and the credit in place of the level and account
  const credit = el("div", { class: "psf-credit", hidden: true }, el("span", { class: "psf-version" }, "Version 1.2.0"), el("span", { class: "psf-by" }, "by giltyworks"));
  const header = el("div", { class: "psf-header" }, level, account, credit, settingsButton);
  const iconButtons = {};
  const icons = el("div", { class: "psf-icons" }, ["graph", "calendar", "friends"].map((name) => {
    iconButtons[name] = el("button", { type: "button", class: "psf-icon-button", title: `Show or hide ${name}`, onclick: () => { markUsed("icons"); toggleModule(name); } }, svg(ICONS[name]));
    return iconButtons[name];
  }));
  const blocks = el("div", { class: "psf-blocks" });
  // Settings takes the place of the icons and blocks while open, see toggleSettings
  const settingsPage = el("div", { class: "psf-settings-page", hidden: true });
  // The grip the window is resized by: its bottom edge in portrait, its right edge in landscape
  const grip = el("div", { class: "psf-grip", "aria-hidden": "true" });
  win.append(titlebar, header, icons, blocks, settingsPage, grip);
  stage.append(win);

  const dockIcon = () => el("button", { type: "button", class: "psf-icon-button psf-dock", title: "Back into the window", "data-dock": "" }, svg(ICONS.dock));
  const strip = (title, extra = []) => el("div", { class: "psf-strip" }, el("span", {}, title), el("span", { class: "psf-spacer" }), extra, dockIcon());

  // The program panel
  const today_ = {
    two: el("span", { class: "psf-two-week" }),
    metric: el("div", { class: "psf-metric" }),
    sessions: el("span", { class: "psf-small" }),
    record: el("span", {}),
    status: el("span", { class: "psf-status" }),
    last: el("span", {}),
  };
  const todayBlock = el("div", { class: "psf-block psf-today", "data-name": "today" },
    el("div", { class: "psf-strip" }, el("span", {}, "Photoshop"), today_.two, dockIcon()),
    el("div", { class: "psf-today-body" }, today_.metric,
      el("div", { class: "psf-row" }, today_.sessions, today_.record),
      el("div", { class: "psf-row" }, today_.status, today_.last)));
  const sessionsCount = [...history.values()].filter((hours) => hours.reduce((a, b) => a + b, 0) >= SESSION_MINIMUM).length;
  const lastSession = (() => { for (let ago = 1; ago <= STARTED_DAYS_AGO; ago++) if (dayTotal(daysAgo(ago)) > 0) return daysAgo(ago); return today; })();

  function renderToday() {
    const todaySeconds = dayTotal(today);
    today_.two.textContent = `${(rangeTotal(daysAgo(13), today) / 3600).toFixed(1)} hrs past 2 weeks`;
    today_.metric.textContent = clock(todaySeconds);
    today_.sessions.textContent = `${sessionsCount} SESSIONS`;
    today_.record.textContent = `${(lifetime / 3600).toFixed(1)} hrs on record`;
    const active = state.drawing && !state.paused;
    today_.status.textContent = active ? "ACTIVE" : state.paused ? "PAUSED" : "NOT ACTIVE";
    today_.status.classList.toggle("psf-active", active);
    today_.last.textContent = `last session on ${lastSession.getDate()} ${MONTHS[lastSession.getMonth()]}`;
    progressDot.classList.toggle("psf-reached", todaySeconds >= SESSION_MINIMUM);
    levelBadge.textContent = String(levelFor(lifetime / 3600));
  }

  // ----- The graph -----

  const PERIODS = [["Day", "1D"], ["Week", "1W"], ["Month", "1M"], ["3 Months", "3M"], ["6 Months", "6M"], ["1 Year", "1Y"]];
  const periodButtons = {};
  const readoutValue = el("b"), readoutCaption = el("span");
  const chart = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  chart.setAttribute("class", "psf-chart");
  chart.setAttribute("viewBox", "0 0 298 170");
  const graphBlock = el("div", { class: "psf-block psf-graph", "data-name": "graph" },
    strip("Usage over time"),
    el("div", { class: "psf-graph-head" }, `${MONTHS[today.getMonth()]} ${today.getFullYear()}`, el("span", { class: "psf-spacer" }),
      PERIODS.map(([period, label]) => (periodButtons[period] = el("button", { type: "button", class: "psf-period", onclick: () => { state.period = period; renderGraph(); } }, label)))),
    el("div", { class: "psf-readout" }, readoutValue, readoutCaption), chart);

  function series() {
    const now = new Date();
    if (state.period === "Day") {
      return { values: todayHours.map((s) => s / 3600), labels: todayHours.map((_, h) => `${h % 12 || 12} ${h < 12 ? "AM" : "PM"} – ${(h + 1) % 12 || 12} ${(h + 1) % 24 < 12 ? "AM" : "PM"}`),
        ticks: [[0, "12a"], [4, "4a"], [8, "8a"], [12, "12p"], [16, "4p"], [20, "8p"]], caption: "Today", upTo: now.getHours() };
    }
    if (state.period === "Week") {
      const monday = daysAgo((today.getDay() + 6) % 7);
      const days = [...Array(7)].map((_, i) => new Date(monday.getTime() + i * DAY));
      return { values: days.map((d) => dayTotal(d) / 3600), labels: days.map(longDate), ticks: WEEKDAYS.map((w, i) => [i, w]), caption: "This week", upTo: (today.getDay() + 6) % 7 };
    }
    if (state.period === "Month") {
      const days = [...Array(30)].map((_, i) => daysAgo(29 - i));
      return { values: days.map((d) => dayTotal(d) / 3600), labels: days.map(longDate), ticks: days.map((d, i) => [i, String(d.getDate())]).filter((_, i) => i % 5 === 0), caption: "Past 30 days" };
    }
    if (state.period === "1 Year") {
      const months = [...Array(12)].map((_, i) => new Date(today.getFullYear(), today.getMonth() - 11 + i, 1));
      const values = months.map((start) => { const end = new Date(start.getFullYear(), start.getMonth() + 1, 0); return rangeTotal(start, end > today ? today : end) / 3600; });
      return { values, labels: months.map((m) => `${MONTH_NAMES[m.getMonth()]} ${m.getFullYear()}`), ticks: months.map((m, i) => [i, MONTHS[m.getMonth()]]).filter((_, i) => i % 2 === 0), caption: "Past year" };
    }
    const weeks = state.period === "3 Months" ? 13 : 26;
    const ends = [...Array(weeks)].map((_, i) => daysAgo((weeks - 1 - i) * 7));
    return { values: ends.map((end) => rangeTotal(new Date(end.getTime() - 6 * DAY), end) / 3600), labels: ends.map((end) => `Week to ${longDate(end)}`),
      ticks: ends.map((end, i) => [i, `${end.getDate()} ${MONTHS[end.getMonth()]}`]).filter((_, i) => i % (weeks === 13 ? 4 : 8) === 0),
      caption: state.period === "3 Months" ? "Past 90 days" : "Past 180 days" };
  }

  function renderGraph(hover = null) {
    Object.entries(periodButtons).forEach(([period, button]) => button.classList.toggle("psf-selected", period === state.period));
    const data = series();
    const total = data.values.reduce((a, b) => a + b, 0);
    if (hover == null) { readoutValue.textContent = hm(total * 3600); readoutCaption.textContent = data.caption; }
    else { readoutValue.textContent = hm(data.values[hover] * 3600); readoutCaption.textContent = data.labels[hover]; }
    const left = 24, right = 280, top = 10, bottom = 140;
    const peak = Math.max(1, ...data.values);
    const step = peak <= 4 ? 1 : peak <= 8 ? 2 : peak <= 20 ? 5 : peak <= 40 ? 10 : 20;
    const ceiling = Math.ceil(peak / step) * step;
    const x = (i) => left + (data.values.length === 1 ? 0 : i * (right - left) / (data.values.length - 1));
    const y = (v) => bottom - v / ceiling * (bottom - top);
    const shown = data.values.map((v, i) => (data.upTo != null && i > data.upTo ? null : v));
    const points = shown.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    let markup = "";
    for (let v = 0; v <= ceiling; v += step) {
      markup += `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(34,34,34,1)"/><text x="${left - 6}" y="${y(v) + 4}" text-anchor="end">${v}h</text>`;
    }
    data.ticks.forEach(([i, label]) => { markup += `<text x="${x(i)}" y="${bottom + 18}" text-anchor="middle">${label}</text>`; });
    if (points.length) {
      const line = points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
      markup += `<defs><linearGradient id="psf-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3d5ce6" stop-opacity=".45"/><stop offset="1" stop-color="#3d5ce6" stop-opacity="0"/></linearGradient></defs>`;
      markup += `<path d="${line}L${points[points.length - 1][0]},${bottom}L${points[0][0]},${bottom}Z" fill="url(#psf-fill)"/>`;
      markup += `<path d="${line}" stroke="#3d5ce6" stroke-width="2" fill="none" stroke-linejoin="round"/>`;
      const last = points[points.length - 1];
      markup += `<circle cx="${last[0]}" cy="${last[1]}" r="3" fill="#3d5ce6"/>`;
    }
    if (hover != null && shown[hover] != null) {
      markup += `<line x1="${x(hover)}" x2="${x(hover)}" y1="${top - 4}" y2="${bottom}" stroke="#8d9a98" stroke-dasharray="2 3"/>`;
      markup += `<circle cx="${x(hover)}" cy="${y(shown[hover])}" r="3.5" fill="#3d5ce6" stroke="#eef3f1" stroke-width="2"/>`;
    }
    markup += `<rect x="${left}" y="0" width="${right - left}" height="${bottom}" fill="transparent" data-hit=""/>`;
    chart.innerHTML = markup;
    chart.dataset.count = data.values.length;
  }
  chart.addEventListener("pointermove", (event) => {
    const box = chart.getBoundingClientRect();
    const px = (event.clientX - box.left) * 298 / box.width;
    const count = Number(chart.dataset.count);
    const index = Math.round((px - 24) / ((280 - 24) / Math.max(1, count - 1)));
    renderGraph(Math.max(0, Math.min(count - 1, index)));
  });
  chart.addEventListener("pointerleave", () => renderGraph());

  // ----- The calendar -----

  const calTitle = el("span", { class: "psf-cal-title" });
  const calToggle = el("button", { type: "button", class: "psf-cal-button", onclick: () => { state.calendarView = state.calendarView === "Month" ? "Year" : "Month"; renderCalendar(); } }, "month");
  const step = (offset) => {
    const m = state.calendarMonth;
    state.calendarMonth = state.calendarView === "Year" ? new Date(m.getFullYear() + offset, m.getMonth(), 1) : new Date(m.getFullYear(), m.getMonth() + offset, 1);
    renderCalendar();
  };
  const calLegend = el("div", { class: "psf-cal-legend" });
  const calBody = el("div");
  const calendarBlock = el("div", { class: "psf-block psf-calendar", "data-name": "calendar" },
    strip("Calendar"),
    el("div", { class: "psf-cal-head" }, calTitle, calToggle,
      el("button", { type: "button", class: "psf-cal-button", "aria-label": "Back", onclick: () => step(-1) }, "<"),
      el("button", { type: "button", class: "psf-cal-button", "aria-label": "Forward", onclick: () => step(1) }, ">")),
    calLegend, calBody);

  function streaks() {
    let weeks = 0;
    const monday = daysAgo((today.getDay() + 6) % 7);
    for (let w = 0; w < 60; w++) {
      const start = new Date(monday.getTime() - w * 7 * DAY);
      let blue = false;
      for (let d = 0; d < 7; d++) if (dayTotal(new Date(start.getTime() + d * DAY)) >= SESSION_MINIMUM) blue = true;
      if (!blue) break;
      weeks++;
    }
    let rest = 0;
    while (rest < STARTED_DAYS_AGO && dayTotal(daysAgo(rest)) < SESSION_MINIMUM) rest++;
    return [weeks, rest];
  }

  let tip = null;
  const showTip = (target, text, wrap = false) => {
    hideTip();
    tip = el("div", { class: `psf-tip${wrap ? " psf-tip-wrap" : ""}` }, text);
    stage.append(tip);
    const t = target.getBoundingClientRect(), s = stage.getBoundingClientRect();
    tip.style.left = `${Math.max(4, Math.min(t.left - s.left + t.width / 2 - tip.offsetWidth / 2, stage.clientWidth - tip.offsetWidth - 4))}px`;
    // Above what it explains, or below it when there is no room above, and always inside the scene
    const above = t.top - s.top - tip.offsetHeight - 6;
    const below = t.bottom - s.top + 6;
    const top = above >= 4 ? above : Math.min(below, stage.clientHeight - tip.offsetHeight - 4);
    tip.style.top = `${Math.max(4, top)}px`;
  };
  const hideTip = () => { tip?.remove(); tip = null; };

  function renderCalendar() {
    const [weeks, rest] = streaks();
    calLegend.replaceChildren(el("span", { class: "psf-square" }), "15 min+", el("span", { class: "psf-spacer" }),
      `🔥 ${weeks} week streak`, el("span", { style: "width:8px" }), `🌙 ${rest} rest days`);
    const m = state.calendarMonth;
    calToggle.textContent = state.calendarView.toLowerCase();
    if (state.calendarView === "Year") {
      calTitle.textContent = String(m.getFullYear());
      calBody.replaceChildren(el("div", { class: "psf-year" }, MONTHS.map((name, month) => {
        const first = new Date(m.getFullYear(), month, 1);
        const length = new Date(m.getFullYear(), month + 1, 0).getDate();
        const cells = [...Array((first.getDay() + 6) % 7)].map(() => el("i", { class: "psf-none" }));
        for (let d = 1; d <= length; d++) {
          const date = new Date(m.getFullYear(), month, d);
          cells.push(el("i", { class: dayTotal(date) >= SESSION_MINIMUM ? "psf-active" : "" }));
        }
        return el("div", { class: "psf-mini" }, el("b", {}, name), el("div", { class: "psf-mini-grid" }, cells));
      })));
      return;
    }
    calTitle.textContent = `${MONTH_NAMES[m.getMonth()]} ${m.getFullYear()}`;
    const offset = (m.getDay() + 6) % 7;
    const length = new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate();
    const cells = [...Array(offset)].map(() => el("div", { class: "psf-day psf-blank" }));
    for (let d = 1; d <= length; d++) {
      const date = new Date(m.getFullYear(), m.getMonth(), d);
      const seconds = dayTotal(date);
      const rating = ratings.get(key(date));
      const future = date > today;
      const cell = el("div", { class: `psf-day${seconds >= SESSION_MINIMUM ? " psf-active" : ""}${date.getTime() === today.getTime() ? " psf-today-cell" : ""}${future ? " psf-future" : ""}` },
        String(d), rating ? el("span", { class: "psf-rating" }, `★ ${rating}`) : null);
      if (!future) {
        cell.addEventListener("pointerenter", () => showTip(cell, `${longDate(date)} · ${seconds ? hm(seconds) : "nothing tracked"}${rating ? ` · rated ${rating}/10` : ""}`));
        cell.addEventListener("pointerleave", hideTip);
        cell.addEventListener("click", () => showTip(cell, `${longDate(date)} · ${seconds ? hm(seconds) : "nothing tracked"}${rating ? ` · rated ${rating}/10` : ""}`));
      }
      cells.push(cell);
    }
    calBody.replaceChildren(el("div", { class: "psf-weekdays" }, WEEKDAYS.map((w) => el("span", {}, w))), el("div", { class: "psf-days" }, cells));
  }

  // ----- Friends -----

  const copyButton = el("button", { type: "button", class: "psf-copy", title: "Copy your friend code" }, "Copy code");
  const requestsIcon = el("button", { type: "button", class: "psf-icon-button psf-person-icon", title: "Friend requests", hidden: true }, svg(PERSON));
  const addIcon = el("button", { type: "button", class: "psf-icon-button psf-person-icon", title: "Add friend" }, svg(PERSON_PLUS));
  const codeField = el("span", { class: "psf-code-field", hidden: true },
    el("input", { type: "text", maxlength: 11, placeholder: "Friend's code", "aria-label": "Friend's code" }),
    el("button", { type: "button", title: "Add" }, "✓"));
  const friendList = el("div", { class: "psf-friend-list" });
  const friendsBlock = el("div", { class: "psf-block psf-friends", "data-name": "friends" },
    strip("Friends", [codeField, copyButton, requestsIcon, addIcon]), friendList);
  let copyTimer;
  const flash = (content) => {
    copyButton.replaceChildren(...content);
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => copyButton.replaceChildren("Copy code"), 4000);
  };
  copyButton.addEventListener("click", () => {
    navigator.clipboard?.writeText("GLTY-7K2Q").catch(() => {});
    flash([el("b", {}, "GLTY-7K2Q"), el("em", {}, " copied")]);
  });
  const finishAdding = (keep) => {
    const input = codeField.querySelector("input");
    if (keep && input.value.trim()) flash([el("em", {}, "Request sent")]);
    input.value = "";
    codeField.hidden = true;
    copyButton.hidden = false;
    addIcon.classList.remove("psf-open");
  };
  addIcon.addEventListener("click", () => {
    if (!codeField.hidden) return finishAdding(false);
    codeField.hidden = false;
    copyButton.hidden = true;
    addIcon.classList.add("psf-open");
    codeField.querySelector("input").focus();
  });
  codeField.querySelector("input").addEventListener("keydown", (event) => { if (event.key === "Enter") finishAdding(true); if (event.key === "Escape") finishAdding(false); });
  codeField.querySelector("button").addEventListener("click", () => finishAdding(true));
  requestsIcon.addEventListener("click", () => { markUsed("requests"); state.requestsOpen = !state.requestsOpen; renderFriends(); });

  function friendRow(friend) {
    const nameClass = { drawing: "psf-drawing", online: "psf-online", away: "psf-online", offline: "psf-offline" }[friend.presence];
    const name = el("span", { class: `psf-name ${nameClass}` }, friend.name);
    if (friend.presence === "drawing") name.append(el("span", { class: "psf-program" }, friend.program));
    if (friend.presence === "away") name.append(el("span", { class: "psf-zzz", title: "Away" }, el("span", {}, "z"), el("span", {}, "z"), el("span", {}, "z")));
    name.append(el("button", { type: "button", class: "psf-icon-button psf-chevron", title: `${friend.name}'s menu`, onclick: (event) => friendMenu(event.currentTarget, friend) }, svg(ICONS.chevron)));
    const row = el("div", { class: `psf-friend${friend.fresh ? " psf-new" : ""}`, oncontextmenu: (event) => { event.preventDefault(); friendMenu(name, friend); } },
      el("span", { class: "psf-lv" }, String(friend.level)), name,
      el("span", { class: "psf-right", style: friend.presence === "offline" ? "color:var(--psf-muted)" : "" }, `${friend.two.toFixed(1)} hrs past 2 weeks`),
      el("span", {}), el("span", { class: "psf-sub" }, `${friend.today.toFixed(1)}h today`), el("span", { class: "psf-sub-right" }, `${friend.total.toFixed(1)} hrs total`));
    friend.fresh = false;
    return row;
  }

  function renderFriends() {
    requestsIcon.hidden = !state.request;
    requestsIcon.querySelector(".psf-count")?.remove();
    if (state.request) requestsIcon.append(el("span", { class: "psf-count" }, "1"));
    requestsIcon.classList.toggle("psf-open", state.requestsOpen && !!state.request);
    if (state.status === "offline") {
      friendList.replaceChildren(el("div", { class: "psf-offline-note" }, "You're offline, so friends don't see your hours change. Go online from the menu next to your name."));
      return;
    }
    const parts = [];
    if (state.requestsOpen && state.request) {
      parts.push(el("div", { class: "psf-request-row" }, el("span", {}, `${state.request.name} wants to be friends`),
        el("button", { type: "button", class: "psf-accept", onclick: acceptRequest }, "Accept"),
        el("button", { type: "button", class: "psf-decline", onclick: declineRequest }, "Decline")));
    }
    const section = (friend) => (state.favourites.has(friend.code) ? "Favourites" : friend.presence === "offline" ? "Offline" : "Online");
    const order = { Favourites: 0, Online: 1, Offline: 2 };
    const sorted = [...state.friends].sort((a, b) => order[section(a)] - order[section(b)] || b.two - a.two);
    const hasFavourites = sorted.some((f) => section(f) === "Favourites");
    let current = null;
    for (const friend of sorted) {
      const name = section(friend);
      if (name !== current) {
        current = name;
        if (name !== "Online" || hasFavourites) parts.push(el("div", { class: "psf-section" }, `${name} — ${sorted.filter((f) => section(f) === name).length}`));
      }
      parts.push(friendRow(friend));
    }
    friendList.replaceChildren(...parts);
  }

  function requestArrives() {
    // A request shows on the requests icon in the friends strip, with its count, as in the app; its list holds it
    if (state.requestShown) return;
    state.requestShown = true;
    state.request = { code: "SAMM", name: "Sam", level: 16, presence: "drawing", program: "Photoshop", two: 12.7, total: 92.4, today: 1.1 };
    // In the demo the list opens by itself, so the request is seen without hunting for it
    state.requestsOpen = true;
    renderFriends();
    placeHotspots();
  }
  function acceptRequest() {
    if (!state.request) return;
    state.friends.push({ ...state.request, fresh: true });
    state.request = null;
    state.requestsOpen = false;
    renderFriends();
  }
  function declineRequest() {
    state.request = null;
    state.requestsOpen = false;
    renderFriends();
  }

  function friendMenu(anchor, friend) {
    const favourite = state.favourites.has(friend.code);
    openMenu(anchor, [
      el("button", { type: "button", onclick: () => { favourite ? state.favourites.delete(friend.code) : state.favourites.add(friend.code); closeMenu(); renderFriends(); } }, favourite ? "Remove from favourites" : "Add to favourites"),
      el("button", { type: "button", class: "psf-danger", onclick: () => { state.friends = state.friends.filter((f) => f !== friend); closeMenu(); renderFriends(); toast(`${friend.name} removed`); } }, "Remove friend"),
    ]);
  }

  function statusMenu(anchor) {
    markUsed("status");
    const choices = [["online", "Online", ""], ["away", "Away", "Friends see you're away"], ["invisible", "Invisible", "Appear offline, but still see your friends"], ["offline", "Offline", "Stop sharing with friends"]];
    openMenu(anchor, choices.map(([status, name, note]) => el("button", { type: "button", class: status === state.status ? "psf-current" : "",
      onclick: () => { state.status = status; account.classList.toggle("psf-hidden-name", status === "invisible" || status === "offline"); closeMenu(); renderFriends(); } }, name, note ? el("small", {}, note) : null)));
  }

  // ----- Settings -----

  const checkbox = (checked, label, onToggle) => {
    const box = el("button", { type: "button", class: `psf-check${checked ? " psf-checked" : ""}`, role: "checkbox", "aria-checked": String(checked), "aria-label": label });
    box.addEventListener("click", () => { onToggle(); });
    return box;
  };
  const settingsSlider = el("input", { type: "range", min: 0, max: 100, value: 100 - state.transparency, "aria-label": "Transparency, solid at the right" });
  settingsSlider.addEventListener("input", () => setTransparency(100 - Number(settingsSlider.value)));
  const backupStatus = el("div", { class: "psf-backup-line psf-green" }, "Activity backup saved to Google Drive");

  function boxedRow(title, text, control) {
    return el("div", { class: "psf-boxed" }, el("div", { class: "psf-boxed-text" }, el("b", {}, title), el("span", {}, text)), control);
  }

  function renderSettings() {
    const programs = Object.entries(state.programs).map(([program, on]) => el("label", { class: "psf-check-label" },
      program === "Clip Studio Paint" ? "CSP" : program === "Photoshop" ? "PS" : program,
      checkbox(on, program, () => {
        // One program panel is always shown, as in the app
        if (on && Object.values(state.programs).filter(Boolean).length === 1) return toast("One program stays shown");
        state.programs[program] = !on;
        renderSettings();
      })));
    const orientation = el("div", { class: "psf-orientation" },
      el("button", { type: "button", class: `psf-shape psf-tall${state.landscape ? "" : " psf-chosen"}`, "aria-label": "Portrait", onclick: () => chooseOrientation(false) }),
      el("button", { type: "button", class: "psf-shape psf-wide psf-disabled", "aria-label": "Landscape, disabled in the demo", title: "Disabled in the demo",
        onclick: () => toast("Landscape is disabled in the demo. In the app it lays PS Focus out as one wide strip") }));
    const toggle = (key) => checkbox(state[key], key, () => { state[key] = !state[key]; renderSettings(); });
    settingsPage.replaceChildren(
      el("h3", {}, "Settings"),
      el("p", { class: "psf-settings-text" }, "PS Focus counts time in Photoshop, Krita and CSP while they are in front and pauses when you're inactive"),
      el("div", { class: "psf-check-row" }, programs),
      boxedRow("Orientation", "Modules below or beside the program panels", orientation),
      boxedRow("Transparency", "PS Focus turns see-through while the mouse is elsewhere", settingsSlider),
      boxedRow("Start with Windows", "Launch PS Focus when you sign in to Windows", toggle("startWithWindows")),
      boxedRow("Start minimized", "Open PS Focus minimized when launched at sign-in", toggle("startMinimized")),
      el("div", { class: "psf-check-row" },
        el("label", { class: "psf-check-label" }, "Pause tracking", checkbox(state.paused, "Pause tracking", () => { state.paused = !state.paused; renderSettings(); renderToday(); })),
        el("label", { class: "psf-check-label" }, "Disable fanfare sound", toggle("fanfareOff"))),
      el("div", { class: "psf-backups" },
        el("b", {}, "Settings and activity backups"),
        el("span", {}, "Activity is saved locally on this PC and backed up to Google Drive when connected"),
        el("div", { class: "psf-backup-line psf-green" }, "demo@example.com"), backupStatus,
        el("div", { class: "psf-backup-buttons" },
          el("button", { type: "button", onclick: () => { backupStatus.textContent = "Local activity backups saved"; setTimeout(() => (backupStatus.textContent = "Activity backup saved to Google Drive"), 1200); } }, "Back up now"),
          el("button", { type: "button", onclick: () => toast("Switch to another Google account") }, "Switch account"),
          el("button", { type: "button", onclick: () => toast("Log out of Google; your history stays on this PC") }, "Log out"))),
      el("button", { type: "button", class: "psf-exit", onclick: () => toast("Exit closes PS Focus; it counts nothing until you open it again") }, "Exit"));
  }

  function toggleSettings(open = !state.settingsOpen) {
    state.settingsOpen = open;
    if (open) { renderSettings(); markUsed("settings"); }
    // Settings stands under the header, which leaves the landscape column while it is open
    arrange();
    settingsPage.hidden = !open;
    icons.hidden = open;
    blocks.hidden = open;
    level.hidden = open;
    account.hidden = open;
    credit.hidden = !open;
    settingsButton.classList.toggle("psf-open", open);
    if (!open) arrange();
    applySize();
    updateGlass();
  }

  function chooseOrientation(landscape) {
    // Choosing one docks every floating panel and goes back to that layout, as in the app
    Object.keys(state.floating).forEach((name) => dockBack(name, null));
    state.landscape = landscape;
    state.size = null;
    win.classList.toggle("psf-landscape", landscape);
    toggleSettings(false);
  }

  // ----- Showing, hiding and arranging the modules -----

  // The other programs' panels, quieter: this visitor draws in Photoshop
  const otherProgram = (program, two, record, sessions, last) => el("div", { class: "psf-block psf-today", "data-name": program },
    el("div", { class: "psf-strip" }, el("span", {}, program), el("span", { class: "psf-two-week" }, `${two} hrs past 2 weeks`), dockIcon()),
    el("div", { class: "psf-today-body" }, el("div", { class: "psf-metric" }, "0s"),
      el("div", { class: "psf-row" }, el("span", { class: "psf-small" }, `${sessions} SESSIONS`), el("span", {}, `${record} hrs on record`)),
      el("div", { class: "psf-row" }, el("span", { class: "psf-status" }, "NOT ACTIVE"), el("span", {}, `last session on ${last}`))));
  const blockOf = {
    today: todayBlock, graph: graphBlock, calendar: calendarBlock, friends: friendsBlock,
    "Clip Studio Paint": otherProgram("Clip Studio Paint", "1.8", "6.2", 4, `${daysAgo(9).getDate()} ${MONTHS[daysAgo(9).getMonth()]}`),
    Krita: otherProgram("Krita", "0.0", "2.5", 2, `${daysAgo(23).getDate()} ${MONTHS[daysAgo(23).getMonth()]}`),
  };
  const PROGRAM_BLOCKS = { Photoshop: "today", "Clip Studio Paint": "Clip Studio Paint", Krita: "Krita" };
  const PROGRAM_OF = { today: "Photoshop", "Clip Studio Paint": "Clip Studio Paint", Krita: "Krita" };
  // A block is wanted when its program is ticked in Settings, or its module in the icons
  const wanted = (name) => (PROGRAM_OF[name] ? state.programs[PROGRAM_OF[name]] : state.shown[name]);

  function toggleModule(name) {
    state.shown[name] = !state.shown[name];
    if (state.floating[name]) state.floating[name].panel.hidden = !wanted(name);
    arrange();
    if (name === "friends" && state.shown.friends && !state.requestShown) setTimeout(requestArrives, 1600);
  }

  function arrange(placeholderAt = null, placeholderHeight = 0, placeholderWidth = 300) {
    Object.entries(iconButtons).forEach(([name, button]) => button.classList.toggle("psf-on", state.shown[name]));
    // A floating panel shows while its block is wanted
    Object.entries(state.floating).forEach(([name, f]) => (f.panel.hidden = !wanted(name)));
    const docked = state.order.filter((name) => wanted(name) && !state.floating[name]);
    const children = docked.map((name) => blockOf[name]);
    if (state.landscape && !state.settingsOpen) {
      // The header and icons head the column of the Photoshop panel, or the first program panel shown, wherever it
      // stands; with none in the window they stand first on their own, as in the app
      const anchor = docked.find((name) => name === "today") || docked.find((name) => PROGRAM_OF[name]);
      if (anchor) {
        anchorColumn.replaceChildren(header, icons, blockOf[anchor]);
        children[docked.indexOf(anchor)] = anchorColumn;
      } else {
        anchorColumn.replaceChildren(header, icons);
        children.unshift(anchorColumn);
      }
    } else {
      win.insertBefore(header, blocks);
      win.insertBefore(icons, blocks);
    }
    if (placeholderAt != null) {
      const holder = el("div", { class: "psf-placeholder" });
      holder.style.height = `${placeholderHeight}px`;
      if (state.landscape) holder.style.width = `${placeholderWidth - 2}px`;
      children.splice(placeholderAt, 0, holder);
    }
    blocks.replaceChildren(...children);
    fitStage();
  }

  const anchorColumn = el("div", { class: "psf-anchor-column" });

  function fitStage() {
    const panels = Object.values(state.floating).filter((f) => !f.panel.hidden);
    const bottom = Math.max(win.offsetTop + win.offsetHeight, ...panels.map((f) => f.panel.offsetTop + f.panel.offsetHeight));
    // The scene holds the painting whole on a desktop, and grows only if PS Focus is dragged further down
    stage.style.minHeight = `${Math.max(touch.matches ? 640 : 1148, bottom + 24)}px`;
    // On the narrowest phones the window, 300 pixels wide like the app's, is shrunk to fit
    const room = stage.clientWidth - 16;
    win.style.transform = touch.matches ? `translateX(-50%)${room < 300 ? ` scale(${room / 300})` : ""}` : "";
    win.style.transformOrigin = "top center";
    // A wide window keeps inside the scene, moving left as far as it must
    if (!touch.matches && win.offsetLeft + win.offsetWidth > stage.clientWidth - 8) {
      win.style.left = `${Math.max(8, stage.clientWidth - 8 - win.offsetWidth)}px`;
    }
    placeHotspots();
  }
  window.addEventListener("resize", fitStage);
  // Fonts arriving late change sizes, and so where the dots go
  document.fonts?.ready.then(fitStage);

  // ----- Panels: pulled out by their title, snapped beside the window, dropped back in -----

  function rect(node) {
    const r = node.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return { left: r.left - s.left, top: r.top - s.top, right: r.right - s.left, bottom: r.bottom - s.top, width: r.width, height: r.height };
  }

  // Whether the header stands first on its own in landscape, with no program panel in the window to head
  const headerAlone = () => anchorColumn.parentNode === blocks && anchorColumn.children.length === 2;

  function dockSlot(pointerX, pointerY) {
    // Where among the window's blocks a panel dropped here goes: in landscape by where across, in portrait by how far
    // down; never before the header standing on its own
    const docked = [...blocks.children].filter((child) => !child.classList.contains("psf-placeholder"));
    const least = headerAlone() ? 1 : 0;
    let slot = docked.length;
    docked.forEach((child, index) => {
      const r = rect(child);
      const before = state.landscape ? pointerX < r.left + r.width / 2 : pointerY < r.top + r.height / 2;
      if (slot === docked.length && before) slot = Math.max(least, index);
    });
    return slot;
  }

  function floatOut(name, left, top) {
    const block = blockOf[name];
    const panel = el("div", { class: "psf-floating" });
    panel.append(block);
    stage.append(panel);
    state.floating[name] = { panel, attached: false };
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    arrange();
    if (name === "graph") renderGraph();
    return panel;
  }

  function dockBack(name, slot) {
    const floating = state.floating[name];
    if (!floating) return;
    delete state.floating[name];
    floating.panel.remove();
    // The blocks in the window, in order, which the slot counts, past the header if it stands on its own
    const docked = state.order.filter((n) => wanted(n) && !state.floating[n] && n !== name);
    const before = slot == null ? undefined : docked[Math.max(0, slot - (headerAlone() ? 1 : 0))];
    state.order = state.order.filter((n) => n !== name);
    state.order.splice(before ? state.order.indexOf(before) : state.order.length, 0, name);
    arrange();
    updateGlass();
  }

  const SNAP_DISTANCE = 22;
  const shownPanels = () => Object.values(state.floating).filter((f) => !f.panel.hidden).map((f) => f.panel);

  function touching(a, b) {
    // Two windows touch when an edge of one lies on an edge of the other, along a shared stretch
    const t = 2;
    const across = a.top < b.bottom - t && b.top < a.bottom - t;
    const along = a.left < b.right - t && b.left < a.right - t;
    return (across && (Math.abs(a.right - b.left) <= t || Math.abs(b.right - a.left) <= t))
      || (along && (Math.abs(a.bottom - b.top) <= t || Math.abs(b.bottom - a.top) <= t));
  }

  function groupOf(start) {
    // Everything snapped to this window or panel, directly or through another
    const nodes = [win, ...shownPanels()];
    const group = new Set([start]);
    const queue = [start];
    while (queue.length) {
      const r = rect(queue.pop());
      for (const node of nodes) if (!group.has(node) && touching(r, rect(node))) { group.add(node); queue.push(node); }
    }
    return group;
  }

  function refreshAttached() {
    const main = groupOf(win);
    Object.values(state.floating).forEach((f) => (f.attached = main.has(f.panel)));
  }

  function snapOffset(node, exclude) {
    // How far to move a panel, or a group led by it, for it to snap to the nearest window or panel not in the group:
    // side by side, its top lined up, or one above the other, its left lined up
    const p = rect(node);
    let dx = null, dy = null, bestX = SNAP_DISTANCE, bestY = SNAP_DISTANCE;
    for (const target of [win, ...shownPanels()]) {
      if (exclude.has(target)) continue;
      const t = rect(target);
      const across = p.top < t.bottom + SNAP_DISTANCE && t.top < p.bottom + SNAP_DISTANCE;
      const along = p.left < t.right + SNAP_DISTANCE && t.left < p.right + SNAP_DISTANCE;
      if (across) {
        for (const x of [t.right - p.left, t.left - p.right]) {
          if (Math.abs(x) < bestX) {
            bestX = Math.abs(x); dx = x;
            const lineUp = [t.top - p.top, t.bottom - p.bottom].find((y) => Math.abs(y) < SNAP_DISTANCE);
            dy = lineUp ?? (Math.abs(bestY) < SNAP_DISTANCE && dy != null ? dy : 0);
          }
        }
      }
      if (along) {
        for (const y of [t.bottom - p.top, t.top - p.bottom]) {
          if (Math.abs(y) < bestY) {
            bestY = Math.abs(y); dy = y;
            const lineUp = [t.left - p.left, t.right - p.right].find((x) => Math.abs(x) < SNAP_DISTANCE);
            if (dx == null || bestX >= SNAP_DISTANCE) dx = lineUp ?? 0;
          }
        }
      }
    }
    return [dx ?? 0, dy ?? 0];
  }

  function shift(node, dx, dy) {
    node.style.left = `${node.offsetLeft + dx}px`;
    node.style.top = `${Math.max(0, node.offsetTop + dy)}px`;
  }

  function settle(leader, group) {
    // After a drag: the leader snaps to whatever is near, taking its group with it, and the groups are worked out again
    const [dx, dy] = snapOffset(leader, group);
    if (dx || dy) group.forEach((node) => shift(node, dx, dy));
    refreshAttached();
    fitStage();
    updateGlass();
  }

  function moveFloating(panel, event) {
    // A floating panel taken by anything but its title moves with everything snapped to it, the window included
    const group = groupOf(panel);
    const start = { x: event.clientX, y: event.clientY, places: [...group].map((node) => [node, node.offsetLeft, node.offsetTop]) };
    const target = event.target;
    try { target.setPointerCapture(event.pointerId); } catch (error) { /* moves still reach it */ }
    const move = (moveEvent) => {
      const dx = moveEvent.clientX - start.x, dy = moveEvent.clientY - start.y;
      start.places.forEach(([node, left, top]) => { node.style.left = `${left + dx}px`; node.style.top = `${Math.max(0, top + dy)}px`; });
      hideTip();
    };
    const up = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", up);
      target.removeEventListener("pointercancel", up);
      settle(panel, group);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", up);
    target.addEventListener("pointercancel", up);
  }

  function snap(panel) {
    settle(panel, new Set([panel]));
    return groupOf(win).has(panel);
  }

  grip.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    const start = { x: event.clientX, y: event.clientY, width: win.offsetWidth, height: win.offsetHeight };
    // Never smaller than the header with the first program panel under it, as the app keeps it in view
    const least = state.landscape ? 300 : titlebar.offsetHeight + header.offsetHeight + icons.offsetHeight + todayBlock.offsetHeight + 12;
    const most = state.landscape ? blocks.scrollWidth : win.scrollHeight;
    try { grip.setPointerCapture(event.pointerId); } catch (error) { /* moves still reach it */ }
    const move = (moveEvent) => {
      if (state.landscape) state.size = Math.max(least, Math.min(most, start.width + moveEvent.clientX - start.x));
      else state.size = Math.max(least, Math.min(most, start.height + moveEvent.clientY - start.y));
      // Dragged back out as far as everything goes, the window follows what it shows again
      if (state.size >= most) state.size = null;
      applySize();
    };
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); grip.removeEventListener("pointercancel", up); };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  });

  function applySize() {
    win.style.height = !state.landscape && state.size && !state.settingsOpen ? `${state.size}px` : "";
    win.style.width = state.landscape && state.size && !state.settingsOpen ? `${state.size}px` : "";
    win.classList.toggle("psf-clipped", !!state.size && !state.settingsOpen);
    fitStage();
  }

  // What a press keeps for itself, rather than moving the window: buttons and fields, calendar days, the chart's
  // readout, the friends list, which scrolls, a friend request, and a panel's title, which takes the panel
  const CLICKED = "button, input, label, .psf-day, .psf-chart, .psf-friend-list, .psf-strip, .psf-grip, .psf-account-name";

  win.addEventListener("pointerdown", (event) => {
    if (touch.matches || event.button !== 0 || event.target.closest(CLICKED)) return;
    const start = { x: event.clientX, y: event.clientY, left: win.offsetLeft, top: win.offsetTop };
    // Everything snapped to the window, directly or through another panel, moves with it
    const group = groupOf(win);
    const attached = [...group].filter((node) => node !== win).map((node) => ({ panel: node, left: node.offsetLeft, top: node.offsetTop }));
    const grip = event.target;
    try { grip.setPointerCapture(event.pointerId); } catch (error) { /* moves still reach it */ }
    const move = (moveEvent) => {
      const dx = Math.max(-start.left, Math.min(moveEvent.clientX - start.x, stage.clientWidth - win.offsetWidth - start.left));
      const dy = Math.max(-start.top, moveEvent.clientY - start.y);
      win.style.left = `${start.left + dx}px`;
      win.style.top = `${start.top + dy}px`;
      attached.forEach((a) => { a.panel.style.left = `${a.left + dx}px`; a.panel.style.top = `${a.top + dy}px`; });
      fitStage();
      hideTip();
    };
    const up = () => {
      grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); grip.removeEventListener("pointercancel", up);
      // The window snaps to a panel it was brought up to, as a panel snaps to it
      if (!touch.matches) settle(win, group);
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  });

  stage.addEventListener("pointerdown", (event) => {
    const dock = event.target.closest("[data-dock]");
    if (dock) {
      const name = dock.closest(".psf-block").dataset.name;
      dockBack(name, null);
      return;
    }
    const floatingPanel = event.target.closest(".psf-floating");
    if (floatingPanel && !touch.matches && event.button === 0 && !event.target.closest(CLICKED)) return moveFloating(floatingPanel, event);
    const stripNode = event.target.closest(".psf-strip");
    if (!stripNode || touch.matches || event.button !== 0 || event.target.closest("button, input")) return;
    const block = stripNode.closest(".psf-block");
    const name = block.dataset.name;
    const start = { x: event.clientX, y: event.clientY };
    const blockRect = rect(block);
    const grab = { x: start.x - stage.getBoundingClientRect().left - blockRect.left, y: start.y - stage.getBoundingClientRect().top - blockRect.top };
    let panel = state.floating[name]?.panel || null;
    let dragging = false;
    let slot = null;
    // Kept on the strip as it moves, so the drag carries on outside it; a browser refusing still lets the drag work
    try { stripNode.setPointerCapture(event.pointerId); } catch (error) { /* moves still reach the strip */ }
    const move = (moveEvent) => {
      const s = stage.getBoundingClientRect();
      const x = moveEvent.clientX - s.left, y = moveEvent.clientY - s.top;
      if (!dragging) {
        if (Math.hypot(moveEvent.clientX - start.x, moveEvent.clientY - start.y) < 6) return;
        dragging = true;
        markUsed("drag");
        if (!panel) panel = floatOut(name, x - grab.x, y - grab.y);
        panel.classList.add("psf-dragging");
      }
      panel.style.left = `${x - grab.x}px`;
      panel.style.top = `${y - grab.y}px`;
      // Over the window, a blue space shows where it would go back in
      const w = rect(win);
      const over = x > w.left && x < w.right && y > w.top && y < w.bottom + 30;
      const newSlot = over ? dockSlot(x, y) : null;
      if (newSlot !== slot) { slot = newSlot; arrange(slot, panel.offsetHeight - 2, panel.offsetWidth); }
      state.pointerInside.main = true;
      updateGlass();
    };
    const up = () => {
      stripNode.removeEventListener("pointermove", move);
      stripNode.removeEventListener("pointerup", up);
      stripNode.removeEventListener("pointercancel", up);
      if (!dragging) return;
      panel.classList.remove("psf-dragging");
      if (slot != null) dockBack(name, slot);
      else { snap(panel); arrange(); }
      updateGlass();
    };
    stripNode.addEventListener("pointermove", move);
    stripNode.addEventListener("pointerup", up);
    stripNode.addEventListener("pointercancel", up);
  });

  // ----- Glass: backgrounds fade while the pointer is elsewhere, text staying solid with a soft glow -----

  let pointer = null;
  function updateGlass() {
    const alpha = 1 - state.transparency / 100 * (1 - GLASS_MIN);
    const glow = (1 - alpha) * 0.67;
    const inside = (node) => pointer && (() => { const r = rect(node); return pointer.x >= r.left && pointer.x <= r.right && pointer.y >= r.top && pointer.y <= r.bottom; })();
    const set = (node, solid) => { node.style.setProperty("--a", solid ? 1 : alpha); node.style.setProperty("--g", solid ? 0 : glow); };
    // Windows snapped together count as one: the pointer over any of them makes them all solid
    const done = new Set();
    let mainSolid = true;
    for (const start of [win, ...shownPanels()]) {
      if (done.has(start)) continue;
      const group = groupOf(start);
      group.forEach((node) => done.add(node));
      const withMain = group.has(win);
      const solid = touch.matches ? !stageAway : [...group].some(inside) || (withMain && !!menu);
      if (withMain) mainSolid = solid;
      group.forEach((node) => set(node, solid));
    }
    if (!mainSolid && (touch.matches ? stageAway : pointer && inside(canvas))) markUsed("fade");
  }
  let stageAway = false;
  stage.addEventListener("pointermove", (event) => {
    const s = stage.getBoundingClientRect();
    pointer = { x: event.clientX - s.left, y: event.clientY - s.top };
    updateGlass();
  });
  stage.addEventListener("pointerleave", () => { pointer = null; updateGlass(); });
  // On a touch screen there is no pointer to move away: a tap on the painting fades PS Focus, a tap on it brings it back
  stage.addEventListener("click", (event) => {
    if (!touch.matches) return;
    stageAway = !event.target.closest(".psf-window, .psf-floating, .psf-menu");
    updateGlass();
  });

  // ----- Tips: a pulsing dot on each main feature, explained under the pointer, gone once the feature is used. A few
  // at a time, in this order, so the demo grows quieter as it is learnt, as the app does -----

  const HOTSPOTS = [
    { id: "timer", target: () => today_.metric, at: (r) => [r.left + 196, r.top + 6],
      text: "Counts by itself while your art app is in front, and stops when you step away. Try the switch above." },
    { id: "icons", target: () => icons, at: (r) => [r.right - 86, r.top - 4], text: "Show or hide the graph, calendar and friends." },
    { id: "drag", target: () => [...blocks.querySelectorAll(".psf-block:not(.psf-today) .psf-strip")][0], at: (r) => [r.left + 140, r.top + 8],
      text: "Drag a panel out by its title to keep it beside your canvas. Drop it back in, or press « on it." },
    { id: "fade", target: () => canvas, at: (r) => [r.left + 28, r.top + 28],
      text: "Move your mouse onto the painting: PS Focus fades so your art shows through, and comes back when you point at it." },
    { id: "requests", target: () => (requestsIcon.hidden ? null : requestsIcon), at: (r) => [r.left - 4, r.top - 4],
      text: "Someone wants to be friends: open your requests to accept or decline." },
    { id: "status", target: () => statusButton, at: (r) => [r.right - 2, r.top - 6], text: "Show friends you're Away, or go Invisible or Offline." },
    { id: "settings", target: () => settingsButton, at: (r) => [r.right - 4, r.top - 6], text: "Settings: your programs, transparency, and backups." },
    { id: "rename", target: () => accountName, at: (r) => [r.left - 2, r.top - 4], text: "Double-click your name to change what friends see." },
  ];
  const TIPS_AT_ONCE = 3;
  const used = new Set();
  const hotspots = el("div", { class: "psf-hotspots" });
  stage.append(hotspots);

  function markUsed(id) {
    if (used.has(id)) return;
    used.add(id);
    hideTip();
    placeHotspots();
  }

  function placeHotspots() {
    if (!hotspots.isConnected) return;
    const shown = HOTSPOTS.filter((spot) => {
      if (used.has(spot.id)) return false;
      const target = spot.target();
      return target && target.offsetParent !== null && !target.closest("[hidden]");
    }).slice(0, TIPS_AT_ONCE);
    hotspots.replaceChildren(...shown.map((spot) => {
      const [x, y] = spot.at(rect(spot.target()));
      const dot = el("button", { type: "button", class: "psf-hotspot", "aria-label": spot.text });
      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;
      dot.addEventListener("pointerenter", () => showTip(dot, spot.text, true));
      dot.addEventListener("pointerleave", hideTip);
      dot.addEventListener("click", () => showTip(dot, spot.text, true));
      return dot;
    }));
  }

  // ----- The clock -----

  setInterval(() => {
    if (!state.drawing || state.paused) return;
    const hour = new Date().getHours();
    todayHours[hour] += 1;
    lifetime += 1;
    renderToday();
    if (state.shown.graph && (state.period === "Day" || state.period === "Week") && !chart.matches(":hover")) renderGraph();
  }, 1000);

  // ----- What each panel is for, under the pointer on its title, after a moment -----

  const PANEL_TIPS = {
    today: "Today's drawing time in Photoshop, counted for you, with your past two weeks and all your hours.",
    "Clip Studio Paint": "Your time in Clip Studio Paint, counted the same way. Each program you use gets its own panel.",
    Krita: "Your time in Krita, counted the same way. Each program you use gets its own panel.",
    graph: "When and how much you draw, from today back to a year, so you can see your rhythm.",
    calendar: "Every day you draw 15 minutes or more turns blue. Keep your streak going, and rate your days.",
    friends: "Your friends' hours and who's drawing right now, for a little friendly motivation.",
  };
  let panelTipTimer;
  Object.entries(PANEL_TIPS).forEach(([name, text]) => {
    const title = blockOf[name].querySelector(".psf-strip");
    title.addEventListener("pointerenter", () => {
      clearTimeout(panelTipTimer);
      panelTipTimer = setTimeout(() => { if (title.matches(":hover")) showTip(title, text, true); }, 500);
    });
    title.addEventListener("pointerleave", () => { clearTimeout(panelTipTimer); hideTip(); });
    title.addEventListener("pointerdown", () => { clearTimeout(panelTipTimer); hideTip(); });
  });

  renderToday();
  renderGraph();
  renderCalendar();
  renderFriends();
  arrange();
  updateGlass();

  // For checking states while the page is built, from the browser's console
  window.psfDemo = { state, toggleModule, toggleSettings, chooseOrientation, requestArrives, floatOut, snap, updateGlass, renderCalendar, renderGraph, setPointer: (x, y) => { pointer = x == null ? null : { x, y }; updateGlass(); } };
})();
