import { describe, expect, it } from "vitest";
import { asText, statusClass } from "./api";

describe("dashboard display semantics", () => {
  it("does not turn missing values into zero", () => {
    expect(asText(undefined)).toBe("UNKNOWN");
    expect(asText(0)).toBe("UNKNOWN");
  });

  it("keeps blocked distinct from technical success", () => {
    expect(statusClass("BLOCKED")).toBe("status status-blocked");
    expect(statusClass("SUCCEEDED")).toBe("status status-succeeded");
  });
});
