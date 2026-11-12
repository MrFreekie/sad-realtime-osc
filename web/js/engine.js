// Loads Pyodide (Python compiled to WebAssembly) and the repo's shared/
// Python files, so the browser runs exactly the same array_math.py as the
// desktop app. There is deliberately no JavaScript copy of the math.
//
// Usage:
//   const engine = await initEngine({ onStatus: msg => ... });
//   const subs = engine.call("end_fire", [6, 1.2, 343]);

export const PYODIDE_VERSION = "0.27.2";
export const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

// Repo root, resolved from this file (web/js/engine.js). The deployed site
// keeps the same folder layout, so these relative paths work locally and
// on GitHub Pages.
const ROOT = new URL("../../", import.meta.url);

export const SHARED_FILES = [
  "shared/array_math.py",
  "shared/jsonable.py",
  "shared/version.py",
  "shared/sub_profiles.py",
  "shared/sub_profiles.csv",
  "shared/prealign_profiles.py",
  "shared/prealign_delays.csv",
  "web/py/bridge.py",
];

const FS_ROOT = "/sadrt";

// JSON from Python encodes NaN / ±inf as {"_float": "..."}; turn them back.
function revive(_key, value) {
  if (value && typeof value === "object" && typeof value._float === "string") {
    return { nan: NaN, inf: Infinity, "-inf": -Infinity }[value._float];
  }
  return value;
}

async function fetchText(path) {
  const res = await fetch(new URL(path, ROOT));
  if (!res.ok) throw new Error(`Couldn't load ${path} (HTTP ${res.status})`);
  return res.text();
}

/**
 * @param {object} opts
 * @param {(msg: string) => void} [opts.onStatus]
 * @param {string[]} [opts.extraFiles]  more repo-relative files to mount (e.g. tests)
 */
export async function initEngine({ onStatus = () => {}, extraFiles = [] } = {}) {
  const t0 = performance.now();
  onStatus("Loading Python runtime…");
  const { loadPyodide } = await import(`${PYODIDE_BASE}pyodide.mjs`);
  const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });

  onStatus("Loading array math…");
  const files = [...SHARED_FILES, ...extraFiles];
  const texts = await Promise.all(files.map(fetchText));
  const dirs = new Set();
  files.forEach((path, i) => {
    const dir = `${FS_ROOT}/${path.split("/").slice(0, -1).join("/")}`;
    if (!dirs.has(dir)) {
      pyodide.FS.mkdirTree(dir);
      dirs.add(dir);
    }
    pyodide.FS.writeFile(`${FS_ROOT}/${path}`, texts[i]);
  });
  const pyDirs = [...dirs].map((d) => JSON.stringify(d)).join(", ");
  pyodide.runPython(`import sys\nfor d in (${pyDirs},):\n    sys.path.insert(0, d) if d not in sys.path else None`);

  const bridge = pyodide.pyimport("bridge");

  function unwrap(json) {
    const out = JSON.parse(json, revive);
    if ("error" in out) {
      const e = new Error(out.error);
      e.pyType = out.type;
      throw e;
    }
    return out.ok;
  }

  const info = unwrap(bridge.info());
  const engine = {
    pyodide,
    info,
    version: info.version,
    loadMs: performance.now() - t0,
    /** Call a public array_math function. Throws Error (with .pyType) on bad input. */
    call(fn, args = [], kwargs = {}) {
      return unwrap(bridge.call(fn, JSON.stringify(args), JSON.stringify(kwargs)));
    },
    subProfiles: () => unwrap(bridge.sub_profile_list()),
    prealignData: () => unwrap(bridge.prealign_data()),
  };
  onStatus("Ready");
  return engine;
}
