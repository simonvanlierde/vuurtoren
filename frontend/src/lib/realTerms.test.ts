import { expect, test } from "vitest";
import { toReal } from "./realTerms";

test("deflates each point by its cumulative price level", () => {
  // 2% over the first year: €102 nominal at factor 1.02 is €100 real.
  expect(toReal([100, 102], [1, 1.02])).toEqual([100, 100]);
});

test("leaves the series unchanged when the factor is flat 1.0", () => {
  expect(toReal([100, 200, 300], [1, 1, 1])).toEqual([100, 200, 300]);
});

test("a zero or missing factor entry stays nominal rather than dividing by zero", () => {
  expect(toReal([100, 100], [0, undefined as unknown as number])).toEqual([100, 100]);
});
