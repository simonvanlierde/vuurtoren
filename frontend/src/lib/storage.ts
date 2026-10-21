/** localStorage, minus the throw. Storage is per-viewer convenience only (a theme, a
 * locale, a dismissed card), and it can be missing or refuse access: Safari private
 * mode, blocked site data, a sandboxed iframe. A read then answers null and a write is
 * dropped, so the app falls back to its defaults instead of failing to render. */
export function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Stores `value`, or removes the key when it is null. Never throws. */
export function writeStored(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Not persisted; the in-memory state still applies for this visit.
  }
}
