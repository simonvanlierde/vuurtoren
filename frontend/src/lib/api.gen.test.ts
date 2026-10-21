/** `api.gen.ts` is what `pnpm run gen:api` makes of the committed `openapi.json`. The
 * pytest `test_openapi.py` checks that the schema itself matches the app. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { generate } from "@vuurtoren/gen-api";
import { expect, it } from "vitest";

it("api.gen.ts is current with openapi.json", async () => {
  const schema = fileURLToPath(new URL("./openapi.json", import.meta.url));
  const committed = readFileSync(new URL("./api.gen.ts", import.meta.url), "utf8");
  expect(committed, "stale: run `pnpm run gen:api`").toBe(await generate(schema));
});
