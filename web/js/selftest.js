import { initEngine } from "./engine.js";

const $ = (id) => document.getElementById(id);

function setStatus(text, state = "loading") {
  $("status").textContent = text;
  $("status").dataset.state = state;
}

try {
  const engine = await initEngine({
    onStatus: (m) => setStatus(m),
    extraFiles: ["tests/parity_common.py", "tests/parity_cases.json"],
  });
  setStatus("Running cases…");
  const t0 = performance.now();
  const result = JSON.parse(engine.pyodide.runPython(`
import json, array_math, parity_common
with open("/sadrt/tests/parity_cases.json", encoding="utf-8") as f:
    _cases = json.load(f)["cases"]
json.dumps({"total": len(_cases), "failures": parity_common.run_cases(array_math, _cases)})
`));
  const ms = performance.now() - t0;
  const passed = result.total - result.failures.length;
  const ok = result.failures.length === 0;

  $("summary").textContent = `${passed}/${result.total} parity cases passed`;
  $("summary").dataset.state = ok ? "pass" : "fail";
  $("meta").textContent =
    `App v${engine.version} · Python ${engine.info.python} (Pyodide) · ` +
    `engine loaded in ${(engine.loadMs / 1000).toFixed(1)} s · cases ran in ${ms.toFixed(0)} ms`;
  if (!ok) {
    $("failures").hidden = false;
    $("failures").textContent = result.failures
      .map(([id, diffs]) => `FAIL ${id}\n` + diffs.slice(0, 5).map((d) => `    ${d}`).join("\n"))
      .join("\n");
  }
  setStatus(ok ? "Pass" : "Fail", ok ? "ready" : "error");
  document.documentElement.dataset.selftest = ok ? "pass" : "fail"; // hook for automated checks
} catch (e) {
  console.error(e);
  $("summary").textContent = `Self-test couldn't run: ${e.message}`;
  $("summary").dataset.state = "fail";
  setStatus("Error", "error");
  document.documentElement.dataset.selftest = "error";
}
