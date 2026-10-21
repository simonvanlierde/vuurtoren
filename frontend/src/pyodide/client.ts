// Main-thread side of the Pyodide worker: id-correlated RPC, no comlink dependency.
//
// The worker runs Python on one thread, so requests are queued here and posted one at a
// time. A queued request whose signal aborts (React Query superseding a projection) is
// dropped before it reaches the worker. The one in flight cannot be interrupted: an abort
// only rejects its promise, and its late result is ignored.
type Pending = { resolve: (r: Response) => void; reject: (e: Error) => void };
type Queued = Pending & { id: number; message: Record<string, unknown> };

let worker: Worker | null = null;
let makeWorker = () => new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
const pending = new Map<number, Pending>();
const queue: Queued[] = [];
let inFlight: number | null = null;
let progressCb: (stage: string) => void = () => {};
let readyResolve: (() => void) | null = null;
let seq = 0;

/** Test seam — inject a fake worker. */
export function __setWorkerFactory(f: () => Worker) {
  makeWorker = f;
}

function ensureWorker(): Worker {
  if (worker) return worker;
  worker = makeWorker();
  worker.addEventListener("message", (e: MessageEvent) => {
    const m = e.data;
    if (m.type === "progress") {
      progressCb(m.stage);
      if (m.stage === "ready") readyResolve?.();
    } else if (m.type === "response") {
      // A 204/304 must be built with a null body: Response throws on any other, even "".
      const body = m.status === 204 || m.status === 304 ? null : m.body;
      pending.get(m.id)?.resolve(new Response(body, { status: m.status, headers: m.headers }));
      settle(m.id);
    } else if (m.type === "error") {
      if (m.id != null) {
        pending.get(m.id)?.reject(new Error(m.message));
        settle(m.id);
      } else {
        progressCb("error");
      }
    }
  });
  return worker;
}

export function bootWorker(onProgress: (stage: string) => void): Promise<void> {
  progressCb = onProgress;
  const w = ensureWorker();
  return new Promise((resolve, reject) => {
    readyResolve = resolve;
    w.addEventListener("message", (e: MessageEvent) => {
      if (e.data?.type === "error" && e.data.id == null) reject(new Error(e.data.message));
    });
    // Absolute site base (origin + Vite's base path) so the worker's asset fetches work
    // at root or under a project subpath (GitHub Pages serves under /<repo>/).
    const base = new URL(import.meta.env.BASE_URL, location.href).href;
    w.postMessage({ type: "init", base });
  });
}

const abortError = () => new DOMException("The request was aborted", "AbortError");

function settle(id: number) {
  pending.delete(id);
  if (inFlight === id) {
    inFlight = null;
    pump();
  }
}

function pump() {
  if (inFlight !== null) return;
  const next = queue.shift();
  if (!next) return;
  inFlight = next.id;
  pending.set(next.id, next);
  ensureWorker().postMessage(next.message);
}

export function pyodideFetch(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  ensureWorker();
  const id = ++seq;
  return new Promise<Response>((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const item: Queued = {
      id,
      resolve,
      reject,
      message: {
        type: "request",
        id,
        method,
        // ASGI takes the query string apart from the path; left in, a route never matches it.
        path: `/api/${path.split("?")[0]}`,
        query: path.includes("?") ? path.slice(path.indexOf("?") + 1) : "",
        body: body === undefined ? "" : JSON.stringify(body),
      },
    };
    signal?.addEventListener(
      "abort",
      () => {
        const at = queue.indexOf(item);
        if (at !== -1) queue.splice(at, 1);
        reject(abortError());
      },
      { once: true },
    );
    queue.push(item);
    pump();
  });
}
