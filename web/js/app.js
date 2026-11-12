// UI layer. Holds no calculation or behaviour rules of its own: every
// change goes to web/py/model.py (Python, the same rules as the desktop
// app) as an action, and this file renders the state + view that come
// back. Controls are bound declaratively in index.html:
//   data-path="array.spacing_m"    editable field bound to state
//   data-length                    shown in the selected length unit
//   data-text="info.length_text"   text from the view
//   data-show="angle" / "!x"       visible when view.show.angle is (not) true
//   data-action="makeup_apply"     button that sends that action
//   data-enabled="optimum_enabled" button enabled when that view value is true

import { initEngine } from "./engine.js";
import { HELP } from "./help.js";

const $ = (id) => document.getElementById(id);
const app = $("app");
const UNIT_SCALE = { m: 1, cm: 0.01, mm: 0.001 };
const UNIT_DECIMALS = { m: 3, cm: 1, mm: 0 };
const UNIT_STEP = { m: 0.01, cm: 1, mm: 10 };
const STORAGE_KEY = "sadrt.lastSession";
const TAB_KEY = "sadrt.tab";

let model = null; // Python module (Pyodide proxy)
let state = null;
let view = null;
let meta = null;

// --------------------------------------------------------------- helpers --
function get(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function setStatus(text, kind = "loading") {
  $("status").textContent = text;
  $("status").dataset.state = kind;
}

function unit() {
  return state.units.length_unit;
}

function toDisplay(meters) {
  const u = unit();
  const v = meters / UNIT_SCALE[u];
  return String(Number(v.toFixed(UNIT_DECIMALS[u])));
}

// Number("") is 0, which would pass as a real value and get clamped to the
// field's minimum. A blank field means "no value": NaN, so the caller
// puts the last good value back (the desktop ignores a blank field too).
function toNumber(text) {
  return String(text).trim() === "" ? NaN : Number(text);
}

function toMeters(display) {
  return Math.round(toNumber(display) * UNIT_SCALE[unit()] * 1000) / 1000;
}

function fmtNumber(value) {
  return typeof value === "number" ? String(Number(value.toFixed(6))) : String(value ?? "");
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function safeFilename(name, fallback) {
  const cleaned = (name || "").replace(/[\\/:*?"<>|\n\r\t]+/g, " ").trim().slice(0, 80);
  return cleaned || fallback;
}

// --------------------------------------------------------------- dialogs --
function showDialog(title, body, { confirm = false, okLabel = "OK" } = {}) {
  const dlg = $("dialog");
  $("dialog-title").textContent = title;
  const container = $("dialog-body");
  container.replaceChildren();
  for (const para of [].concat(body)) {
    if (Array.isArray(para)) {
      const ul = document.createElement("ul");
      ul.append(...para.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
      container.append(ul);
    } else {
      container.append(Object.assign(document.createElement("p"), { textContent: para }));
    }
  }
  $("dialog-cancel").hidden = !confirm;
  $("dialog-ok").textContent = okLabel;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true }));
}

// ------------------------------------------------------------ model calls --
function applyResponse(json) {
  const out = JSON.parse(json);
  if (out.error) throw new Error(out.error);
  state = out.state;
  view = out.view;
  render();
  persist();
  return out;
}

let pending = null;
function dispatch(action) {
  return applyResponse(model.dispatch(JSON.stringify(state), JSON.stringify(action)));
}

// Slider drags can fire faster than we need to recompute; collapse them to
// one dispatch per animation frame with the latest value (the desktop does
// the same with after_idle).
function dispatchCoalesced(action) {
  const first = pending === null;
  pending = action;
  if (first) {
    requestAnimationFrame(() => {
      const a = pending;
      pending = null;
      dispatch(a);
    });
  }
}

let persistTimer = null;
function persist() {
  clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, model.save(JSON.stringify(state)));
    } catch {
      /* private mode / storage blocked: the app works without it */
    }
  }, 400);
}

// ---------------------------------------------------------------- render --
function fillSelect(select, options) {
  // options: [[value, label], ...]; only rebuild when the list changed
  const sig = JSON.stringify(options);
  if (select.dataset.sig === sig) return;
  select.dataset.sig = sig;
  select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
}

function optionsFor(name) {
  switch (name) {
    case "topologies": return Object.entries(meta.topologies);
    case "patterns": return [...meta.patterns, meta.custom].map((p) => [p, p]);
    case "windows": return meta.windows.map((w) => [w, w]);
    case "xy_conventions": return meta.xy_conventions.map((x) => [x, x]);
    case "dsp_rates": return Object.entries(meta.dsp_rates).map(([label, hz]) => [String(hz), label]);
    case "profiles": return [meta.custom, ...view.profiles].map((p) => [p, p]);
    default: return [];
  }
}

function render() {
  const u = unit();
  for (const el of app.querySelectorAll("[data-options]")) fillSelect(el, optionsFor(el.dataset.options));

  for (const el of app.querySelectorAll("[data-path]")) {
    // Only free text (the show name) commits on every keystroke, so it's the
    // one field to leave alone while it has focus. Number fields commit on
    // Enter/blur, so they're redrawn even when focused: that shows the value
    // the model actually kept (e.g. Count 999 clamped to 12) or puts the
    // last good value back after a blank or invalid entry.
    if (el === document.activeElement && el.type === "text") continue;
    const value = get(state, el.dataset.path);
    if (el.type === "checkbox") el.checked = Boolean(value);
    else if ("length" in el.dataset) {
      el.value = toDisplay(value);
      el.step = UNIT_STEP[u];
    } else if (el.tagName === "SELECT") el.value = String(value);
    else el.value = el.type === "range" ? value : fmtNumber(value);
  }
  for (const el of app.querySelectorAll("[data-view-length]")) {
    el.value = toDisplay(get(view, el.dataset.viewLength)); // commits on Enter/blur, see above
    el.step = UNIT_STEP[u];
  }
  for (const el of app.querySelectorAll("[data-unit]")) el.textContent = u;
  for (const el of app.querySelectorAll("[data-text]")) el.textContent = get(view, el.dataset.text) ?? "";
  for (const el of app.querySelectorAll("[data-text-state]")) el.textContent = get(state, el.dataset.textState) ?? "";
  for (const el of app.querySelectorAll("[data-show]")) {
    const key = el.dataset.show;
    const on = key.startsWith("!") ? !view.show[key.slice(1)] : Boolean(view.show[key]);
    el.hidden = !on;
  }
  for (const el of app.querySelectorAll("[data-enabled]")) el.disabled = !get(view, el.dataset.enabled);
  $("f-count").max = view.count_max;
  for (const el of document.querySelectorAll("[data-help-from]")) {
    $(el.getAttribute("popovertarget")).textContent = get(view, el.dataset.helpFrom);
  }

  renderPrealign();
  renderTable();
  renderLayout();
  $("version").textContent = `v${view.version}`;
}

function renderPrealign() {
  const p = view.prealign;
  $("prealign-error").hidden = !p.error;
  $("prealign-controls").hidden = Boolean(p.error);
  if (p.error) {
    $("prealign-error").textContent = p.error;
    return;
  }
  fillSelect($("f-pa-main"), p.mains.map((m) => [m, m]));
  fillSelect($("f-pa-sub"), p.subs.map((s) => [s, s]));
  $("f-pa-main").value = p.main;
  $("f-pa-sub").value = p.sub;
  for (const [id, text, pol] of [["pa-main-text", p.main_text, p.main_polarity], ["pa-sub-text", p.sub_text, p.sub_polarity]]) {
    $(id).textContent = text;
    $(id).dataset.polarity = pol || "";
  }
}

function renderTable() {
  const t = view.table;
  const unitLabel = t.unit;
  $("th-delay").textContent = `Delay (${unitLabel})`;
  $("th-delay-total").textContent = `Delay + Group (${unitLabel})`;
  $("table-error").hidden = !view.error;
  $("table-error").textContent = view.error ? `Can't compute: ${view.error}` : "";

  const tbody = $("results");
  const editing = tbody.contains(document.activeElement);
  if (editing && t.editable) {
    // Don't rebuild under the cursor in Manual mode (focus would be lost);
    // refresh values in place. Cells commit on Enter/blur, so writing the
    // kept value back into the focused cell is safe.
    t.rows.forEach((r, i) => {
      const tr = tbody.rows[i];
      if (!tr) return;
      for (const el of tr.querySelectorAll('input[type="number"]')) {
        el.value = fmtNumber(state.manual[el.dataset.field][i]);
      }
      tr.cells[3].textContent = r.text.rotation;
      tr.cells[4].textContent = r.text.delay;
      tr.cells[5].textContent = r.text.delay_total;
      tr.cells[7].textContent = r.text.gain_total;
    });
    return;
  }
  const rows = t.rows.map((r, i) => {
    const tr = document.createElement("tr");
    const cell = (text, cls) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (cls) td.className = cls;
      return td;
    };
    const input = (field, value, label) => {
      const td = document.createElement("td");
      const el = Object.assign(document.createElement("input"), {
        type: "number", step: field === "gain_db" ? "0.1" : "0.01", value: fmtNumber(value),
      });
      el.dataset.row = i;
      el.dataset.field = field;
      el.setAttribute("aria-label", `Sub ${r.index} ${label}`);
      td.append(el);
      return td;
    };
    tr.append(cell(String(r.index)));
    if (t.editable) {
      // Y and X are typed directly; the X/Y convention decides which one the
      // model treats as depth (d&b: X, L-Acoustics: Y)
      tr.append(input("y_m", state.manual.y_m[i], "Y"), input("x_m", state.manual.x_m[i], "X"));
    } else {
      tr.append(cell(r.text.y), cell(r.text.x));
    }
    tr.append(cell(r.text.rotation), cell(r.text.delay), cell(r.text.delay_total));
    tr.append(t.editable ? input("gain_db", state.manual.gain_db[i], "gain trim") : cell(r.text.gain));
    tr.append(cell(r.text.gain_total));
    if (t.editable) {
      const td = document.createElement("td");
      const label = document.createElement("label");
      label.className = "check";
      const cb = Object.assign(document.createElement("input"), { type: "checkbox", checked: r.manual_reversed });
      cb.dataset.row = i;
      cb.dataset.field = "reversed";
      label.append(cb, " Reversed");
      td.append(label);
      tr.append(td);
    } else {
      tr.append(cell(r.text.polarity, r.polarity_reversed ? "pol-rev" : ""));
    }
    return tr;
  });
  tbody.replaceChildren(...rows);
}

// ---------------------------------------------------------------- layout --
// Draws view.plot (geometry from shared/layout_plot.py, in metres) as SVG.
// Same scale on both axes, X left to right, Y bottom to top. The desktop
// draws the same geometry on a Tk Canvas (_draw_layout_plot).
const SVG_NS = "http://www.w3.org/2000/svg";

// shared/layout_plot.py:nice_step
function niceStep(span, target = 6) {
  if (!(span > 0)) return 1;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 5, 10]) if (raw <= m * mag) return m * mag;
  return 10 * mag;
}

function svgEl(tag, attrs, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

function renderLayout() {
  const svg = $("layout-plot");
  const plot = view && view.plot;
  const W = svg.clientWidth, H = svg.clientHeight;
  if (!plot || !W || !H) return; // hidden tab: drawn when it's shown (ResizeObserver)
  const m = { l: 44, r: 12, t: 12, b: 30 };
  const pw = W - m.l - m.r, ph = H - m.t - m.b;
  const b = plot.bounds;
  // Equal scale: fit the larger span, centre the other one.
  const scale = Math.min(pw / (b.xmax - b.xmin), ph / (b.ymax - b.ymin));
  const cx = (b.xmin + b.xmax) / 2, cy = (b.ymin + b.ymax) / 2;
  const x0 = cx - pw / scale / 2, x1 = cx + pw / scale / 2;
  const y0 = cy - ph / scale / 2, y1 = cy + ph / scale / 2;
  const X = (x) => m.l + (x - x0) * scale;
  const Y = (y) => m.t + (y1 - y) * scale;
  const pt = ([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`;

  const parts = [];
  const step = niceStep(Math.max(x1 - x0, y1 - y0));
  const fmt = (v) => String(Number(v.toFixed(3)));
  for (let v = Math.ceil(x0 / step) * step; v <= x1 + 1e-9; v += step) {
    parts.push(svgEl("line", { class: "grid", x1: X(v), x2: X(v), y1: m.t, y2: m.t + ph }));
    parts.push(svgEl("text", { class: "tick", x: X(v), y: m.t + ph + 13, "text-anchor": "middle" }, fmt(v)));
  }
  for (let v = Math.ceil(y0 / step) * step; v <= y1 + 1e-9; v += step) {
    parts.push(svgEl("line", { class: "grid", y1: Y(v), y2: Y(v), x1: m.l, x2: m.l + pw }));
    parts.push(svgEl("text", { class: "tick", x: m.l - 5, y: Y(v) + 3.5, "text-anchor": "end" }, fmt(v)));
  }
  parts.push(svgEl("rect", { class: "axis", x: m.l, y: m.t, width: pw, height: ph, fill: "none" }));
  parts.push(svgEl("text", { class: "axis-title", x: m.l + pw, y: H - 3, "text-anchor": "end" }, "X (m) →"));
  parts.push(svgEl("text", { class: "axis-title", x: 4, y: m.t + 8, "text-anchor": "start" }, "↑ Y (m)"));

  for (const s of plot.subs) {
    const rev = s.reversed ? " rev" : "";
    if (s.outline.length) parts.push(svgEl("polygon", { class: `box${rev}`, points: s.outline.map(pt).join(" ") }));
    else parts.push(svgEl("circle", { class: `dot${rev}`, cx: X(s.centre[0]), cy: Y(s.centre[1]), r: 3.5 }));
    const [[ax, ay], [bx, by]] = s.aim;
    const px0 = X(ax), py0 = Y(ay), px1 = X(bx), py1 = Y(by);
    parts.push(svgEl("line", { class: "aim", x1: px0, y1: py0, x2: px1, y2: py1 }));
    const ang = Math.atan2(py1 - py0, px1 - px0), hl = 6;
    const head = [[px1, py1], [px1 - hl * Math.cos(ang - 0.45), py1 - hl * Math.sin(ang - 0.45)],
      [px1 - hl * Math.cos(ang + 0.45), py1 - hl * Math.sin(ang + 0.45)]];
    parts.push(svgEl("polygon", { class: "aim-head", points: head.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ") }));
  }
  for (const l of plot.labels) {
    parts.push(svgEl("text", { class: "label", x: X(l.x), y: Y(l.y) + 3.5, "text-anchor": "middle" }, l.text));
  }
  // Which way the audience is (rotation 0)
  const [fx, fy] = plot.forward;
  const arrow = fx > 0 ? "→" : fx < 0 ? "←" : fy > 0 ? "↑" : "↓";
  const ax = fx > 0 ? m.l + pw - 6 : fx < 0 ? m.l + 6 : m.l + pw / 2;
  const ay = fy > 0 ? m.t + 14 : fy < 0 ? m.t + ph - 6 : m.t + ph / 2;
  parts.push(svgEl("text", { class: "axis-title", x: ax, y: ay, "text-anchor": fx > 0 ? "end" : fx < 0 ? "start" : "middle" },
    `audience ${arrow}`));
  svg.replaceChildren(...parts);
}

// ---------------------------------------------------------------- events --
function readField(el) {
  if (el.type === "checkbox") return el.checked;
  if ("bool" in el.dataset) return el.value === "true";
  if ("int" in el.dataset) return parseInt(el.value, 10);
  if ("length" in el.dataset) return toMeters(el.value);
  if (el.type === "number" || el.type === "range") return toNumber(el.value);
  return el.value;
}

function onFieldCommit(el) {
  const value = readField(el);
  if (typeof value === "number" && !Number.isFinite(value)) {
    render(); // put the last good value back
    return;
  }
  const action = { type: "set", path: el.dataset.path, value };
  if (el.type === "range") dispatchCoalesced(action);
  else dispatch(action);
}

function bindEvents() {
  app.addEventListener("input", (e) => {
    const el = e.target;
    if (el.matches('input[type="range"][data-path]')) onFieldCommit(el);
    else if (el.matches('input[type="text"][data-path]')) onFieldCommit(el);
  });
  app.addEventListener("change", (e) => {
    const el = e.target;
    if (el.matches("[data-path]") && el.type !== "range" && el.type !== "text") onFieldCommit(el);
    else if (el.matches("[data-action-input]")) {
      const v = toMeters(el.value);
      if (Number.isFinite(v)) dispatch({ type: el.dataset.actionInput, value: v });
      else render();
    } else if (el.matches("[data-prealign]")) {
      dispatch({ type: `prealign_${el.dataset.prealign}`, value: el.value });
    } else if (el.matches("#results input")) {
      const value = el.type === "checkbox" ? el.checked : toNumber(el.value);
      if (typeof value === "number" && !Number.isFinite(value)) return render();
      dispatch({ type: "manual", row: Number(el.dataset.row), field: el.dataset.field, value });
    }
  });
  // Enter in a number field commits it, like the desktop's <Return> binding.
  app.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches('input[type="number"]')) e.target.dispatchEvent(new Event("change", { bubbles: true }));
  });
  app.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (btn && !btn.disabled) dispatch({ type: btn.dataset.action });
  });

  $("btn-new").addEventListener("click", async () => {
    if (await showDialog("New project", "Reset every setting to defaults? Anything unsaved will be lost.", { confirm: true, okLabel: "Reset" })) {
      dispatch({ type: "new" });
      $("project-status").textContent = "unsaved project";
    }
  });
  $("btn-save").addEventListener("click", () => {
    const filename = `${safeFilename(state.name, "show")}.sadrt`;
    download(filename, model.save(JSON.stringify(state)), "application/json");
    $("project-status").textContent = `saved: ${filename}`;
  });
  $("btn-load").addEventListener("click", () => $("file-load").click());
  $("file-load").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    let out;
    try {
      out = applyResponse(model.load(JSON.stringify(state), await file.text()));
    } catch (err) {
      showDialog("Load failed", [err.message, "The current settings were left unchanged."]);
      return;
    }
    $("project-status").textContent = `loaded: ${file.name}`;
    if (out.warnings.length) {
      showDialog("Loaded with warnings", ["Project loaded, but some values needed fixing up:", out.warnings]);
    }
  });
  $("btn-copy").addEventListener("click", copyTable);
  $("btn-csv").addEventListener("click", exportCsv);
}

// --------------------------------------------------------------- results --
function tableHeaders() {
  return [...document.querySelectorAll(".results thead th")].map((th) => th.textContent);
}

async function copyTable() {
  const lines = [tableHeaders().join("\t")];
  for (const r of view.table.rows) {
    const t = r.text;
    lines.push([r.index, t.y, t.x, t.rotation, t.delay, t.delay_total, t.gain, t.gain_total, t.polarity].join("\t"));
  }
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    setStatus("Table copied to clipboard", "ready");
  } catch {
    setStatus("Couldn't copy: the browser blocked clipboard access", "error");
  }
}

function exportCsv() {
  const rate = state.dsp.sample_rate_hz;
  const header = ["Sub", "X (m)", "Y (m)", "Rotation (deg)", "Delay (ms)", "Delay + Group (ms)",
    `Delay (samples @ ${rate} Hz)`, `Delay + Group (samples @ ${rate} Hz)`, "Gain Trim (dB)", "Gain + Group (dB)", "Polarity"];
  const csvCell = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const lines = [header.map(csvCell).join(",")];
  for (const r of view.table.rows) {
    lines.push([r.index, fmtNumber(r.x_m), fmtNumber(r.y_m), fmtNumber(r.rotation_deg), fmtNumber(r.delay_ms),
      fmtNumber(r.delay_total_ms), r.delay_samples, r.delay_total_samples, fmtNumber(r.gain_db),
      fmtNumber(r.gain_total_db), r.polarity_reversed ? "Reversed" : "Normal"].map(csvCell).join(","));
  }
  download(`${safeFilename(state.name, "show")}-subs.csv`, lines.join("\r\n") + "\r\n", "text/csv");
}

// ------------------------------------------------------------- help + tabs --
function setupHelp() {
  let n = 0;
  for (const btn of document.querySelectorAll("button.help")) {
    const id = `help-${n++}`;
    const pop = Object.assign(document.createElement("div"), { id, className: "help-pop" });
    pop.popover = "auto";
    pop.textContent = HELP[btn.dataset.help] ?? "";
    document.body.append(pop);
    btn.type = "button";
    btn.textContent = "?";
    btn.setAttribute("popovertarget", id);
    if (!btn.hasAttribute("aria-label")) btn.setAttribute("aria-label", "Help");
    // Position under the button; flip above it if it doesn't fit below, and
    // keep it inside the window either way (it's position: fixed, so
    // scrolling the page wouldn't bring a cut-off part into view).
    pop.addEventListener("toggle", (e) => {
      if (e.newState !== "open") return;
      const r = btn.getBoundingClientRect();
      const margin = 16, gap = 6;
      const width = Math.min(420, window.innerWidth - 2 * margin);
      pop.style.width = `${width}px`;
      pop.style.maxHeight = `${window.innerHeight - 2 * margin}px`;
      pop.style.left = `${Math.max(margin, Math.min(r.left, window.innerWidth - width - margin))}px`;
      const h = pop.offsetHeight;
      const below = window.innerHeight - r.bottom - gap - margin;
      const above = r.top - gap - margin;
      let top;
      if (h <= below) top = r.bottom + gap;
      else if (h <= above) top = r.top - gap - h;
      else top = Math.max(margin, window.innerHeight - margin - h);
      pop.style.top = `${top}px`;
    });
  }
}

function setupTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const select = (tab) => {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      $(t.getAttribute("aria-controls")).hidden = !on;
    }
    try { localStorage.setItem(TAB_KEY, tab.id); } catch { /* optional */ }
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => select(t));
    t.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      const next = tabs[(i + step + tabs.length) % tabs.length];
      select(next);
      next.focus();
    });
  });
  let saved = null;
  try { saved = localStorage.getItem(TAB_KEY); } catch { /* optional */ }
  select(tabs.find((t) => t.id === saved) || tabs[0]);
}

// ------------------------------------------------------------------ start --
setupTabs();
setupHelp();
bindEvents();
new ResizeObserver(() => renderLayout()).observe($("layout-plot"));
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((e) => console.warn("Service worker not registered:", e));
}

initEngine({ onStatus: (m) => setStatus(m) })
  .then((engine) => {
    model = engine.pyodide.pyimport("model");
    const first = JSON.parse(model.init());
    meta = first;
    state = first.state;
    view = first.view;
    let restored = false;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const out = JSON.parse(model.load(JSON.stringify(state), saved));
        if (!out.error) {
          state = out.state;
          view = out.view;
          restored = true;
        }
      }
    } catch { /* nothing saved, or storage blocked */ }
    render();
    app.inert = false;
    setStatus(`Ready${restored ? " · restored last session" : ""} · loaded in ${(engine.loadMs / 1000).toFixed(1)} s`, "ready");
  })
  .catch((e) => {
    console.error(e);
    setStatus(navigator.onLine ? `Engine failed to load: ${e.message}` : "Offline and the engine isn't cached yet — open once while online", "error");
  });
