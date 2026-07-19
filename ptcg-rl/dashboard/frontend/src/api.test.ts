import { describe, expect, it } from "vitest";
import { asArray, asNumber, asText, statusClass } from "./api";

describe("dashboard display semantics", () => {
  it("does not turn missing text into zero", () => {
    expect(asText(undefined)).toBe("UNKNOWN");
    expect(asText(0)).toBe("UNKNOWN");
    expect(asNumber(undefined)).toBe(0);
    expect(asNumber(1.5)).toBe(1.5);
  });

  it("keeps blocked distinct from technical success", () => {
    expect(statusClass("BLOCKED")).toBe("status status-blocked");
    expect(statusClass("SUCCEEDED")).toBe("status status-succeeded");
  });

  it("normalizes only real arrays", () => {
    expect(asArray(["R1", "G2"])).toEqual(["R1", "G2"]);
    expect(asArray("R1")).toEqual([]);
  });
});
