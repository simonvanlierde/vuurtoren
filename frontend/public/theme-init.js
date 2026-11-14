// Mirrors src/lib/theme.ts — key "vuurtoren-theme", class "dark" on <html>.
// Storage can refuse access (private mode, blocked site data): fall back to the system.
let t = null;
try {
  t = localStorage.getItem("vuurtoren-theme");
} catch {}
const dark = t === "dark" || (t !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
document.documentElement.classList.toggle("dark", dark);
