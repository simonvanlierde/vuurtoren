import { expect, test, vi } from "vitest";
import { __setWorkerFactory, pyodideFetch } from "./client";

// One fake worker for the whole file: the client keeps its worker for the module's life.
const listeners: ((e: MessageEvent) => void)[] = [];
const posted: { type: string; id: number; path: string; query: string }[] = [];
const fake = {
  postMessage(msg: { type: string; id: number; path: string; query: string }) {
    posted.push(msg);
  },
  addEventListener: (_t: string, l: (e: MessageEvent) => void) => listeners.push(l),
  terminate: vi.fn(),
};
__setWorkerFactory(() => fake as unknown as Worker);

function respond(id: number, body: string, status = 200) {
  for (const l of listeners)
    l({
      data: {
        type: "response",
        id,
        status,
        headers: [["content-type", "application/json"]],
        body,
      },
    } as MessageEvent);
}

test("pyodideFetch resolves a Response from a worker response message", async () => {
  const req = pyodideFetch("GET", "households");
  const sent = posted.at(-1);
  if (!sent) throw new Error("nothing posted");
  respond(sent.id, '{"ok":true}');
  const res = await req;
  expect(res.status).toBe(200);
  expect(await res.json()).toEqual({ ok: true });
});

test("sends the query string apart from the path, as ASGI expects", () => {
  posted.length = 0;
  void pyodideFetch("GET", "tax-config?year=2026&country=NL");
  expect(posted[0]).toMatchObject({ path: "/api/tax-config", query: "year=2026&country=NL" });
  respond(posted[0].id, "{}");
});

test("posts one request at a time and drops queued ones whose signal aborted", async () => {
  posted.length = 0;
  const first = new AbortController();
  const second = new AbortController();
  const a = pyodideFetch("POST", "project", {}, first.signal);
  const b = pyodideFetch("POST", "project", {}, second.signal);
  const c = pyodideFetch("POST", "project");
  // Only the first reaches the single-threaded worker; the rest wait on the main thread.
  expect(posted).toHaveLength(1);
  const [inFlight] = posted;

  first.abort(); // in flight: cannot be interrupted, only stops waiting
  second.abort(); // queued: never posted at all
  await expect(a).rejects.toMatchObject({ name: "AbortError" });
  await expect(b).rejects.toMatchObject({ name: "AbortError" });
  expect(posted).toHaveLength(1);

  // The abandoned result arrives, is ignored, and frees the worker for the next request.
  respond(inFlight.id, '{"stale":true}');
  expect(posted).toHaveLength(2);
  respond(posted[1].id, '{"fresh":true}');
  expect(await (await c).json()).toEqual({ fresh: true });
});

test("rejects at once when the signal has already aborted", async () => {
  posted.length = 0;
  const done = new AbortController();
  done.abort();
  await expect(pyodideFetch("GET", "meta", undefined, done.signal)).rejects.toMatchObject({
    name: "AbortError",
  });
  expect(posted).toHaveLength(0);
});

test("resolves a 204 with no body, as every DELETE returns", async () => {
  posted.length = 0;
  const req = pyodideFetch("DELETE", "households/1/all");
  respond(posted[0].id, "", 204);
  const res = await req;
  expect(res.status).toBe(204);
  expect(res.ok).toBe(true);
});
