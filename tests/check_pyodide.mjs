// Runs the parity cases inside Pyodide under Node -- the same Python build
// the web app uses -- so CI checks the browser math without a browser.
// It loads exactly the files web/js/engine.js mounts, then also imports the
// web model to catch anything that won't run under Pyodide (non-stdlib
// imports, 3.12-only syntax problems, etc.).
//
// Needs the npm "pyodide" package at the version pinned in engine.js:
//   npm install --prefix <dir> pyodide@<version>
//   node tests/check_pyodide.mjs <dir>
// (Run from anywhere; paths are resolved from this file.)

import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { PYODIDE_VERSION, SHARED_FILES } from "../web/js/engine.js";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const FS_ROOT = "/sadrt";
const EXTRA_FILES = ["tests/parity_common.py", "tests/parity_cases.json"];

const prefix = process.argv[2];
if (!prefix) {
  console.error("usage: node tests/check_pyodide.mjs <npm prefix holding node_modules/pyodide>");
  process.exit(2);
}
const pkgDir = join(prefix, "node_modules", "pyodide");
const pkg = JSON.parse(await readFile(join(pkgDir, "package.json"), "utf-8"));
if (pkg.version !== PYODIDE_VERSION) {
  console.error(`pyodide ${pkg.version} installed, but engine.js pins ${PYODIDE_VERSION}`);
  process.exit(1);
}

const { loadPyodide } = await import(pathToFileURL(join(pkgDir, "pyodide.mjs")).href);
const pyodide = await loadPyodide({ indexURL: pkgDir + "/" });

const dirs = new Set();
for (const path of [...SHARED_FILES, ...EXTRA_FILES]) {
  const text = await readFile(join(ROOT, path), "utf-8");
  const full = `${FS_ROOT}/${path}`;
  const dir = full.slice(0, full.lastIndexOf("/"));
  pyodide.FS.mkdirTree(dir);
  pyodide.FS.writeFile(full, text, { encoding: "utf8" });
  if (path.endsWith(".py")) dirs.add(dir);
}
pyodide.globals.set("_dirs", [...dirs]);

const result = JSON.parse(pyodide.runPython(`
import sys, json
for d in _dirs:
    if d not in sys.path:
        sys.path.insert(0, d)
import array_math, parity_common, bridge, model
with open("${FS_ROOT}/tests/parity_cases.json", encoding="utf-8") as f:
    _cases = json.load(f)["cases"]
_init = json.loads(model.init())
json.dumps({
    "python": sys.version.split()[0],
    "total": len(_cases),
    "failures": parity_common.run_cases(array_math, _cases),
    "model_ok": isinstance(_init, dict),
})
`));

for (const [id, diffs] of result.failures) {
  console.log(`FAIL ${id}`);
  for (const d of diffs.slice(0, 5)) console.log(`    ${d}`);
}
const passed = result.total - result.failures.length;
console.log(`Pyodide ${PYODIDE_VERSION} (Python ${result.python}): ` +
            `${passed}/${result.total} parity cases passed; web model ${result.model_ok ? "loads" : "FAILED to load"}`);
process.exit(result.failures.length === 0 && result.model_ok ? 0 : 1);
