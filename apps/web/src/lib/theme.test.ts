import { beforeEach, describe, expect, it } from "vitest";
import { getPreference, resolveTheme, setPreference, THEME_STORAGE_KEY } from "./theme";

describe("theme preferences", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("follows the system theme when no choice is stored", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("uses a saved choice instead of the system theme", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(getPreference()).toBe("light");
    expect(resolveTheme(getPreference(), true)).toBe("light");
  });

  it("falls back to the system setting for corrupted values", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(getPreference()).toBe("system");
  });

  it("persists and applies an explicit choice", () => {
    setPreference("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
