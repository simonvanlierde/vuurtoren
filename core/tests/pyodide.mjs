// Run the same generated Python comparisons against the actual Emscripten extension.
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import pyodidePkg from "../../frontend/node_modules/pyodide/package.json" with { type: "json" };
import { loadPyodide } from "../../frontend/node_modules/pyodide/pyodide.mjs";

async function wheel(directory) {
  const files = (await readdir(directory)).filter((f) => f.endsWith(".whl"));
  if (files.length !== 1)
    throw new Error(`expected one wheel in ${directory}, got ${files.length}`);
  return resolve(directory, files[0]);
}

const py = await loadPyodide({
  packageCacheDir: resolve("core/.cache/pyodide"),
  packageBaseUrl: `https://cdn.jsdelivr.net/pyodide/v${pyodidePkg.version}/full/`,
});
await py.loadPackage(["micropip", "numpy", "pydantic", "pyyaml", "pytest"]);
await py.loadPackage([await wheel("dist/app"), await wheel("dist/pyodide")]);
await py.runPythonAsync("import micropip; await micropip.install('hypothesis==6.170.9')");
py.FS.mkdir("/core_tests");
for (const file of (await readdir("core/tests")).filter(
  (f) => f.startsWith("test_") && f.endsWith(".py"),
)) {
  py.FS.writeFile(`/core_tests/${file}`, await readFile(`core/tests/${file}`));
}
const status = py.runPython(
  "import pytest; int(pytest.main(['/core_tests', '-q', '-p', 'no:cacheprovider']))",
);
if (status !== 0) throw new Error(`Pyodide differential suite exited ${status}`);
