import { afterEach, expect, it, vi } from "vitest";

const { loadPyodide, py } = vi.hoisted(() => {
  const py = {
    FS: { mkdirTree: vi.fn(), writeFile: vi.fn() },
    runPythonAsync: vi.fn(),
    globals: { get: vi.fn() },
  };
  return { py, loadPyodide: vi.fn().mockResolvedValue(py) };
});
vi.mock("pyodide", () => ({ loadPyodide }));

afterEach(() => vi.unstubAllGlobals());

it("preloads every staged wheel and bundled dependency while the runtime boots", async () => {
  const postMessage = vi.fn();
  const worker = { postMessage, onmessage: null as ((e: MessageEvent) => Promise<void>) | null };
  vi.stubGlobal("self", worker);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce({
        json: async () => ({
          household: "household.example.toml",
          packages: ["anyio", "vuurtoren"],
          pyodide: ["numpy", "idna"],
        }),
      })
      .mockResolvedValueOnce({ arrayBuffer: async () => new ArrayBuffer(0) }),
  );
  await import("./worker");
  await worker.onmessage?.({
    data: { type: "init", base: "https://example.com/demo/" },
  } as MessageEvent);
  expect(loadPyodide).toHaveBeenCalledWith(
    expect.objectContaining({
      lockFileURL: "https://example.com/demo/pyodide/pyodide-lock.json",
      packages: ["anyio", "vuurtoren", "numpy", "idna"],
    }),
  );
  expect(py.runPythonAsync).toHaveBeenCalledOnce();
  expect(postMessage).toHaveBeenLastCalledWith({ type: "progress", stage: "ready" });
});
