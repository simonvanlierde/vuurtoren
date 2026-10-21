// Build the vuurtoren wheel and stage the browser build's runtime assets: that wheel, the
// example household, and the pure-Python wheels the worker installs that this Pyodide
// release does not bundle, so the boot fetches nothing but the runtime from jsDelivr.
//   node scripts/build_browser_assets.mjs
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(REPO, "frontend/public/pyodide");
const WHEEL_CACHE = join(REPO, "dist/pyodide-wheels");

execFileSync("uv", ["build", "--wheel", "--out-dir", join(REPO, "dist")], {
  cwd: REPO,
  stdio: "inherit",
});
// Numeric compare: a plain string sort puts 0.9.0 after 0.10.0.
const wheel = readdirSync(join(REPO, "dist"))
  .filter((f) => f.endsWith(".whl"))
  .sort((a, b) => a.localeCompare(b, "en", { numeric: true }))
  .at(-1);
if (!wheel) throw new Error("uv build produced no wheel");

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
copyFileSync(join(REPO, "dist", wheel), join(OUT, wheel));
copyFileSync(join(REPO, "household.example.toml"), join(OUT, "household.example.toml"));

// Each pin in wheels.json must be the version uv.lock resolves (a vitest checks it too);
// the wheel's URL and sha256 come from uv.lock, so what ships is what the backend tests.
const pins = JSON.parse(readFileSync(join(REPO, "frontend/src/pyodide/wheels.json"), "utf8"));
const uvLock = readFileSync(join(REPO, "uv.lock"), "utf8");
mkdirSync(join(OUT, "wheels"), { recursive: true });
mkdirSync(WHEEL_CACHE, { recursive: true });
const wheels = [];
for (const [name, version] of Object.entries(pins.pypi)) {
  const block = uvLock.split("\n[[package]]\n").find((b) => b.startsWith(`name = "${name}"\n`));
  const locked = block && /^version = "([^"]+)"/m.exec(block)?.[1];
  if (locked !== version) {
    throw new Error(`wheels.json pins ${name} ${version} but uv.lock has ${locked}`);
  }
  const m = /url = "([^"]+-py3-none-any\.whl)", hash = "sha256:([0-9a-f]+)"/.exec(block);
  if (!m) throw new Error(`uv.lock has no pure-Python wheel for ${name} ${version}`);
  const [, url, sha256] = m;
  const file = url.split("/").at(-1);
  const cached = join(WHEEL_CACHE, file);
  const digest = (buf) => createHash("sha256").update(buf).digest("hex");
  if (!existsSync(cached) || digest(readFileSync(cached)) !== sha256) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (digest(buf) !== sha256) throw new Error(`${file}: sha256 does not match uv.lock`);
    writeFileSync(cached, buf);
  }
  copyFileSync(cached, join(OUT, "wheels", file));
  wheels.push(file);
}

writeFileSync(
  join(OUT, "manifest.json"),
  JSON.stringify(
    { wheel, household: "household.example.toml", pyodide: pins.pyodide, wheels },
    null,
    2,
  ),
);
console.log(
  `staged ${wheel}, ${wheels.length} dependency wheels, household.example.toml and manifest.json in frontend/public/pyodide/`,
);
