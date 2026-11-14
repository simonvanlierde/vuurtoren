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
  // Absolute site base also supports project subpaths such as /vuurtoren/.
  const manifest = await (await fetch(`${base}pyodide/manifest.json`)).json();
  py = await loadPyodide({
    indexURL: `https://cdn.jsdelivr.net/pyodide/v${pyodidePkg.version}/full/`,
    lockFileURL: `${base}pyodide/pyodide-lock.json`,
    // The build records the complete dependency closure and wheel hashes, so the
    // loader can download and install packages while the interpreter starts.
    packages: [...manifest.packages, ...manifest.pyodide],
  });

  progress("wheel");
  py.FS.mkdirTree("/assets");
  const toml = await (await fetch(`${base}pyodide/${manifest.household}`)).arrayBuffer();
  py.FS.writeFile("/assets/household.example.toml", new Uint8Array(toml));

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
