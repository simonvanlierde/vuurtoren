import { describe, expect, it } from "vitest";
import { detectLocale, MESSAGES } from "./i18n";

describe("detectLocale", () => {
  it("honours a stored choice over the browser", () => {
    expect(detectLocale("en", "nl-NL")).toBe("en");
    expect(detectLocale("nl", "en-US")).toBe("nl");
  });

  it("detects Dutch browsers, defaults everyone else to English", () => {
    expect(detectLocale(null, "nl-NL")).toBe("nl");
    expect(detectLocale(null, "nl")).toBe("nl");
    expect(detectLocale(null, "en-US")).toBe("en");
    expect(detectLocale(null, "de-DE")).toBe("en");
  });
});

describe("dictionaries", () => {
  it("nl and en carry exactly the same keys", () => {
    expect(Object.keys(MESSAGES.nl).sort()).toEqual(Object.keys(MESSAGES.en).sort());
  });
});
