# Measure browser startup

The browser build runs the real FastAPI app in a Pyodide worker. The worker reads the
site's manifest and lockfile, then preloads their packages while Python starts.
The lockfile preserves the staged wheels' versions and SHA-256 hashes. Native packages
come from the installed Pyodide release on jsDelivr; pure Python wheels come from the site.

## Record the boot stages

1. Build and serve the static demo from the repository root:

   ```bash
   pnpm -C frontend build:browser && pnpm -C frontend exec vite preview --mode pyodide --host 127.0.0.1 --port 4281 --strictPort
   ```

2. Open `http://127.0.0.1:4281/`. Before starting the demo, paste this into the browser console:

   ```js
   const stages = [];
   let started = 0;
   document.querySelector("button").addEventListener("click", () => {
     started = performance.now();
   }, { once: true });
   const OriginalWorker = window.Worker;
   window.Worker = class extends OriginalWorker {
     constructor(...args) {
       super(...args);
       this.addEventListener("message", ({ data }) => {
         if (data.type !== "progress") return;
         stages.push({ stage: data.stage, seconds: (performance.now() - started) / 1000 });
         if (data.stage === "ready") console.table(stages);
       });
     }
   };
   ```

3. Start the demo. `wheel` follows package installation; `seed` begins household creation
   and app imports. `ready` means the worker can serve requests. The first rendered plan
   also needs those requests and its React chunks, so record that separately.
4. Reload and repeat the console setup for each warm run. Keep the browser context and
   cache. A fresh context measures the first visit instead. Check that network requests
   reach only the site and `cdn.jsdelivr.net`.

Compare builds in alternating order within one browser context. Discard the first pair
when reporting warm starts. Run the privacy and wheel-integrity tests after changing boot:

```bash
pnpm -C frontend exec playwright test --config=playwright.pyodide.config.ts --project=chromium boot-hosts.spec.ts
```

## Measurements on 14 November 2026

Chromium ran alternating baseline and preload builds in one context, with three warm
runs per build after the first pair. Both used the fictional example household and
Pyodide 314.0.7. The shared host had 12 vCPUs and a load average around 30 during the run.

| Warm interval                              | Sequential installation | Lockfile preload |
| ------------------------------------------ | ----------------------: | ---------------: |
| Start click to worker `ready`              |             6.87–19.9 s |      8.07–18.9 s |
| Start click to first plan provenance stamp |             8.38–22.5 s |      9.57–22.6 s |

These ranges overlap under heavy contention. They do not establish a speedup percentage.
The preload removes runtime dependency resolution and overlaps package downloads with
interpreter startup, but the **under-three-second warm-start target remains unmet**.
Python profiling identified source compilation and app imports as substantial remaining work.
Memory use was not measured reliably; the page's JavaScript heap counter excludes worker
and WebAssembly memory.

## Memory snapshots

An experiment loaded the same app with `_makeSnapshot: true`, then called
`makeMemorySnapshot()` after `boot.py`. Pyodide 314.0.7 raised:

```text
Unexpected hiwire entry at index 6
```

The internal JavaScript reference table expected an empty object at that entry. It held
the populated package registry, including FastAPI and its dependencies, instead.
`serializeHiwireState` checks these initial entries before calling a custom serializer,
so that serializer cannot repair this failure. `_makeSnapshot` and `_loadSnapshot` have
working code paths; their hidden documentation markers do not mean the runtime ignores them.

No snapshot is stored or restored by the application. A snapshot taken before packages
load would not retain the expensive app-import stage. That alternative has not been timed.
Repeat the snapshot experiment after a Pyodide change before relying on it.

[Startup issue #68](https://github.com/simonvanlierde/vuurtoren/issues/68) remains open.
The next measurement needs a quiet host and the same cold/warm procedure before choosing
another optimization or claiming the target is met.
