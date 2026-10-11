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

  // ----- Made-up history: ten weeks and more of believable sessions, the same on every visit -----

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
  for (let ago = 400; ago >= 1; ago--) {
    const day = daysAgo(ago);
    const weekend = day.getDay() === 0 || day.getDay() === 6;
    if (random() < (weekend ? 0.45 : 0.2)) continue;
    const hours = new Array(24).fill(0);
    let hour = pick([9, 10, 13, 14, 19, 20]);
    let remaining = pick([35, 50, 75, 90, 110, 140, 170, 205]) * 60;
    while (remaining > 0 && hour < 24) {
      const seconds = Math.min(remaining, 2400 + Math.floor(random() * 1200));
      hours[hour++] = seconds;
      remaining -= seconds;
    }
    history.set(key(day), hours);
    if (random() < 0.4) ratings.set(key(day), 5 + Math.floor(random() * 5));
  }
  const todayHours = new Array(24).fill(0);
  todayHours[9] = 2900; todayHours[10] = 3400; todayHours[11] = 2170;
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
    shown: { graph: true, calendar: false, friends: false },
    order: ["today", "graph", "calendar", "friends"],
    floating: {},
    status: "online",
    favourites: new Set(),
    friends: [
      { code: "MIAA", name: "Mia", level: 47, presence: "drawing", program: "Krita", two: 41.6, total: 1288.4, today: 2.4 },
      { code: "LEOO", name: "Leo", level: 33, presence: "online", two: 27.9, total: 655.0, today: 1.1 },
      { code: "AVAA", name: "Ava", level: 26, presence: "away", two: 18.3, total: 402.7, today: 0.0 },
      { code: "NOAH", name: "Noah", level: 17, presence: "offline", two: 9.4, total: 210.2, today: 0.0 },
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
  const slider = el("input", { type: "range", min: 0, max: 100, value: state.transparency, "aria-label": "Transparency" });
  const controls = el("div", { class: "psf-controls" },
    drawingSwitch,
    el("label", { class: "psf-slider" }, "Transparency", slider),
    el("span", { class: "psf-hint" }, touch.matches ? "Tap the painting to let PS Focus fade" : "Drag a panel out by its title · move your mouse away to see it fade"));
  const stage = el("div", { class: "psf-stage" });
  const canvas = el("div", { class: "psf-canvas", role: "img", "aria-label": "A painting on the art app's canvas" });
  canvas.style.backgroundImage = `url("${PAINTING}")`;
  stage.append(canvas);
  root.append(controls, stage);

  drawingSwitch.addEventListener("click", () => {
    state.drawing = !state.drawing;
    drawingSwitch.setAttribute("aria-checked", String(state.drawing));
    renderToday();
  });
  slider.addEventListener("input", () => { state.transparency = Number(slider.value); updateGlass(); });

  // ----- The window -----

  const win = el("div", { class: "psf-window", role: "application", "aria-label": "PS Focus demo" });
  const titlebar = el("div", { class: "psf-titlebar" },
    el("img", { src: LOGO, alt: "" }), "PS Focus", el("span", { class: "psf-spacer" }),
    el("button", { type: "button", title: "Minimise", onclick: () => toast("In the app this minimises PS Focus") }, "–"),
    el("button", { type: "button", class: "psf-close", title: "Close to the tray", onclick: () => toast("PS Focus keeps counting in the tray when closed") }, "✕"));
  const progressDot = el("span", { class: "psf-dot" });
  const levelBadge = el("span", { class: "psf-badge" });
  const accountName = el("span", {}, "gilty");
  const statusButton = el("button", { type: "button", class: "psf-icon-button psf-chevron", title: "Status", onclick: (event) => statusMenu(event.currentTarget) }, svg(ICONS.chevron));
  const account = el("div", { class: "psf-account" }, progressDot, accountName, statusButton);
  const settingsButton = el("button", { type: "button", class: "psf-icon-button psf-settings", title: "Settings", onclick: (event) => settingsMenu(event.currentTarget) }, "···");
  const header = el("div", { class: "psf-header" }, el("div", { class: "psf-level" }, "Level", levelBadge), account, settingsButton);
  const iconButtons = {};
  const icons = el("div", { class: "psf-icons" }, ["graph", "calendar", "friends"].map((name) => {
    iconButtons[name] = el("button", { type: "button", class: "psf-icon-button", title: `Show or hide ${name}`, onclick: () => toggleModule(name) }, svg(ICONS[name]));
    return iconButtons[name];
  }));
  const blocks = el("div", { class: "psf-blocks" });
  win.append(titlebar, header, icons, blocks);
  stage.append(win);

  const strip = (title, extra = []) => el("div", { class: "psf-strip" }, el("span", {}, title), el("span", { class: "psf-spacer" }), extra,
    el("button", { type: "button", class: "psf-icon-button psf-dock", title: "Back into the window", "data-dock": "" }, svg(ICONS.dock)));

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
    el("div", { class: "psf-strip" }, el("span", {}, "Photoshop"), today_.two),
    el("div", { class: "psf-today-body" }, today_.metric,
      el("div", { class: "psf-row" }, today_.sessions, today_.record),
      el("div", { class: "psf-row" }, today_.status, today_.last)));
  const sessionsCount = [...history.values()].filter((hours) => hours.reduce((a, b) => a + b, 0) >= SESSION_MINIMUM).length;
  const lastSession = (() => { for (let ago = 1; ago < 400; ago++) if (dayTotal(daysAgo(ago)) > 0) return daysAgo(ago); return today; })();

  function renderToday() {
    const todaySeconds = dayTotal(today);
    today_.two.textContent = `${(rangeTotal(daysAgo(13), today) / 3600).toFixed(1)} hrs past 2 weeks`;
    today_.metric.textContent = clock(todaySeconds);
    today_.sessions.textContent = `${sessionsCount} SESSIONS`;
    today_.record.textContent = `${(lifetime / 3600).toFixed(1)} hrs on record`;
    today_.status.textContent = state.drawing ? "ACTIVE" : "NOT ACTIVE";
    today_.status.classList.toggle("psf-active", state.drawing);
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
    while (rest < 400 && dayTotal(daysAgo(rest)) < SESSION_MINIMUM) rest++;
    return [weeks, rest];
  }

  let tip = null;
  const showTip = (target, text) => {
    hideTip();
    tip = el("div", { class: "psf-tip" }, text);
    stage.append(tip);
    const t = target.getBoundingClientRect(), s = stage.getBoundingClientRect();
    tip.style.left = `${Math.max(4, Math.min(t.left - s.left + t.width / 2 - tip.offsetWidth / 2, stage.clientWidth - tip.offsetWidth - 4))}px`;
    tip.style.top = `${t.top - s.top - tip.offsetHeight - 6}px`;
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
  requestsIcon.addEventListener("click", () => { state.requestsOpen = !state.requestsOpen; renderFriends(); });

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

  let popup = null;
  const closePopup = () => { popup?.remove(); popup = null; };
  function requestArrives() {
    if (state.requestShown) return;
    state.requestShown = true;
    state.request = { code: "SAMM", name: "Sam", level: 39, presence: "drawing", program: "Photoshop", two: 33.0, total: 870.5, today: 1.6 };
    renderFriends();
    popup = el("div", { class: "psf-popup", role: "dialog", "aria-label": "Friend request" },
      el("button", { type: "button", class: "psf-x", title: "Later", onclick: closePopup }, "✕"),
      el("b", {}, "Sam"), el("span", {}, "wants to be friends on PS Focus"),
      el("div", { class: "psf-popup-buttons" },
        el("button", { type: "button", class: "psf-accept", onclick: acceptRequest }, "Accept"),
        el("button", { type: "button", class: "psf-decline", onclick: declineRequest }, "Decline")));
    win.append(popup);
  }
  function acceptRequest() {
    if (!state.request) return;
    state.friends.push({ ...state.request, fresh: true });
    state.request = null;
    state.requestsOpen = false;
    closePopup();
    renderFriends();
  }
  function declineRequest() {
    state.request = null;
    state.requestsOpen = false;
    closePopup();
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
    const choices = [["online", "Online", ""], ["away", "Away", "Friends see you're away"], ["invisible", "Invisible", "Appear offline, but still see your friends"], ["offline", "Offline", "Stop sharing with friends"]];
    openMenu(anchor, choices.map(([status, name, note]) => el("button", { type: "button", class: status === state.status ? "psf-current" : "",
      onclick: () => { state.status = status; account.classList.toggle("psf-hidden-name", status === "invisible" || status === "offline"); closeMenu(); renderFriends(); } }, name, note ? el("small", {}, note) : null)));
  }

  function settingsMenu(anchor) {
    const range = el("input", { type: "range", min: 0, max: 100, value: state.transparency });
    range.addEventListener("input", () => { state.transparency = Number(range.value); slider.value = range.value; updateGlass(); });
    openMenu(anchor, [el("label", {}, "Transparency", range)]);
    menu.style.left = `${Math.max(4, parseFloat(menu.style.left) - 120)}px`;
  }

  // ----- Showing, hiding and arranging the modules -----

  const blockOf = { today: todayBlock, graph: graphBlock, calendar: calendarBlock, friends: friendsBlock };

  function toggleModule(name) {
    state.shown[name] = !state.shown[name];
    if (state.floating[name]) state.floating[name].panel.hidden = !state.shown[name];
    arrange();
    if (name === "friends" && state.shown.friends && !state.requestShown) setTimeout(requestArrives, 1600);
  }

  function arrange(placeholderAt = null, placeholderHeight = 0) {
    Object.entries(iconButtons).forEach(([name, button]) => button.classList.toggle("psf-on", state.shown[name]));
    const docked = state.order.filter((name) => (name === "today" || state.shown[name]) && !state.floating[name]);
    const children = docked.map((name) => blockOf[name]);
    if (placeholderAt != null) {
      const holder = el("div", { class: "psf-placeholder" });
      holder.style.height = `${placeholderHeight}px`;
      children.splice(placeholderAt, 0, holder);
    }
    blocks.replaceChildren(...children);
    fitStage();
  }

  function fitStage() {
    const panels = Object.values(state.floating).filter((f) => !f.panel.hidden);
    const bottom = Math.max(win.offsetTop + win.offsetHeight, ...panels.map((f) => f.panel.offsetTop + f.panel.offsetHeight));
    stage.style.minHeight = `${Math.max(640, bottom + 24)}px`;
    // On the narrowest phones the window, 300 pixels wide like the app's, is shrunk to fit
    const room = stage.clientWidth - 16;
    win.style.transform = touch.matches ? `translateX(-50%)${room < 300 ? ` scale(${room / 300})` : ""}` : "";
    win.style.transformOrigin = "top center";
  }
  window.addEventListener("resize", fitStage);

  // ----- Panels: pulled out by their title, snapped beside the window, dropped back in -----

  function rect(node) {
    const r = node.getBoundingClientRect(), s = stage.getBoundingClientRect();
    return { left: r.left - s.left, top: r.top - s.top, right: r.right - s.left, bottom: r.bottom - s.top, width: r.width, height: r.height };
  }

  function dockSlot(pointerY) {
    // Where among the window's blocks a panel dropped at this height goes, the program panel always first
    const docked = [...blocks.children].filter((child) => !child.classList.contains("psf-placeholder"));
    let slot = docked.length;
    docked.forEach((child, index) => { const r = rect(child); if (slot === docked.length && pointerY < r.top + r.height / 2) slot = Math.max(1, index); });
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
    const docked = state.order.filter((n) => (n === "today" || state.shown[n]) && !state.floating[n] && n !== name);
    const after = docked[slot - 1];
    state.order = state.order.filter((n) => n !== name);
    state.order.splice(after ? state.order.indexOf(after) + 1 : state.order.length, 0, name);
    arrange();
    updateGlass();
  }

  function snap(panel) {
    // Within a short distance of the window's side and level with it, a panel snaps to that side and to its top
    const p = rect(panel), w = rect(win), near = 22;
    let left = p.left, top = p.top, attached = false;
    const overlaps = p.bottom > w.top && p.top < w.bottom;
    if (overlaps && Math.abs(p.left - w.right) < near) { left = w.right; attached = true; }
    else if (overlaps && Math.abs(p.right - w.left) < near) { left = w.left - p.width; attached = true; }
    if (attached && Math.abs(p.top - w.top) < near) top = w.top;
    left = Math.max(0, Math.min(left, stage.clientWidth - p.width));
    top = Math.max(0, top);
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    return attached;
  }

  stage.addEventListener("pointerdown", (event) => {
    const dock = event.target.closest("[data-dock]");
    if (dock) {
      const name = dock.closest(".psf-block").dataset.name;
      dockBack(name, null);
      return;
    }
    const stripNode = event.target.closest(".psf-strip");
    if (!stripNode || touch.matches || event.button !== 0 || event.target.closest("button, input")) return;
    const block = stripNode.closest(".psf-block");
    const name = block.dataset.name;
    if (name === "today") return;
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
        if (!panel) panel = floatOut(name, x - grab.x, y - grab.y);
        panel.classList.add("psf-dragging");
      }
      panel.style.left = `${x - grab.x}px`;
      panel.style.top = `${y - grab.y}px`;
      // Over the window, a blue space shows where it would go back in
      const w = rect(win);
      const over = x > w.left && x < w.right && y > w.top && y < w.bottom + 30;
      const newSlot = over ? dockSlot(y) : null;
      if (newSlot !== slot) { slot = newSlot; arrange(slot, panel.offsetHeight - 2); }
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
      else { state.floating[name].attached = snap(panel); arrange(); }
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
    const attached = Object.values(state.floating).filter((f) => f.attached && !f.panel.hidden);
    const mainSolid = touch.matches ? !stageAway : inside(win) || attached.some((f) => inside(f.panel)) || !!menu;
    const set = (node, solid) => { node.style.setProperty("--a", solid ? 1 : alpha); node.style.setProperty("--g", solid ? 0 : glow); };
    set(win, mainSolid);
    Object.values(state.floating).forEach((f) => set(f.panel, f.attached ? mainSolid : (touch.matches ? !stageAway : inside(f.panel))));
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

  // ----- The clock -----

  setInterval(() => {
    if (!state.drawing) return;
    const hour = new Date().getHours();
    todayHours[hour] += 1;
    lifetime += 1;
    renderToday();
    if (state.shown.graph && (state.period === "Day" || state.period === "Week") && !chart.matches(":hover")) renderGraph();
  }, 1000);

  renderToday();
  renderGraph();
  renderCalendar();
  renderFriends();
  arrange();
  updateGlass();

  // For checking states while the page is built, from the browser's console
  window.psfDemo = { state, toggleModule, requestArrives, floatOut, snap, updateGlass, renderCalendar, renderGraph, setPointer: (x, y) => { pointer = x == null ? null : { x, y }; updateGlass(); } };
})();
