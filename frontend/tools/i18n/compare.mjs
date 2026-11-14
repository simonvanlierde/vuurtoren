// Frozen pre-migration templates include the Check my tax messages.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { setupI18n } from "@lingui/core";
import { messages as en } from "../../src/locales/en.mjs";
import { messages as nl } from "../../src/locales/nl.mjs";

const baseline = JSON.parse(readFileSync(new URL("./baseline.json", import.meta.url), "utf8"));
let count = 0;
for (const [locale, messages] of Object.entries({ en, nl })) {
  assert.deepEqual(
    Object.keys(messages).sort(),
    Object.keys(baseline[locale]).sort(),
    `${locale}: message IDs`,
  );
  const i18n = setupI18n({ locale, messages: { [locale]: messages } });
  for (const [id, expected] of Object.entries(baseline[locale])) {
    assert.equal(i18n._(id), expected, `${locale}: ${id}`);
    count++;
  }
}
console.log(
  `PASS: ${count} exact templates across both locales, including literal interpolation placeholders.`,
);
