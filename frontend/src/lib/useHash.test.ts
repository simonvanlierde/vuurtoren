import { describe, expect, it } from "vitest";
import { hashForLens, lensFromHash, viewFromHash } from "./useHash";

describe("viewFromHash", () => {
  it("defaults to today", () => {
    expect(viewFromHash("")).toBe("today");
    expect(viewFromHash("#")).toBe("today");
  });

  it("passes the four surfaces through", () => {
    for (const v of ["today", "plan", "flows", "settings"]) {
      expect(viewFromHash(`#${v}`)).toBe(v);
    }
  });

  it("redirects every legacy hash to its new surface", () => {
    expect(viewFromHash("#accounts")).toBe("today");
    expect(viewFromHash("#timeline")).toBe("plan");
    expect(viewFromHash("#projection")).toBe("plan");
    expect(viewFromHash("#monte-carlo")).toBe("plan");
    expect(viewFromHash("#scenarios")).toBe("plan");
    expect(viewFromHash("#cash-flow")).toBe("flows");
  });
});

describe("lensFromHash", () => {
  it("defaults to opbouw", () => {
    expect(lensFromHash("")).toBe("opbouw");
    expect(lensFromHash("#plan")).toBe("opbouw");
    expect(lensFromHash("#plan/nonsense")).toBe("opbouw");
  });

  it("reads the lens segment", () => {
    expect(lensFromHash("#plan/onzekerheid")).toBe("onzekerheid");
    expect(lensFromHash("#plan/scenarios")).toBe("scenarios");
  });

  it("maps legacy deep hashes onto their replacing lens", () => {
    expect(lensFromHash("#monte-carlo")).toBe("onzekerheid");
    expect(lensFromHash("#scenarios")).toBe("scenarios");
    expect(lensFromHash("#timeline")).toBe("opbouw");
    expect(lensFromHash("#projection")).toBe("opbouw");
  });
});

describe("viewFromHash with lens segments", () => {
  it("routes plan/<lens> to plan", () => {
    expect(viewFromHash("#plan/onzekerheid")).toBe("plan");
    expect(viewFromHash("#plan/scenarios")).toBe("plan");
  });
});

describe("hashForLens", () => {
  it("round-trips", () => {
    expect(hashForLens("opbouw")).toBe("plan");
    expect(lensFromHash(`#${hashForLens("onzekerheid")}`)).toBe("onzekerheid");
    expect(lensFromHash(`#${hashForLens("scenarios")}`)).toBe("scenarios");
  });
});
