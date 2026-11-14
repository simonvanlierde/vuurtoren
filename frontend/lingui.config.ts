import { defineConfig } from "@lingui/cli";
import { formatter } from "@lingui/format-po";

export default defineConfig({
  locales: ["en", "nl"],
  sourceLocale: "en",
  catalogs: [{ path: "src/locales/{locale}", include: ["src"] }],
  format: formatter({ origins: false, explicitIdAsDefault: true }),
  compileNamespace: "es",
});
