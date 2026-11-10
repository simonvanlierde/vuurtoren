import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { apiErrorText, parseApiError } from "./fieldErrors";

describe("parseApiError", () => {
  it("maps a FastAPI 422 detail list onto fields by path and last segment", () => {
    const err = new ApiError(
      422,
      [
        { loc: ["body", "name"], msg: "Field required", type: "missing" },
        { loc: ["body", "params", "lump_sum_in", "amount"], msg: "Invalid decimal", type: "x" },
      ],
      "POST /api/accounts failed: 422",
    );
    const parsed = parseApiError(err);
    expect(parsed.fields.name).toBe("Field required");
    expect(parsed.fields.amount).toBe("Invalid decimal");
    expect(parsed.fields["params.lump_sum_in.amount"]).toBe("Invalid decimal");
    expect(parsed.general).toBeNull();
  });

  it("keeps list-item errors distinct via numeric path segments", () => {
    const err = new ApiError(
      422,
      [
        { loc: ["body", "items", 0, "amount"], msg: "first item broken", type: "x" },
        { loc: ["body", "items", 1, "amount"], msg: "second item broken", type: "x" },
      ],
      "POST /api/things failed: 422",
    );
    const parsed = parseApiError(err);
    expect(parsed.fields["items.0.amount"]).toBe("first item broken");
    expect(parsed.fields["items.1.amount"]).toBe("second item broken");
    // the named-segment convenience key keeps the first message on collision
    expect(parsed.fields.amount).toBe("first item broken");
  });

  it("routes a string detail (400/409) to general", () => {
    const err = new ApiError(400, "pass exactly one of `price` or `value`", "POST failed: 400");
    expect(parseApiError(err)).toEqual({
      fields: {},
      general: "pass exactly one of `price` or `value`",
    });
  });

  it("falls back to the error message for non-ApiError values", () => {
    expect(parseApiError(new Error("network down")).general).toBe("network down");
  });

  it("treats an empty 422 detail list as a general error, not silence", () => {
    const err = new ApiError(422, [], "POST /api/accounts failed: 422");
    expect(parseApiError(err)).toEqual({ fields: {}, general: "POST /api/accounts failed: 422" });
  });
});

describe("apiErrorText", () => {
  it("reads a body-level 422 list as its messages, never [object Object]", () => {
    // A validator on the whole body (an import's account check) has loc ["body"], so no
    // field claims it.
    const err = new ApiError(
      422,
      [
        { loc: ["body"], msg: "Value error, PENSION account 'Pot' needs an owner", type: "x" },
        { loc: ["body", "name"], msg: "Field required", type: "missing" },
      ],
      "POST /api/import failed: 422",
    );
    expect(apiErrorText(err)).toBe(
      "Value error, PENSION account 'Pot' needs an owner; Field required",
    );
  });

  it("reads a string detail as itself, and falls back to the status text", () => {
    expect(apiErrorText(new ApiError(400, "no owner", "POST /api/solve failed: 400"))).toBe(
      "no owner",
    );
    expect(apiErrorText(new ApiError(500, null, "POST /api/solve failed: 500"))).toBe(
      "POST /api/solve failed: 500",
    );
    expect(apiErrorText(new ApiError(422, [], "POST /api/solve failed: 422"))).toBe(
      "POST /api/solve failed: 422",
    );
    expect(apiErrorText(new Error("network down"))).toBe("network down");
  });
});
