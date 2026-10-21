// Boots Pyodide, installs the browser-safe deps + the vuurtoren wheel, runs boot.py,
// then answers dispatch RPCs. Progress messages let the gate show meaningful states.
import { loadPyodide, type PyodideInterface } from "pyodide";
import pyodidePkg from "pyodide/package.json";
import bootPy from "./boot.py?raw";

let py: PyodideInterface | null = null;
let dispatch: ((m: string, p: string, q: string, b: string) => Promise<string>) | null = null;

const post = (msg: unknown) => (self as unknown as Worker).postMessage(msg);
const progress = (stage: string) => post({ type: "progress", stage });

async function init(base: string) {
  progress("runtime");
  // The runtime is the one thing fetched from elsewhere: jsDelivr. Vite bundles pyodide's
  // loader but not its wasm/stdlib assets, so the default same-origin indexURL 404s. The
  // version is read from the installed pyodide package so it can never drift. That is a
  // one-time code download; household data is never sent anywhere.
  py = await loadPyodide({
    indexURL: `https://cdn.jsdelivr.net/pyodide/v${pyodidePkg.version}/full/`,
  });
  await py.loadPackage("micropip");
  const micropip = py.pyimport("micropip");

  // `base` is the site's absolute base URL (origin + Vite base path), so the assets are
  // found whether the site is served at root or under a project subpath like /vuurtoren/.
  const manifest = await (await fetch(`${base}pyodide/manifest.json`)).json();

  progress("deps");
  // Two sources, never PyPI (scripts/build_browser_assets.mjs and wheels.json):
  // - `manifest.pyodide` (numpy, pyyaml, pydantic) come from this Pyodide release's own
  //   index on jsDelivr, because they need a compiled wasm wheel, and a version ahead of
  //   the release's has none (uv.lock's pydantic 2.14 needs a pydantic-core with no
  //   emscripten wheel). They install by bare name, at the release's version.
  // - `manifest.wheels` are uv.lock's pure-Python wheels, served from this site. URL
  //   wheels go first so micropip resolves their names to them, not to the release's
  //   older copies or to PyPI.
  await micropip.install([
    ...manifest.wheels.map((f: string) => `${base}pyodide/wheels/${f}`),
    ...manifest.pyodide,
  ]);

  progress("wheel");
  py.FS.mkdirTree("/assets");
  const toml = await (await fetch(`${base}pyodide/${manifest.household}`)).arrayBuffer();
  py.FS.writeFile("/assets/household.example.toml", new Uint8Array(toml));
  // deps=False so micropip installs the wheel WITHOUT resolving its declared deps: it
  // requires uvicorn[standard]+alembic (no wasm wheels, deferred imports). `deps` is a keyword-
  // only arg — the 2nd positional is keep_going — so it must go through callKwargs.
  await (
    micropip.install as unknown as {
      callKwargs: (r: string, kw: { deps: boolean }) => Promise<void>;
    }
  ).callKwargs(`${base}pyodide/${manifest.wheel}`, { deps: false });

  progress("seed");
  await py.runPythonAsync(bootPy);
  dispatch = py.globals.get("dispatch");

  progress("ready");
}

self.onmessage = async (e: MessageEvent) => {
  const msg = e.data;
  try {
    if (msg.type === "init") {
      await init(msg.base);
      return;
    }
    if (msg.type === "request") {
      if (!dispatch) throw new Error("worker not ready");
      const raw = await dispatch(msg.method, msg.path, msg.query ?? "", msg.body ?? "");
      const r = JSON.parse(raw);
      post({ type: "response", id: msg.id, status: r.status, headers: r.headers, body: r.body });
    }
  } catch (err) {
    console.error("[pyodide worker]", err);
    post({ type: "error", id: msg?.id, message: err instanceof Error ? err.message : String(err) });
  }
};
