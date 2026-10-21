import { describe, expect, it } from "vitest";
import { decodeShareState, encodeShareState, type ShareState } from "./urlHash";

describe("share-state hash round-trip", () => {
  it("round-trips a full state through encode then decode", () => {
    const state: ShareState = {
      inflation: 0.03,
      swr: 0.035,
      houseAppreciation: 0.02,
      realTerms: true,
      minEndNetWorth: "100000",
    };
    expect(decodeShareState(`#${encodeShareState(state)}`)).toEqual(state);
  });

  it("omits unset knobs rather than encoding defaults", () => {
    expect(encodeShareState({ swr: 0.04 })).toBe("swr=0.04");
  });

  it("drops a malformed number in a hand-edited link", () => {
    expect(decodeShareState("#inflation=notanumber&swr=0.04")).toEqual({ swr: 0.04 });
  });

  it("treats real=1 as the only truthy form and ignores anything else", () => {
    expect(decodeShareState("#real=0").realTerms).toBeUndefined();
    expect(decodeShareState("#real=1").realTerms).toBe(true);
  });
});
