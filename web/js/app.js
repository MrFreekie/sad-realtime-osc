import { initEngine } from "./engine.js";

const $ = (id) => document.getElementById(id);
const status = $("status");

function setStatus(text, state = "loading") {
  status.textContent = text;
  status.dataset.state = state;
}

// --- Tabs ---------------------------------------------------------------
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  }
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!step) return;
    const next = tabs[(i + step + tabs.length) % tabs.length];
    selectTab(next);
    next.focus();
  });
});
selectTab(tabs[0]);

// --- Service worker (offline support) -----------------------------------
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((e) => console.warn("Service worker not registered:", e));
}

// --- Engine + End-Fire preview -------------------------------------------
const inputs = { count: $("count"), spacing: $("spacing"), temp: $("temp") };
const fmt = (x, d) => (Number.isFinite(x) ? x.toFixed(d) : "—");

function render(engine) {
  const n = Number(inputs.count.value);
  const spacing = Number(inputs.spacing.value);
  const temp = Number(inputs.temp.value);
  $("count-out").textContent = String(n);
  $("spacing-out").textContent = `${spacing.toFixed(2)} m`;
  $("temp-out").textContent = `${temp.toFixed(1)} °C`;

  const t0 = performance.now();
  try {
    const c = engine.call("speed_of_sound", [temp, 50, 0]);
    const subs = engine.call("end_fire", [n, spacing, c]);
    const ms = performance.now() - t0;
    $("results").replaceChildren(...subs.map((s) => {
      const tr = document.createElement("tr");
      const pol = s.polarity_reversed ? "Reversed" : "Normal";
      tr.innerHTML = `<td>${s.index}</td><td>${fmt(s.delay_ms, 3)}</td><td>${fmt(s.gain_db, 1)}</td>` +
        `<td class="${s.polarity_reversed ? "pol-rev" : ""}">${pol}</td>`;
      return tr;
    }));
    $("demo-meta").textContent = `Speed of sound ${c.toFixed(2)} m/s (50 % RH, sea level). Computed in ${ms.toFixed(1)} ms.`;
  } catch (e) {
    $("demo-meta").textContent = `Error: ${e.message}`;
  }
}

initEngine({ onStatus: (m) => setStatus(m) })
  .then((engine) => {
    $("version").textContent = `v${engine.version}`;
    setStatus(`Ready · Python ${engine.info.python} · loaded in ${(engine.loadMs / 1000).toFixed(1)} s`, "ready");
    $("demo-controls").disabled = false;
    Object.values(inputs).forEach((el) => el.addEventListener("input", () => render(engine)));
    render(engine);
  })
  .catch((e) => {
    console.error(e);
    setStatus(navigator.onLine ? `Engine failed to load: ${e.message}` : "Offline and the engine isn't cached yet — open once while online", "error");
  });
