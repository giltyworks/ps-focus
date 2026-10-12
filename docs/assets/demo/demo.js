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
  // As the app's stats and day tips: hours and minutes, or under an hour "37 min"
  const hmMin = (seconds) => (Math.round(seconds / 60) < 60 ? `${Math.round(Math.max(0, seconds) / 60)} min` : hm(seconds));
  const hm = (seconds) => { const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60); return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`; };
  const longDate = (date) => `${WEEKDAYS[(date.getDay() + 6) % 7]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;

  // ----- State -----

  const state = {
    todayProgram: "Photoshop",
    programSeconds: { "Krita": 0, "Clip Studio Paint": 0, "PhotoCraft": 0 },
    drawing: true,
    transparency: 50,
    period: "3 Months",
    calendarView: "Month",
    calendarMonth: new Date(today.getFullYear(), today.getMonth(), 1),
    shown: { graph: true, calendar: true, stats: false, friends: true },
    // A made-up Google account; in the app the real one is chosen on Google's own page in the browser
    account: { name: "gilty", email: "demo@example.com" },
    paused: false,
    settingsOpen: false,
    landscape: false,
    startWithWindows: true,
    startMinimized: true,
    fanfareOff: false,
    // Every block in the window's order, program panels and modules alike, as in the app
    order: ["today", "friends", "graph", "calendar", "stats"],
    floating: {},
    status: "online",
    favourites: new Set(),
    // Names the user gave friends, by code, shown in place of their own
    nicknames: new Map(),
    nicknaming: null,
    friends: [
      { code: "MIAA", name: "Mia", level: 19, presence: "drawing", program: "Krita", two: 16.4, total: 121.6, today: 1.4, since: new Date(2025, 2, 14) },
      { code: "LEOO", name: "inkbyleo", level: 14, presence: "online", two: 10.2, total: 71.3, today: 0.6, since: new Date(2025, 10, 2) },
      { code: "ISAB", name: "isabella.marsh21", level: 11, presence: "away", two: 6.8, total: 47.9, today: 0.0, since: new Date(2025, 7, 9) },
      { code: "JONA", name: "Jonathan", level: 8, presence: "offline", two: 3.1, total: 28.4, today: 0.0, lastOnline: 11, since: new Date(2026, 1, 15) },
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
    // A circle half filled, half see-through, as the app's transparency icon
    transparency: '<circle cx="7" cy="7" r="6.1"/><path d="M7 0.9A6.1 6.1 0 0 0 7 13.1Z" fill="currentColor" stroke="none"/>',
    friends: '<circle cx="9.5" cy="4" r="1.8"/><path d="M7.4 9.6C8 8 11.6 8 13.3 10.2"/><circle cx="5" cy="4.8" r="2.2"/><path d="M0.8 12.8C1.4 9.4 8.4 9.4 9.2 12.8"/>',
    stats: '<path d="M1.1 2.8H5.6M8.4 2.8H12.9M1.1 7H5.6M8.4 7H12.9M1.1 11.2H5.6M8.4 11.2H12.9"/>',
    chevron: '<path d="M4 5.5L7 8.5L10 5.5"/>',
    dock: '<path d="M6 4L3 7L6 10M10 4L7 7L10 10"/>',
  };
  // The calendar's small pictures, drawn as the app draws them rather than as emoji: the week streak's flame, the rest
  // days' moon, and a rating's star
  const FLAME_OUTLINE = [[0.58, 0.03], [0.70, 0.24], [0.84, 0.48], [0.85, 0.70], [0.72, 0.90], [0.50, 0.97], [0.28, 0.90],
    [0.15, 0.70], [0.18, 0.50], [0.29, 0.34], [0.37, 0.50], [0.45, 0.30], [0.50, 0.14]];
  const flamePoints = (() => {
    // A smooth closed curve through the outline points, as the app traces it
    const points = [], n = FLAME_OUTLINE.length;
    for (let i = 0; i < n; i++) {
      const [b, a, e, f] = [-1, 0, 1, 2].map((o) => FLAME_OUTLINE[(i + o + n) % n]);
      for (let k = 0; k < 12; k++) {
        const t = k / 12;
        points.push([0, 1].map((x) => (0.5 * (2 * a[x] + (e[x] - b[x]) * t + (2 * b[x] - 5 * a[x] + 4 * e[x] - f[x]) * t * t + (3 * a[x] - b[x] - 3 * e[x] + f[x]) * t ** 3) * 14).toFixed(2)).join(","));
      }
    }
    return points.join(" ");
  })();
  const picture = (markup, size, cls) => {
    const holder = document.createElement("span");
    holder.innerHTML = `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 14 14" aria-hidden="true">${markup}</svg>`;
    return holder.firstChild;
  };
  const flameIcon = () => picture(`<polygon points="${flamePoints}" fill="#f28c28"/>`, 14, "psf-streak-icon");
  let moonId = 0;
  const moonIcon = () => {
    const id = `psf-moon-${moonId++}`;
    return picture(`<mask id="${id}"><rect width="14" height="14" fill="#fff"/><circle cx="9.24" cy="5.6" r="5.04" fill="#000"/></mask><circle cx="7" cy="7" r="6.16" fill="#3d5ce6" mask="url(#${id})"/>`, 14, "psf-streak-icon");
  };
  // The rating star: the emoji's outline in one colour, as the app draws it
  const ratingStar = (size = 12) => picture('<path d="M7 1.3l1.62 3.5 3.83.42-2.86 2.6.8 3.77L7 9.66l-3.39 1.93.8-3.77-2.86-2.6 3.83-.42z" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>', size, "psf-star-icon");
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

  let menu = null, menuAnchor = null, closedFrom = null;
  const closeMenu = () => {
    menuAnchor?.classList.remove("psf-open"); menu?.remove(); menu = null; menuAnchor = null;
    if (transparencyOpen) { transparencyOpen = false; updateGlass(); }
  };
  // Clicking what opened a menu while it is open closes it, rather than closing and opening it again
  const openMenu = (anchor, items) => {
    const reopening = closedFrom === anchor;
    closedFrom = null;
    if (reopening) return;
    closeMenu();
    menuAnchor = anchor;
    anchor.classList.add("psf-open");
    menu = el("div", { class: "psf-menu", role: "menu" }, items);
    stage.append(menu);
    const a = anchor.getBoundingClientRect(), s = stage.getBoundingClientRect();
    const left = Math.min(a.left - s.left, stage.clientWidth - menu.offsetWidth - 4);
    menu.style.left = `${Math.max(4, left)}px`;
    menu.style.top = `${a.bottom - s.top + 2}px`;
  };
  document.addEventListener("pointerdown", (event) => {
    if (!menu || menu.contains(event.target)) return;
    if (menuAnchor?.contains(event.target)) { closedFrom = menuAnchor; setTimeout(() => (closedFrom = null), 400); }
    closeMenu();
  }, true);

  // ----- The page's controls and the scene -----

  // Pause tracking, as the checkbox in the app's Settings, which it stays in step with
  const pauseBox = el("button", { type: "button", class: "psf-check", role: "checkbox", "aria-checked": "false", "aria-label": "Pause tracking" });
  const pauseControl = el("label", { class: "psf-check-label psf-pause-control" }, "Pause tracking", pauseBox);
  // Fully right is fully solid, as the app's slider
  const slider = el("input", { type: "range", min: 0, max: 100, value: 100 - state.transparency, "aria-label": "Transparency, solid at the right" });
  const controls = el("div", { class: "psf-controls" },
    pauseControl,
    el("label", { class: "psf-slider" }, "Transparency", slider),
    // On a phone, where there is no pointer to hover the tips with, a line says how the fading works
    touch.matches ? el("span", { class: "psf-hint" }, "Tap the painting to let PS Focus fade") : null);
  const stage = el("div", { class: "psf-stage" });
  const canvas = el("div", { class: "psf-canvas", role: "img", "aria-label": "Painting representing Photoshop in the PS Focus demo." });
  canvas.style.backgroundImage = `url("${PAINTING}")`;
  canvas.append(el("div", { class: "psf-canvas-label", "aria-hidden": "true" }, "Demo canvas"));

  // Capture focus before panel drag handlers can stop propagation. Detached panels and
  // popup dialogs belong to PS Focus too; hovering alone does not change activity.
  root.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const painting = canvas.contains(event.target);
    const app = event.target.closest(".psf-window, .psf-floating, .psf-menu, .psf-sheet, .psf-app-window, .psf-controls");
    if (!painting && !app) return;
    if (state.drawing === painting) return;
    state.drawing = painting;
    renderToday();
  }, true);
  stage.append(canvas);
  root.append(controls, stage);

  function setPaused(paused) {
    state.paused = paused;
    pauseBox.classList.toggle("psf-checked", paused);
    pauseBox.setAttribute("aria-checked", String(paused));
    renderToday();
    if (state.settingsOpen) renderSettings();
  }
  pauseBox.addEventListener("click", () => { markUsed("timer"); setPaused(!state.paused); });
  const setTransparency = (amount) => {
    state.transparency = amount;
    slider.value = 100 - amount;
    popupSlider.value = 100 - amount;
    // The track is blue up to the knob's middle, which travels the track less the knob's width
    popupSlider.style.setProperty("--fill", `${6 + (80 - 12) * (100 - amount) / 100}px`);
    // The icon dims as the setting rises, as the app's: as bright as a shown module's when solid, about as dim as a
    // hidden one's fully see-through
    transparencyButton.style.opacity = String(1 - 0.75 * amount / 100);
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
  const accountName = el("span", { class: "psf-account-name" }, "gilty");
  // A double click on the name edits it, as in the app: Enter or clicking away keeps it, Escape leaves it as it was,
  // and an empty name goes back to the first one
  accountName.addEventListener("click", () => { if (!state.account) signIn(); });
  accountName.addEventListener("dblclick", () => {
    if (!state.account) return;
    const field = el("input", { class: "psf-name-field", type: "text", maxlength: 32, value: accountName.textContent, "aria-label": "Your name" });
    let done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      if (keep) state.account.name = field.value.trim() || state.account.email.split("@")[0];
      renderAccount();
      field.replaceWith(accountName);
    };
    field.addEventListener("keydown", (event) => { if (event.key === "Enter") finish(true); if (event.key === "Escape") finish(false); });
    field.addEventListener("blur", () => finish(true));
    accountName.replaceWith(field);
    field.focus();
    field.select();
  });
  const statusButton = el("button", { type: "button", class: "psf-icon-button psf-chevron", title: "Status", onclick: (event) => statusMenu(event.currentTarget) }, svg(ICONS.chevron));
  // The name, bold, with the arrow to the status menu beside it and the status under it, as the app
  const accountStatus = el("span", { class: "psf-account-status" });
  const account = el("div", { class: "psf-account" }, progressDot,
    el("span", { class: "psf-account-text" }, el("span", { class: "psf-account-line" }, accountName, statusButton), accountStatus));
  const settingsButton = el("button", { type: "button", class: "psf-icon-button psf-settings", title: "Settings", onclick: () => toggleSettings() }, "···");
  const level = el("div", { class: "psf-level" }, "Level", levelBadge);
  // In Settings the header shows the version and the credit in place of the level and account
  const credit = el("div", { class: "psf-credit", hidden: true }, el("span", { class: "psf-version" }, "Version 1.1.25"), el("span", { class: "psf-by" }, "by giltyworks"));
  const header = el("div", { class: "psf-header" }, level, account, credit, settingsButton);
  const iconButtons = {};
  // At the left end of the row, as the app: the transparency icon, opening a small slider under it. While it is open
  // PS Focus shows the transparency being chosen, the pointer over it or not
  const popupSlider = el("input", { type: "range", min: 0, max: 100, value: 100 - state.transparency, "aria-label": "Transparency, solid at the right" });
  popupSlider.addEventListener("input", () => setTransparency(100 - Number(popupSlider.value)));
  let transparencyOpen = false;
  const transparencyButton = el("button", { type: "button", class: "psf-icon-button psf-transparency", title: "Transparency",
    onclick: () => {
      openMenu(transparencyButton, [el("div", { class: "psf-transparency-popup" }, popupSlider)]);
      transparencyOpen = !!menu && menuAnchor === transparencyButton;
      if (menu && transparencyOpen) {
        // Beside the icon, to its right, over the empty end of the row rather than the panel under it
        menu.classList.add("psf-compact");
        const a = transparencyButton.getBoundingClientRect(), st = stage.getBoundingClientRect();
        menu.style.left = `${a.right - st.left + 3}px`;
        menu.style.top = `${a.top - st.top + (a.height - menu.offsetHeight) / 2}px`;
      }
      updateGlass();
    } }, svg(ICONS.transparency));
  transparencyButton.style.opacity = String(1 - 0.75 * state.transparency / 100);
  popupSlider.style.setProperty("--fill", `${6 + (80 - 12) * (100 - state.transparency) / 100}px`);
  const icons = el("div", { class: "psf-icons" }, transparencyButton, ["graph", "calendar", "stats", "friends"].map((name) => {
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
    name: el("span", {}, "Photoshop"),
    program: el("button", { type: "button", class: "psf-icon-button psf-chevron", "aria-label": "Choose program history", onclick: () => {
      state.drawing = false;
      renderToday();
      openMenu(today_.program, ["Photoshop", "Krita", "Clip Studio Paint", "PhotoCraft"].map((program) => el("button", { type: "button", onclick: () => {
        state.todayProgram = program; closeMenu(); renderToday();
      } }, program)));
    } }, svg(ICONS.chevron)),
    two: el("span", { class: "psf-two-week" }),
    metric: el("div", { class: "psf-metric" }),
    sessions: el("span", { class: "psf-small" }),
    record: el("span", {}),
    status: el("span", { class: "psf-status" }),
    last: el("span", {}),
  };
  const todayBlock = el("div", { class: "psf-block psf-today", "data-name": "today" },
    el("div", { class: "psf-strip" }, today_.name, today_.program, today_.two, dockIcon()),
    el("div", { class: "psf-today-body" }, today_.metric,
      el("div", { class: "psf-row" }, today_.status, today_.record),
      el("div", { class: "psf-row" }, today_.sessions, today_.last)));
  const sessionsCount = [...history.values()].filter((hours) => hours.reduce((a, b) => a + b, 0) >= SESSION_MINIMUM).length;
  const lastSession = (() => { for (let ago = 1; ago <= STARTED_DAYS_AGO; ago++) if (dayTotal(daysAgo(ago)) > 0) return daysAgo(ago); return today; })();

  function renderToday() {
    const otherSeconds = Object.values(state.programSeconds).reduce((sum, seconds) => sum + seconds, 0);
    const todaySeconds = dayTotal(today) - otherSeconds;
    today_.two.textContent = `${((rangeTotal(daysAgo(13), today) - otherSeconds) / 3600).toFixed(1)} hrs past 2 weeks`;
    today_.metric.textContent = clock(todaySeconds);
    today_.sessions.textContent = `${sessionsCount} SESSIONS`;
    today_.record.textContent = `${((lifetime - otherSeconds) / 3600).toFixed(1)} hrs on record`;
    const active = state.drawing && !state.paused;
    today_.name.textContent = state.todayProgram;
    today_.program.disabled = false;
    if (state.todayProgram !== "Photoshop") {
      const values = { "Krita": ["0.0", "2.5", 2], "Clip Studio Paint": ["1.8", "6.2", 4], "PhotoCraft": ["0.6", "3.1", 3] }[state.todayProgram];
      const seconds = state.programSeconds[state.todayProgram];
      today_.two.textContent = `${(Number(values[0]) + seconds / 3600).toFixed(1)} hrs past 2 weeks`;
      today_.metric.textContent = clock(seconds);
      today_.sessions.textContent = `${values[2]} SESSIONS`;
      today_.record.textContent = `${(Number(values[1]) + seconds / 3600).toFixed(1)} hrs on record`;
    }
    today_.name.style.color = active ? "var(--psf-green)" : "var(--psf-name-online)";
    today_.status.textContent = state.paused ? "PAUSED" : "";
    renderAccount();
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
  chart.setAttribute("viewBox", "0 0 298 210");
  const graphBlock = el("div", { class: "psf-block psf-graph", "data-name": "graph" },
    strip("Usage over time"),
    el("div", { class: "psf-graph-head" }, `${MONTHS[today.getMonth()]} ${today.getFullYear()}`, el("span", { class: "psf-spacer" }),
      PERIODS.map(([period, label]) => (periodButtons[period] = el("button", { type: "button", class: "psf-period", onclick: () => { state.period = period; renderGraph(); } }, label)))),
    // As the app: the total and its caption drawn over the top of the chart's 210-pixel picture
    el("div", { class: "psf-chart-box" }, el("div", { class: "psf-readout" }, readoutValue, readoutCaption), chart));

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
    // The plot's edges and hour lines, as the app's: 34 in from the left, 18 short of the right, 64 down under the
    // total, 26 up from the bottom for the labels; whole hours, at most about four steps
    const left = 34, right = 280, top = 64, bottom = 184;
    let ceiling = Math.max(1, Math.ceil(Math.max(Math.max(0, ...data.values) * 60, 60) / 60));
    const step = Math.max(1, Math.ceil(ceiling / 4));
    ceiling = Math.ceil(ceiling / step) * step;
    const x = (i) => left + (data.values.length === 1 ? 0 : i * (right - left) / (data.values.length - 1));
    const y = (v) => bottom - v / ceiling * (bottom - top);
    const shown = data.values.map((v, i) => (data.upTo != null && i > data.upTo ? null : v));
    const points = shown.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
    let markup = "";
    for (let v = 0; v <= ceiling; v += step) {
      markup += `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(34,34,34,1)"/><text x="${left - 8}" y="${y(v)}" text-anchor="end" dominant-baseline="central">${v}h</text>`;
    }
    data.ticks.forEach(([i, label]) => { markup += `<text x="${x(i)}" y="${bottom + 15}" text-anchor="middle" dominant-baseline="central">${label}</text>`; });
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
  const calToggle = el("button", { type: "button", class: "psf-cal-button psf-cal-toggle", onclick: () => { state.calendarView = state.calendarView === "Month" ? "Year" : "Month"; renderCalendar(); } }, "month");
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
  const overlaps = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const showTip = (target, text, wrap = false) => {
    hideTip();
    tip = el("div", { class: `psf-tip${wrap ? " psf-tip-wrap" : ""}` }, text);
    stage.append(tip);
    const t = rect(target), w = tip.offsetWidth, h = tip.offsetHeight, gap = 6;
    const inside = (x, y) => ({ left: Math.max(4, Math.min(x, stage.clientWidth - w - 4)), top: Math.max(4, Math.min(y, stage.clientHeight - h - 4)) });
    // Above what it explains, below, to its right or to its left: the first place inside the scene clear of the arrows
    const places = [
      inside(t.left + t.width / 2 - w / 2, t.top - h - gap), inside(t.left + t.width / 2 - w / 2, t.bottom + gap),
      inside(t.right + gap, t.top + t.height / 2 - h / 2), inside(t.left - w - gap, t.top + t.height / 2 - h / 2),
    ].map((place) => ({ ...place, right: place.left + w, bottom: place.top + h }));
    const arrows = [...hotspots.children].filter((arrow) => arrow !== target);
    const clear = (place) => !overlaps(place, t) && !arrows.some((arrow) => overlaps(place, rect(arrow)));
    const place = places.find(clear) || places.find((candidate) => !overlaps(candidate, t)) || places[0];
    tip.style.left = `${place.left}px`;
    tip.style.top = `${place.top}px`;
    // With nowhere clear, the arrows under it step aside while it shows
    arrows.forEach((arrow) => arrow.classList.toggle("psf-aside", overlaps(place, rect(arrow))));
  };
  const hideTip = () => {
    tip?.remove();
    tip = null;
    document.querySelectorAll(".psf-aside").forEach((arrow) => arrow.classList.remove("psf-aside"));
  };

  // A day's overview: its time in each program, when it started, and the day's rating from 1 to 10, which a click on
  // the same star clears, as in the app
  const clockTime = (hour, minute) => `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
  // The app's small windows, the day's rating and a friend's details: a title bar with the logo, the title and a close
  // button over the body, centred on PS Focus's window as the app opens them; one at a time
  function appWindow(title, label, cls, ...body) {
    document.querySelector(".psf-app-window")?.remove();
    const box = el("div", { class: `psf-app-window ${cls}`, role: "dialog", "aria-label": label });
    box.append(el("div", { class: "psf-titlebar" }, el("img", { src: LOGO, alt: "" }), title, el("span", { class: "psf-spacer" }),
      el("button", { type: "button", class: "psf-close", title: "Close", onclick: () => box.remove() }, "\u2715")), ...body);
    stage.append(box);
    const w = rect(win);
    box.style.left = `${Math.max(8, Math.min(w.left + (w.width - box.offsetWidth) / 2, stage.clientWidth - box.offsetWidth - 8))}px`;
    box.style.top = `${Math.max(8, Math.min(w.top + (w.height - box.offsetHeight) / 2, stage.clientHeight - box.offsetHeight - 8))}px`;
    return box;
  }

  function dayOverview(date) {
    const hours = history.get(key(date)) || [];
    const seconds = hours.reduce((a, b) => a + b, 0);
    const first = hours.findIndex((value) => value > 0);
    const stars = el("div", { class: "psf-stars" });
    const paintStars = (shown) => [...stars.children].forEach((star, index) => {
      star.classList.toggle("psf-lit", index < shown);
    });
    for (let value = 1; value <= 10; value++) {
      const star = el("button", { type: "button", class: "psf-star", "aria-label": `Rate ${value} out of 10` }, ratingStar(16));
      star.addEventListener("pointerenter", () => paintStars(value));
      star.addEventListener("click", () => {
        if (ratings.get(key(date)) === value) ratings.delete(key(date));
        else ratings.set(key(date), value);
        paintStars(ratings.get(key(date)) || 0);
        renderCalendar();
      });
      stars.append(star);
    }
    stars.addEventListener("pointerleave", () => paintStars(ratings.get(key(date)) || 0));
    paintStars(ratings.get(key(date)) || 0);
    appWindow(`${WEEKDAYS[(date.getDay() + 6) % 7]}, ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`,
      `${longDate(date)} overview`, "psf-day-overview",
      seconds
        ? el("div", { class: "psf-overview-rows" }, el("span", {}, "Photoshop"), el("span", { class: "psf-muted" }, `${clock(seconds)} · started ${clockTime(first, 10 + (date.getDate() * 7) % 40)}`))
        : el("div", { class: "psf-overview-empty" }, "No activity recorded"),
      el("b", { class: "psf-overview-ask" }, "How productive was this session?"), stars);
  }

  function renderCalendar() {
    renderStats();
    const [weeks, rest] = streaks();
    calLegend.replaceChildren(el("span", { class: "psf-square" }), "15 min+", el("span", { class: "psf-spacer" }),
      flameIcon(), `${weeks} week streak`, el("span", { style: "width:6px" }), moonIcon(), `${rest} rest days`);
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
        String(d), rating ? el("span", { class: "psf-rating" }, ratingStar(), ` ${rating}`) : null);
      if (!future) {
        // Under the mouse, the day's date and time tracked; a click opens the day
        cell.addEventListener("pointerenter", () => showTip(cell, `${longDate(date)}${seconds ? ` · ${hmMin(seconds)}` : ""}`));
        cell.addEventListener("pointerleave", hideTip);
        cell.addEventListener("click", () => { hideTip(); dayOverview(date); });
      }
      cells.push(cell);
    }
    const days = el("div", { class: "psf-days" }, cells);
    // The panel's colour between the days, cut around each day's rounded square, so a see-through calendar shows every
    // spot once, as the app draws it, rather than a day on top of the panel
    const rows = Math.ceil(cells.length / 7);
    const holes = cells.map((_, i) => `<rect x="${(i % 7) * 43}" y="${Math.floor(i / 7) * 41}" width="40" height="38" rx="6"/>`).join("");
    const mask = `<svg xmlns="http://www.w3.org/2000/svg" width="298" height="${rows * 41}"><rect width="298" height="${rows * 41}" fill="#fff"/><g fill="#000">${holes}</g></svg>`;
    days.style.setProperty("--days-mask", `url("data:image/svg+xml,${encodeURIComponent(mask)}")`);
    calBody.replaceChildren(el("div", { class: "psf-weekdays" }, WEEKDAYS.map((w) => el("span", {}, w))), days);
  }

  // ----- Stats: label and value rows, as the app's -----

  const statsBody = el("div", { class: "psf-stats" });
  const statsBlock = el("div", { class: "psf-block psf-stats-block", "data-name": "stats" }, strip("Stats"), statsBody);
  const MEDALS = [[10, "gold"], [25, "silver"], [50, "bronze"]];
  const MEDAL_COLORS = { gold: "#f0c33c", silver: "#c3cbd1", bronze: "#d0874a" };
  // The app's award: a disc over two swallowtailed ribbons, a thin gap between them
  const AWARD_TAIL = [[0.03, 0.50], [0.25, 0.50], [0.37, 0.96], [0.26, 0.89], [0.15, 1.0]];
  let awardId = 0;
  const awardIcon = (medal) => {
    const id = `psf-award-${awardId++}`, fill = MEDAL_COLORS[medal];
    const tails = [1, -1].map((m) => `<polygon points="${AWARD_TAIL.map(([x, y]) => `${((0.5 - m * x) * 14).toFixed(2)},${(y * 14).toFixed(2)}`).join(" ")}"/>`).join("");
    return picture(`<mask id="${id}"><rect width="14" height="14" fill="#fff"/><circle cx="7" cy="4.76" r="5.53" fill="#000"/></mask><g fill="${fill}" mask="url(#${id})">${tails}</g><circle cx="7" cy="4.76" r="4.48" fill="${fill}"/>`, 14, "psf-award");
  };
  const firstDay = daysAgo(STARTED_DAYS_AGO);
  const average = (days, end) => rangeTotal(new Date(end.getTime() - (days - 1) * DAY), end) / days;
  // How a daily average moved, in minutes, such as "+10", as the app
  const change = (seconds) => { const m = Math.round(seconds / 60); return m === 0 ? "same" : `${m > 0 ? "+" : "-"}${Math.abs(m)}`; };
  const startOf = (date) => { const hour = (history.get(key(date)) || []).findIndex((v) => v > 0); return hour < 0 ? null : hour * 60; };
  const clockOf = (minutes) => clockTime(Math.floor(minutes / 60), minutes % 60);

  function renderStats() {
    const monday = daysAgo((today.getDay() + 6) % 7);
    const week = rangeTotal(monday, today);
    // This week so far against the same days of each past week
    const past = [];
    for (let w = 1; w < 52; w++) {
      const start = new Date(monday.getTime() - w * 7 * DAY);
      if (start.getTime() + 6 * DAY < firstDay.getTime()) break;
      past.push(rangeTotal(start, new Date(start.getTime() + (today.getTime() - monday.getTime()))));
    }
    const rank = past.length >= 4 ? Math.max(1, Math.round((past.filter((v) => v > week).length + 1) / (past.length + 1) * 100)) : null;
    const medal = rank != null ? (MEDALS.find(([limit]) => rank <= limit) || [])[1] : null;
    const row = (label, value, { note = "", noteClass = "", valueClass = "", medalName = null, gap = false } = {}) =>
      el("div", { class: `psf-stat${gap ? " psf-stat-gap" : ""}` }, el("span", { class: "psf-stat-label" }, label),
        el("span", { class: `psf-stat-value ${valueClass}` }, medalName ? awardIcon(medalName) : null, value),
        el("span", { class: `psf-stat-note ${noteClass}` }, note));
    const rows = [row("This week", hmMin(week), { valueClass: "psf-bold", medalName: medal })];
    rows[0].classList.add("psf-stat-big");
    if (medal) rows.push(row("", `top ${rank}% of your weeks`, { valueClass: "psf-muted" }));
    rows[rows.length - 1].classList.add("psf-stat-gap");
    for (const days of [7, 30]) {
      const now = average(days, today), before = average(days, new Date(today.getTime() - days * DAY));
      rows.push(row(`${days}-day average`, `${hmMin(now)}/day`, { note: change(now - before), noteClass: Math.round((now - before) / 60) > 0 ? "psf-up" : "" }));
    }
    // Each weekday averaged over every time it has come round since the first day
    const totals = new Array(7).fill(0), counts = new Array(7).fill(0);
    for (let t = firstDay.getTime(); t <= today.getTime(); t += DAY) { const d = new Date(t), i = (d.getDay() + 6) % 7; totals[i] += dayTotal(d); counts[i]++; }
    const best = totals.map((v, i) => v / counts[i]).reduce((b, v, i, all) => (v > all[b] ? i : b), 0);
    rows.push(row("Best day", `${WEEKDAYS[best]} · ${hmMin(totals[best] / counts[best])}/day`));
    let longest = null;
    history.forEach((_, k) => { const [y, m, d] = k.split("-").map(Number), date = new Date(y, m, d), total = dayTotal(date); if (total >= SESSION_MINIMUM && (!longest || total > longest[1] || (total === longest[1] && date < longest[0]))) longest = [date, total]; });
    rows.push(row("Longest session", longest ? `${longest[0].getDate()} ${MONTHS[longest[0].getMonth()]} ${longest[0].getFullYear()} · ${hmMin(longest[1])}` : "--"));
    // The start of the highest-rated days, averaged
    const top = Math.max(0, ...ratings.values());
    const starts = [...ratings].filter(([, r]) => r === top).map(([k]) => { const [y, m, d] = k.split("-").map(Number); return startOf(new Date(y, m, d)); }).filter((v) => v != null);
    if (top && starts.length) rows.push(row("Best start time", clockOf(Math.round(starts.reduce((a, b) => a + b, 0) / starts.length)), { note: [ratingStar(), ` ${top}`], noteClass: "psf-gold" }));
    // The sessions in the period the calendar shows
    const m = state.calendarMonth, year = state.calendarView === "Year";
    const from = year ? new Date(m.getFullYear(), 0, 1) : m, to = year ? new Date(m.getFullYear(), 11, 31) : new Date(m.getFullYear(), m.getMonth() + 1, 0);
    const sessions = [];
    for (let t = from.getTime(); t <= Math.min(to.getTime(), today.getTime()); t += DAY) { const d = new Date(t); if (dayTotal(d) >= SESSION_MINIMUM) sessions.push(startOf(d)); }
    const period = year ? String(m.getFullYear()) : MONTH_NAMES[m.getMonth()];
    const summary = sessions.length
      ? row(`${sessions.length} session${sessions.length === 1 ? "" : "s"} in ${period}`, `avg start ${clockOf(Math.round(sessions.reduce((a, b) => a + b, 0) / sessions.length))}`, { valueClass: "psf-muted" })
      : row("No sessions for this period", "");
    summary.classList.add("psf-stat-summary");
    statsBody.replaceChildren(...rows, summary);
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

  const PROGRAM_SHORT = { "Clip Studio Paint": "Clip Studio" };
  // Today's time on a friend's row: hours to a decimal, or under an hour in minutes, as the app
  const todayAmount = (hours) => (hours >= 1 ? `${hours.toFixed(1)} hrs` : `${Math.round(hours * 60)} min`);
  function friendRow(friend) {
    const nameClass = { drawing: "psf-drawing", online: "psf-online", away: "psf-away", offline: "psf-offline" }[friend.presence];
    const shown = state.nicknames.get(friend.code) || friend.name;
    const name = el("span", { class: `psf-name ${nameClass}` }, shown);
    if (state.nicknaming === friend.code) {
      // The nickname is typed over the name: Enter keeps it, Escape or clicking elsewhere leaves it as it was
      const field = el("input", { type: "text", class: "psf-nick-input", maxlength: 32, value: shown, placeholder: "Nickname", "aria-label": "Nickname" });
      const finish = (keep) => {
        if (state.nicknaming !== friend.code) return;
        state.nicknaming = null;
        if (keep) { const typed = field.value.trim(); typed && typed !== friend.name ? state.nicknames.set(friend.code, typed) : state.nicknames.delete(friend.code); }
        renderFriends();
      };
      field.addEventListener("keydown", (event) => { if (event.key === "Enter") finish(true); if (event.key === "Escape") finish(false); });
      field.addEventListener("blur", () => finish(false));
      name.replaceChildren(field);
      setTimeout(() => { field.focus(); field.select(); });
    }
    if (friend.presence === "away") name.append(el("span", { class: "psf-zzz", title: "Away" }, el("span", {}, "z"), el("span", {}, "z"), el("span", {}, "z")));
    name.append(el("button", { type: "button", class: "psf-icon-button psf-chevron", title: `${friend.name}'s menu`, onclick: (event) => friendMenu(event.currentTarget, friend) }, svg(ICONS.chevron)));
    const row = el("div", { class: `psf-friend${friend.fresh ? " psf-new" : ""}`, oncontextmenu: (event) => { event.preventDefault(); friendMenu(name, friend); } },
      el("span", { class: "psf-lv" }, String(friend.level)), name,
      el("span", {}), friend.presence === "drawing"
        // Today's time with the program they are drawing in, as the app shows it
        ? el("span", { class: "psf-sub psf-program" }, `${PROGRAM_SHORT[friend.program] || friend.program} (${todayAmount(friend.today)})`)
        // Online: today's time in blue, or just Online with none yet, as the app
        : friend.presence === "online"
          ? el("span", { class: "psf-sub psf-online-today" }, friend.today > 0 ? `${todayAmount(friend.today)} today` : "Online")
          : friend.presence === "away"
            ? el("span", { class: "psf-sub psf-away" }, "Away")
            : friend.presence === "offline" && friend.today <= 0
              // Nothing today: when they were last online, as the app
              ? el("span", { class: "psf-sub" }, friend.lastOnline ? `Last online ${friend.lastOnline} hours ago` : "Offline")
              : el("span", { class: "psf-sub" }, `${todayAmount(friend.today)} today`));
    // Detailed figures open on a double-click of the name, as in the app.
    const figures = `${friend.two.toFixed(1)} hrs past 2 weeks
${friend.total.toFixed(1)} hrs total`
      + (friend.since ? `
Member since ${friend.since.getDate()} ${MONTHS[friend.since.getMonth()]} ${friend.since.getFullYear()}` : "");
    // Anywhere on the friend's rows, as the app, but their menu arrow
    row.addEventListener("dblclick", (event) => {
      if (event.target.closest("button, input")) return;
      event.stopPropagation(); hideTip();
      // A small window titled with their name, as the app's: the figures, and when they joined in grey
      appWindow(shown, `${shown} details`, "psf-friend-details",
        el("div", { class: "psf-details-body" },
          figures.split("\n").map((line) => el("span", line.startsWith("Member since") ? { class: "psf-muted" } : {}, line))));
    });
    friend.fresh = false;
    return row;
  }

  function renderFriends() {
    requestsIcon.hidden = !state.request;
    requestsIcon.querySelector(".psf-count")?.remove();
    if (state.request) requestsIcon.append(el("span", { class: "psf-count" }, "1"));
    requestsIcon.classList.toggle("psf-open", state.requestsOpen && !!state.request);
    [copyButton, addIcon].forEach((control) => (control.hidden = !state.account));
    if (!state.account) {
      requestsIcon.hidden = true;
      friendList.replaceChildren(el("div", { class: "psf-offline-note" }, "Sign in with Google to add friends and see each other's hours.",
        el("div", { class: "psf-center" }, el("button", { type: "button", class: "psf-accept", onclick: () => signIn() }, "Sign in with Google"))));
      return;
    }
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
    // Favourites, then those drawing, the others online, and those offline, as the app
    const section = (friend) => (state.favourites.has(friend.code) ? "Favourites" : friend.presence === "drawing" ? "In App" : friend.presence === "offline" ? "Offline" : "Online");
    const order = { Favourites: 0, "In App": 1, Online: 2, Offline: 3 };
    const sorted = [...state.friends].sort((a, b) => order[section(a)] - order[section(b)] || b.two - a.two);
    const onlyOnline = sorted.every((f) => section(f) === "Online");
    let current = null;
    for (const friend of sorted) {
      const name = section(friend);
      if (name !== current) {
        current = name;
        if (!onlyOnline) {
          // A count only from four up, such as "Online (4)", as the app
          const count = sorted.filter((f) => section(f) === name).length;
          parts.push(el("div", { class: "psf-section" }, count > 3 ? `${name} (${count})` : name));
        }
      }
      parts.push(friendRow(friend));
    }
    friendList.replaceChildren(...parts);
  }

  function requestArrives() {
    // A request shows on the requests icon in the friends strip, with its count, as in the app; its list holds it
    if (state.requestShown) return;
    state.requestShown = true;
    state.request = { code: "SAMI", name: "Samira", level: 16, presence: "drawing", program: "Photoshop", two: 12.7, total: 92.4, today: 1.1, since: new Date(2025, 5, 2) };
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
    const nickname = state.nicknames.get(friend.code);
    openMenu(anchor, [
      el("button", { type: "button", onclick: () => { favourite ? state.favourites.delete(friend.code) : state.favourites.add(friend.code); closeMenu(); renderFriends(); } }, favourite ? "Remove from favourites" : "Add to favourites"),
      el("button", { type: "button", onclick: () => { closeMenu(); state.nicknaming = friend.code; renderFriends(); } }, nickname ? "Change nickname" : "Set nickname"),
      nickname ? el("button", { type: "button", onclick: () => { state.nicknames.delete(friend.code); closeMenu(); renderFriends(); } }, "Clear nickname") : null,
      el("button", { type: "button", class: "psf-danger", onclick: () => { state.friends = state.friends.filter((f) => f !== friend); closeMenu(); renderFriends(); toast(`${nickname || friend.name} removed`); } }, "Remove friend"),
    ]);
  }

  function statusMenu(anchor) {
    markUsed("status");
    const choices = [["online", "Online", ""], ["away", "Away", "Friends see you're away"], ["invisible", "Invisible", "Appear offline, but still see your friends"], ["offline", "Offline", "Stop sharing with friends"]];
    openMenu(anchor, choices.map(([status, name, note]) => el("button", { type: "button", class: status === state.status ? "psf-current" : "",
      onclick: () => { state.status = status; account.classList.toggle("psf-hidden-name", status === "invisible" || status === "offline"); closeMenu(); renderAccount(); renderFriends(); } }, name, note ? el("small", {}, note) : null)));
  }

  // ----- Settings -----

  const checkbox = (checked, label, onToggle) => {
    const box = el("button", { type: "button", class: `psf-check${checked ? " psf-checked" : ""}`, role: "checkbox", "aria-checked": String(checked), "aria-label": label });
    box.addEventListener("click", () => { onToggle(); });
    return box;
  };
  const backupStatus = el("div", { class: "psf-backup-line psf-green" }, "Activity backup saved to Google Drive");

  // ----- Google sign-in, simulated: in the app Google's own page opens in the browser, which the demo says rather
  // than imitates; two made-up accounts to choose from -----

  const ACCOUNTS = [{ name: "gilty", email: "demo@example.com" }, { name: "Lena", email: "lena@example.com" }];

  function renderAccount() {
    const signedIn = !!state.account;
    accountName.textContent = signedIn ? state.account.name : "Local only";
    accountName.title = signedIn ? "" : "Sign in with Google";
    account.classList.toggle("psf-local", !signedIn);
    account.classList.toggle("psf-hidden-name", state.status === "invisible" || state.status === "offline");
    statusButton.hidden = !signedIn;
    accountStatus.hidden = !signedIn;
    const drawing = state.status === "online" && state.drawing && !state.paused;
    account.classList.toggle("psf-in-app", signedIn && drawing);
    accountStatus.textContent = drawing ? state.todayProgram : { online: "Online", away: "Away", invisible: "Invisible", offline: "Offline" }[state.status];
    accountStatus.dataset.status = drawing ? "drawing" : state.status;
  }

  function signIn(switching = false) {
    closeMenu();
    const sheet = el("div", { class: "psf-sheet", role: "dialog", "aria-label": "Sign in, simulated" });
    const card = el("div", { class: "psf-sheet-card" },
      el("b", {}, switching ? "Switch Google account" : "Sign in with Google"),
      el("span", { class: "psf-sheet-note" }, "Simulated. In the app, Google's own sign-in page opens in your browser."),
      ACCOUNTS.filter((choice) => !switching || choice.email !== state.account?.email).map((choice) =>
        el("button", { type: "button", class: "psf-sheet-account", onclick: () => connect(choice) },
          el("span", { class: "psf-avatar" }, choice.name[0].toUpperCase()), el("span", {}, choice.name, el("small", {}, choice.email)))),
      el("button", { type: "button", class: "psf-sheet-cancel", onclick: () => sheet.remove() }, "Cancel"));
    sheet.append(card);
    stage.append(sheet);
    function connect(choice) {
      card.replaceChildren(el("b", {}, "Connecting…"), el("span", { class: "psf-sheet-note" }, "PS Focus is connected, you can close this browser tab"));
      setTimeout(() => {
        sheet.remove();
        state.account = { ...choice };
        backupStatus.textContent = "Activity backup saved to Google Drive";
        backupStatus.className = "psf-backup-line psf-green";
        renderAccount();
        renderFriends();
        if (state.settingsOpen) renderSettings();
        toast(`Connected as ${choice.email}`);
      }, 900);
    }
  }

  function logOut() {
    state.account = null;
    state.request = null;
    state.requestsOpen = false;
    backupStatus.textContent = "Local activity backups saved";
    backupStatus.className = "psf-backup-line psf-muted";
    renderAccount();
    renderFriends();
    if (state.settingsOpen) renderSettings();
    toast("Logged out of Google; your history stays on this PC");
  }

  function boxedRow(title, text, control) {
    return el("div", { class: "psf-boxed" }, el("div", { class: "psf-boxed-text" }, el("b", {}, title), el("span", {}, text)), control);
  }

  function renderSettings() {
    const orientation = el("div", { class: "psf-orientation" },
      el("button", { type: "button", class: `psf-shape psf-tall${state.landscape ? "" : " psf-chosen"}`, "aria-label": "Portrait", onclick: () => chooseOrientation(false) }),
      el("button", { type: "button", class: "psf-shape psf-wide psf-disabled", "aria-label": "Landscape, disabled in the demo", title: "Disabled in the demo",
        onclick: () => toast("Landscape is disabled in the demo. In the app it lays PS Focus out as one wide strip") }));
    const toggle = (key) => checkbox(state[key], key, () => { state[key] = !state[key]; renderSettings(); });
    settingsPage.replaceChildren(
      el("h3", {}, "Settings"),
      el("p", { class: "psf-settings-text" }, "PS Focus counts time in Photoshop, Krita, CSP and PhotoCraft while they are in front and pauses when you're inactive"),
      boxedRow("Orientation", "Modules below or beside the program panel", orientation),
      boxedRow("Start with Windows", "Launch PS Focus when you sign in to Windows", toggle("startWithWindows")),
      boxedRow("Start minimized", "Open PS Focus minimized when launched at sign-in", toggle("startMinimized")),
      el("div", { class: "psf-check-row" },
        el("label", { class: "psf-check-label" }, "Pause tracking", checkbox(state.paused, "Pause tracking", () => setPaused(!state.paused))),
        el("label", { class: "psf-check-label" }, "Disable fanfare sound", toggle("fanfareOff"))),
      el("div", { class: "psf-backups" },
        el("b", {}, "Settings and activity backups"),
        el("span", {}, "Activity is saved locally on this PC and backed up to Google Drive when connected"),
        state.account ? el("div", { class: "psf-backup-line psf-green" }, state.account.email) : el("div", { class: "psf-backup-line psf-muted" }, "Not connected"),
        backupStatus,
        el("div", { class: "psf-backup-buttons" },
          el("button", { type: "button", onclick: () => {
            backupStatus.textContent = "Local activity backups saved";
            if (state.account) setTimeout(() => (backupStatus.textContent = "Activity backup saved to Google Drive"), 1200);
          } }, "Back up now"),
          ...(state.account ? [
            el("button", { type: "button", onclick: () => signIn(true) }, "Switch account"),
            el("button", { type: "button", onclick: logOut }, "Log out"),
          ] : [el("button", { type: "button", class: "psf-connect", onclick: () => signIn() }, "Connect Google")]))),
      el("button", { type: "button", class: "psf-exit", onclick: () => toast("Exit closes PS Focus; it counts nothing until you open it again") }, "Exit"),
      // Since when the user has been a member, from the first day tracked, as the app
      el("p", { class: "psf-member-since" }, `Member since ${firstDay.getDate()} ${MONTH_NAMES[firstDay.getMonth()]} ${firstDay.getFullYear()}`));
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

  const blockOf = { today: todayBlock, graph: graphBlock, calendar: calendarBlock, stats: statsBlock, friends: friendsBlock };
  // The automatic Today panel is always wanted; the other modules follow their toggles.
  const wanted = (name) => name === "today" || state.shown[name];

  function toggleModule(name) {
    state.shown[name] = !state.shown[name];
    if (state.floating[name]) state.floating[name].panel.hidden = !wanted(name);
    arrange();
    if (name === "friends" && state.shown.friends && !state.requestShown) setTimeout(requestArrives, 1600);
  }

  // Friends shows from the start, so a few seconds after the demo comes into view a request arrives on it
  if ("IntersectionObserver" in window) {
    const watch = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { watch.disconnect(); setTimeout(requestArrives, 4000); }
    }, { threshold: 0.3 });
    watch.observe(stage);
  } else {
    setTimeout(requestArrives, 4000);
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
      const anchor = docked.find((name) => name === "today");
      if (anchor) {
        anchorColumn.replaceChildren(header, icons, blockOf[anchor]);
        children[docked.indexOf(anchor)] = anchorColumn;
      } else {
        anchorColumn.replaceChildren(header, icons);
        children.unshift(anchorColumn);
      }
    } else {
      if (header.nextSibling !== icons || icons.nextSibling !== blocks) {
        win.insertBefore(header, blocks);
        win.insertBefore(icons, blocks);
      }
    }
    if (placeholderAt != null) {
      const holder = el("div", { class: "psf-placeholder" });
      holder.style.height = `${placeholderHeight}px`;
      if (state.landscape) holder.style.width = `${placeholderWidth - 2}px`;
      children.splice(placeholderAt, 0, holder);
    }
    // Moving a node, even to where it already is, loses the browser's hover on it, so only a changed order is applied
    const current = [...blocks.children];
    if (current.length !== children.length || children.some((child, i) => child !== current[i])) blocks.replaceChildren(...children);
    fitStage();
  }

  const anchorColumn = el("div", { class: "psf-anchor-column" });

  function stageHeight() {
    const panels = Object.values(state.floating).filter((f) => !f.panel.hidden).map((f) => f.panel);
    return Math.max(1148, ...[win, ...panels].map((node) => node.offsetHeight + 48));
  }

  function lowest(nodes) {
    // How far down a window or panel, or a group of them moving together, may go: its bottom stays inside the scene
    if (touch.matches) return Infinity;
    const height = stageHeight() - 24;
    return Math.min(...[...nodes].map((node) => Math.max(0, height - node.offsetHeight - node.offsetTop)));
  }

  function fitStage() {
    if (touch.matches) {
      // On a phone the window stands in the middle, and the scene is as tall as it needs
      stage.style.minHeight = `${Math.max(640, win.offsetTop + win.offsetHeight + 24)}px`;
    } else {
      // The scene holds the painting whole, and grows only as far as the tallest window or panel needs, never because
      // something was dragged down: what is dragged stops at its bottom, see lowest
      stage.style.minHeight = `${stageHeight()}px`;
    }
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
    const children = [...blocks.children];
    const holder = children.find((child) => child.classList.contains("psf-placeholder"));
    const docked = children.filter((child) => child !== holder);
    const least = headerAlone() ? 1 : 0;
    // Measured where the blocks stand without the space shown for the panel, so showing that space, which pushes the
    // blocks after it along, does not move the slot and the space with it back and forth
    const room = holder ? (state.landscape ? holder.offsetWidth : holder.offsetHeight + 4) : 0;
    const after = (child) => holder && children.indexOf(child) > children.indexOf(holder);
    let slot = docked.length;
    docked.forEach((child, index) => {
      const shown = rect(child);
      const r = after(child) ? (state.landscape ? { ...shown, left: shown.left - room } : { ...shown, top: shown.top - room }) : shown;
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

  const SNAP_DISTANCE = 20;
  // How far below the window a panel's top may be let go and still dock, and how see-through it is meanwhile, as the app
  const DOCK_ZONE = 40;

  function follow(move, up) {
    // Moves and the release are heard on the whole page rather than on what was pressed, which may be redrawn or moved
    // mid-drag (the graph redraws every second; a title moves into a panel of its own). The mouse's moves are taken
    // at most once a frame, the latest one, so the page lays itself out once per frame however fast the mouse reports
    let pending = null, frame = 0;
    const run = () => { frame = 0; const event = pending; pending = null; if (event) move(event); };
    const onMove = (event) => {
      stage.classList.add("psf-moving");
      if (!event.isTrusted) return move(event);
      pending = event;
      if (!frame) frame = requestAnimationFrame(run);
    };
    const end = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      if (frame) { cancelAnimationFrame(frame); run(); }
      stage.classList.remove("psf-moving");
      up();
      placeHotspots();
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  }

  // A snap once made holds until the panel is pulled this much further than the distance that made it, so a panel near
  // several edges at once settles on one rather than flicking between them
  const SNAP_RELEASE = 6;
  // Lining up along an edge already touched is gentler, as such lines lie close together (every block's top and bottom)
  const ALIGN_DISTANCE = 8;

  function snapPosition(x, y, width, height, neighbours, sideTargets, held, align = ALIGN_DISTANCE) {
    // Each way on its own: a panel's side snaps to touch a neighbour's side when within the snapping distance, and its
    // top or bottom to touch a neighbour's bottom or top. Only once touching does it also line up along that edge, its
    // top or bottom with the neighbour's (beside the window, with any block in it), or its left or right; otherwise it
    // slides freely along. `held` is the last snap, kept while within reach
    const pick = (raw, options, before, distance = SNAP_DISTANCE) => {
      const kept = before == null ? null : options.find((o) => Math.abs(o.v - before) < 0.5 && Math.abs(raw - o.v) <= distance + SNAP_RELEASE);
      if (kept) return kept;
      let best = null;
      for (const o of options) if (Math.abs(raw - o.v) <= distance && (!best || Math.abs(raw - o.v) < Math.abs(raw - best.v))) best = o;
      return best;
    };
    const sides = [], ends = [];
    for (const n of neighbours) {
      if (y <= n.bottom + SNAP_DISTANCE && y + height >= n.top - SNAP_DISTANCE) sides.push({ v: n.left - width, n }, { v: n.right, n });
      if (x <= n.right + SNAP_DISTANCE && x + width >= n.left - SNAP_DISTANCE) ends.push({ v: n.top - height, n }, { v: n.bottom, n });
    }
    let sx = pick(x, sides, held?.x), sy = pick(y, ends, held?.y);
    if (sx && !sy) {
      const lines = [{ v: sx.n.top }, { v: sx.n.bottom - height }];
      if (sx.n.isWindow) for (const t of sideTargets) lines.push({ v: t.top }, { v: t.bottom - height });
      sy = pick(y, lines, held?.y, align);
    } else if (sy && !sx) {
      sx = pick(x, [{ v: sy.n.left }, { v: sy.n.right - width }], held?.x, align);
    }
    return { x: sx ? sx.v : x, y: sy ? sy.v : y, held: { x: sx ? sx.v : null, y: sy ? sy.v : null } };
  }

  function liveSnap(panel, x, y, held = null, align = ALIGN_DISTANCE) {
    const w = rect(win);
    const neighbours = [{ ...w, isWindow: true }, ...shownPanels().filter((other) => other !== panel).map(rect)];
    const sideTargets = [...blocks.children].map(rect).filter((b) => b.top >= w.top && b.top < w.bottom).map((b) => ({ top: b.top, bottom: Math.min(b.bottom, w.bottom) }));
    // Positions are set from the stage's inner edge, measured from its outer edge
    const ix = stage.clientLeft, iy = stage.clientTop;
    const toStage = held && { x: held.x == null ? null : held.x + ix, y: held.y == null ? null : held.y + iy };
    const snapped = snapPosition(x + ix, y + iy, panel.offsetWidth, panel.offsetHeight, neighbours, sideTargets, toStage, align);
    const back = { x: snapped.held.x == null ? null : snapped.held.x - ix, y: snapped.held.y == null ? null : snapped.held.y - iy };
    return [snapped.x - ix, snapped.y - iy, back];
  }

  function dockSlotFor(panel, pointerX, pointerY, x, y) {
    // As the app: it docks with the pointer over the window, or with its top let go just below the window's bottom,
    // mostly in line with it; elsewhere it floats
    if (state.settingsOpen) return null;
    const w = rect(win);
    if (pointerX >= w.left && pointerX < w.right && pointerY >= w.top && pointerY < w.bottom) return dockSlot(pointerX, pointerY);
    const width = panel.offsetWidth;
    const inLine = Math.min(x + width, w.right) - Math.max(x, w.left) > Math.min(width, w.width) / 2;
    if (inLine && y >= w.bottom - SNAP_DISTANCE && y <= w.bottom + DOCK_ZONE) return dockSlot(w.left + 1, w.bottom + 1);
    return null;
  }
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

  function groupBounds(group) {
    // The edges of a window and the panels moving with it, from the scene's inner edge
    const nodes = [...group];
    return {
      left: Math.min(...nodes.map((n) => n.offsetLeft)), top: Math.min(...nodes.map((n) => n.offsetTop)),
      right: Math.max(...nodes.map((n) => n.offsetLeft + n.offsetWidth)),
    };
  }

  function moveFloating(panel, event) {
    // A floating panel taken by anything but its title moves with everything snapped to it, the window included
    const group = groupOf(panel);
    if (group.size === 1) return dragPanel(panel.querySelector(".psf-block").dataset.name, event);
    event.preventDefault();
    const start = { x: event.clientX, y: event.clientY, places: [...group].map((node) => [node, node.offsetLeft, node.offsetTop]) };
    const room = lowest(group), bounds = groupBounds(group);
    const move = (moveEvent) => {
      // The group moves as one, kept whole inside the scene
      const dx = Math.max(Math.min(0, -bounds.left), Math.min(moveEvent.clientX - start.x, Math.max(0, stage.clientWidth - bounds.right)));
      const dy = Math.max(Math.min(0, -bounds.top), Math.min(moveEvent.clientY - start.y, room));
      start.places.forEach(([node, left, top]) => { node.style.left = `${left + dx}px`; node.style.top = `${top + dy}px`; });
      hideTip();
    };
    follow(move, () => settle(panel, group));
  }

  // How far outside the window a block's title may be dragged and still be put in order rather than float, and how far
  // the pointer moves before a press becomes a drag, as the app
  const REORDER_MARGIN = 24;
  const DRAG_DISTANCE = 5;

  function reorderAt(name, px, py) {
    // The block goes after every other block in the window whose middle the pointer has passed
    const docked = state.order.filter((n) => wanted(n) && !state.floating[n]);
    const others = docked.filter((n) => n !== name);
    const passed = others.filter((n) => {
      const r = rect(blockOf[n]);
      return state.landscape ? px > r.left + r.width / 2 : py > r.top + r.height / 2;
    });
    const before = others.find((n) => !passed.includes(n));
    const current = docked.indexOf(name), target = before ? docked.indexOf(before) - (docked.indexOf(before) > current ? 1 : 0) : docked.length - 1;
    if (target === current) return;
    state.order = state.order.filter((n) => n !== name);
    state.order.splice(before ? state.order.indexOf(before) : state.order.length, 0, name);
    arrange();
  }

  function dragPanel(name, event) {
    // A panel moved alone, by its title or, floating, by its body: out of the window it snaps to what it comes near as it
    // moves; with the pointer over the window, or its top just below the window, a blue space shows where it will dock
    // and it turns see-through, as in the app
    event.preventDefault();
    const block = blockOf[name];
    const start = { x: event.clientX, y: event.clientY };
    const blockRect = rect(block);
    const s0 = stage.getBoundingClientRect();
    const grab = { x: start.x - s0.left - blockRect.left, y: start.y - s0.top - blockRect.top };
    let panel = state.floating[name]?.panel || null;
    let dragging = false;
    let slot = null;
    // The snap last made, held while the panel stays within reach of it
    let held = null;
    const move = (moveEvent) => {
      const s = stage.getBoundingClientRect();
      const px = moveEvent.clientX - s.left, py = moveEvent.clientY - s.top;
      if (!dragging) {
        if (Math.hypot(moveEvent.clientX - start.x, moveEvent.clientY - start.y) < DRAG_DISTANCE) return;
        dragging = true;
        markUsed("drag");
        if (panel) panel.classList.add("psf-dragging");
      }
      if (!panel) {
        // In the window, as the app: outlined in blue, it passes the block under the pointer as the pointer crosses that
        // block's middle; dragged clear of the window, it floats in a panel of its own
        const w = rect(win);
        if (px > w.left - REORDER_MARGIN && px < w.right + REORDER_MARGIN && py > w.top - REORDER_MARGIN && py < w.bottom + REORDER_MARGIN) {
          block.classList.add("psf-reordering");
          reorderAt(name, px, py);
          hideTip();
          return;
        }
        block.classList.remove("psf-reordering");
        panel = floatOut(name, px - grab.x, py - grab.y);
        panel.classList.add("psf-dragging");
      }
      let x = px - grab.x - stage.clientLeft, y = Math.max(0, py - grab.y - stage.clientTop);
      // Where the pointer puts it decides docking, though it is drawn no lower than the scene's bottom
      const newSlot = dockSlotFor(panel, px, py, x + stage.clientLeft, y + stage.clientTop);
      // Kept inside the scene, so it can never be lost past an edge
      x = Math.max(0, Math.min(x, stage.clientWidth - panel.offsetWidth));
      if (!touch.matches) y = Math.min(y, Math.max(0, stageHeight() - 24 - panel.offsetHeight));
      if (newSlot == null) [x, y, held] = liveSnap(panel, x, y, held);
      else held = null;
      panel.style.left = `${x}px`;
      panel.style.top = `${y}px`;
      panel.classList.toggle("psf-docking", newSlot != null);
      if (newSlot !== slot) { slot = newSlot; arrange(slot, panel.offsetHeight, panel.offsetWidth); }
      state.pointerInside.main = true;
      updateGlass();
      hideTip();
    };
    follow(move, () => {
      if (!dragging) return;
      block.classList.remove("psf-reordering");
      if (!panel) return;
      panel.classList.remove("psf-dragging", "psf-docking");
      if (slot != null) dockBack(name, slot);
      else { refreshAttached(); arrange(); fitStage(); }
      updateGlass();
    });
  }

  function snap(panel) {
    // A panel put down alone snaps as it would while dragged
    // Put down in one go, not dragged, it lines up from as far as it snaps
    const [x, y] = liveSnap(panel, panel.offsetLeft, panel.offsetTop, null, SNAP_DISTANCE);
    panel.style.left = `${x}px`;
    panel.style.top = `${y}px`;
    refreshAttached();
    fitStage();
    updateGlass();
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

  // What a press keeps for itself, rather than moving the window, as in the app: buttons and fields, calendar days, a
  // friend request, your name, and a panel's title, which takes the panel. The graph and friends' rows move it
  const CLICKED = "button, input, label, .psf-day, .psf-strip, .psf-grip, .psf-account-name, .psf-request-row";

  win.addEventListener("pointerdown", (event) => {
    if (touch.matches || event.button !== 0 || event.target.closest(CLICKED)) return;
    const start = { x: event.clientX, y: event.clientY, left: win.offsetLeft, top: win.offsetTop };
    // Everything snapped to the window, directly or through another panel, moves with it
    const group = groupOf(win);
    const attached = [...group].filter((node) => node !== win).map((node) => ({ panel: node, left: node.offsetLeft, top: node.offsetTop }));
    const room = lowest(group), bounds = groupBounds(group);
    event.preventDefault();
    const move = (moveEvent) => {
      const dx = Math.max(Math.min(0, -bounds.left), Math.min(moveEvent.clientX - start.x, Math.max(0, stage.clientWidth - bounds.right)));
      const dy = Math.min(Math.max(Math.min(0, -bounds.top), moveEvent.clientY - start.y), room);
      win.style.left = `${start.left + dx}px`;
      win.style.top = `${start.top + dy}px`;
      attached.forEach((a) => { a.panel.style.left = `${a.left + dx}px`; a.panel.style.top = `${a.top + dy}px`; });
      fitStage();
      hideTip();
    };
    // The window snaps to a panel it was brought up to, as a panel snaps to it
    follow(move, () => { if (!touch.matches) settle(win, group); });
  });

  // On a phone the window stays put, but it can be tugged: it gives a little, less the further it is pulled, and springs
  // back once let go. Its title bar and the panels' titles give every way; elsewhere it gives sideways only, so
  // swiping up and down still scrolls the page. What has a job of its own is left to it, and the graph to its readout
  const TUG_REACH = 36;
  const TUG_START = 6;
  const UNTUGGED = "button, input, label, .psf-day, .psf-grip, .psf-account-name, .psf-request-row, .psf-chart-box, .psf-menu";
  win.addEventListener("pointerdown", (event) => {
    if (!touch.matches || !event.isPrimary || event.target.closest(UNTUGGED)) return;
    const start = { x: event.clientX, y: event.clientY };
    const everyWay = !!event.target.closest(".psf-titlebar, .psf-strip");
    const give = (pulled) => Math.sign(pulled) * TUG_REACH * (1 - Math.exp(-Math.abs(pulled) / 100));
    let tugging = false;
    const move = (moveEvent) => {
      if (moveEvent.pointerId !== event.pointerId) return;
      const dx = moveEvent.clientX - start.x, dy = everyWay ? moveEvent.clientY - start.y : 0;
      if (!tugging) {
        // A tap stays a tap: the tug begins only once the finger has moved
        if (Math.hypot(dx, dy) < TUG_START) return;
        tugging = true;
        try { win.setPointerCapture(event.pointerId); } catch (error) { /* moves still reach it */ }
        win.style.transition = "none";
        hideTip();
      }
      win.style.translate = `${give(dx)}px ${give(dy)}px`;
    };
    const end = (endEvent) => {
      if (endEvent.pointerId !== event.pointerId) return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      if (!tugging) return;
      // Back with a small overshoot, as if on a spring
      win.style.transition = "translate .45s cubic-bezier(.34, 1.56, .64, 1)";
      win.style.translate = "";
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  });

  stage.addEventListener("dragstart", (event) => event.preventDefault());
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
    dragPanel(stripNode.closest(".psf-block").dataset.name, event);
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
      const solid = transparencyOpen ? false : touch.matches ? !stageAway : [...group].some(inside) || (withMain && !!menu);
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
    stageAway = !event.target.closest(".psf-window, .psf-floating, .psf-menu, .psf-app-window");
    updateGlass();
  });

  // ----- Tips: a pulsing dot on each main feature, explained under the pointer, gone once the feature is used. A few
  // at a time, in this order, so the demo grows quieter as it is learnt, as the app does -----

  // Each tip is an arrow pointing at its feature: where the arrow's tip goes, and which way it points
  const HOTSPOTS = [
    { id: "timer", target: () => today_.metric, at: (r) => [r.left + 206, r.top + r.height / 2, "left"],
      text: "Counts by itself while you draw." },
    { id: "icons", target: () => icons, at: (r) => [r.right - 98, r.top + r.height / 2, "right"], text: "Show or hide each panel." },
    { id: "drag", target: () => [...blocks.querySelectorAll(".psf-block:not(.psf-today) .psf-strip")][0], at: (r) => [r.left + 112, r.top + r.height / 2, "left"],
      text: "Drag a title to pull the panel out." },
    { id: "fade", target: () => canvas, at: (r) => [r.left + 4, r.top + 80, "right"],
      text: "Point at the painting: PS Focus fades so your art shows through." },
    { id: "status", target: () => statusButton, at: (r) => [r.left + r.width / 2, r.bottom + 2, "up"], text: "Set Away, Invisible or Offline." },
    { id: "settings", target: () => settingsButton, at: (r) => [r.left - 2, r.top + r.height / 2, "right"], text: "Settings" },
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
    const waiting = HOTSPOTS.filter((spot) => {
      if (used.has(spot.id)) return false;
      // On a phone the window and its panels stay put, and the line above the demo says how the fading works
      if (touch.matches && (spot.id === "drag" || spot.id === "fade")) return false;
      const target = spot.target();
      return target && target.offsetParent !== null && !target.closest("[hidden]");
    });
    hotspots.replaceChildren();
    // A few at a time, in order; one that would land on an arrow already placed gives way to the next
    const placed = [];
    for (const spot of waiting) {
      if (placed.length >= TIPS_AT_ONCE) break;
      const [x, y, direction] = spot.at(rect(spot.target()));
      // An arrow in the app's blue, its tip at the point, nudging towards the feature
      const dot = el("button", { type: "button", class: `psf-hotspot psf-point-${direction}`, "aria-label": spot.text },
        svg('<path d="M1 7H10M6 2.5L10.5 7L6 11.5" stroke-width="2.4"/>', 18));
      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;
      dot.addEventListener("pointerenter", () => showTip(dot, spot.text, true));
      dot.addEventListener("pointerleave", hideTip);
      // A click once the tip has been read puts the arrow away for good; on a phone the first tap shows the tip
      dot.addEventListener("click", () => (tip ? markUsed(spot.id) : showTip(dot, spot.text, true)));
      hotspots.append(dot);
      // Room for its nudge, so two arrows never touch as they move
      const box = rect(dot);
      const reach = { left: box.left - 6, top: box.top - 6, right: box.right + 6, bottom: box.bottom + 6 };
      if (placed.some((other) => overlaps(reach, other))) { dot.remove(); continue; }
      placed.push(reach);
    }
  }

  // ----- The clock -----

  setInterval(() => {
    if (!state.drawing || state.paused) return;
    const hour = new Date().getHours();
    todayHours[hour] += 1;
    if (state.todayProgram !== "Photoshop") state.programSeconds[state.todayProgram] += 1;
    lifetime += 1;
    renderToday();
    if (lifetime % 60 === 0) renderStats();
    if (state.shown.graph && (state.period === "Day" || state.period === "Week") && !chart.matches(":hover")) renderGraph();
  }, 1000);

  // ----- What each panel is for, under the pointer on its title, after a moment -----

  const PANEL_TIPS = {
    today: "Your time in Photoshop today, past two weeks and in total.",
    graph: "How much you draw, from today to the past year.",
    calendar: "Days with 15+ minutes turn blue. Keep your streak going.",
    stats: "Your averages, best day and longest session.",
    friends: "Friends' hours, and who's drawing now.",
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

  renderAccount();
  renderToday();
  renderGraph();
  renderCalendar();
  renderFriends();
  arrange();
  updateGlass();

  // For checking states while the page is built, from the browser's console
  window.psfDemo = { state, toggleModule, toggleSettings, chooseOrientation, requestArrives, floatOut, snap, dockBack, updateGlass, renderCalendar, renderGraph, setPointer: (x, y) => { pointer = x == null ? null : { x, y }; updateGlass(); } };
})();
