import { describe, expect, it } from "vitest";
import { safeRedirect } from "./safeRedirect";

describe("safeRedirect", () => {
  it("allows local absolute paths with their query and hash", () => {
    expect(safeRedirect("/issues?severity=warning#top")).toBe("/issues?severity=warning#top");
  });

  it.each(["//evil.example", "https://evil.example", "/\\evil.example", "javascript:alert(1)", ""])(
    "rejects unsafe redirect %s",
    (value) => {
      expect(safeRedirect(value)).toBe("/app");
    },
  );

  it("uses a safe fallback", () => {
    expect(safeRedirect("//evil.example", "/settings")).toBe("/settings");
  });
});
