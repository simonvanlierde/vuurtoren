// One import point for the build flag so the server build tree-shakes Pyodide code out.
export const PYODIDE = import.meta.env.VITE_PYODIDE === "1";
