export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = Exclude<ThemePreference, "system">;

export const THEME_STORAGE_KEY = "overcall-theme";
export const THEME_CHANGE_EVENT = "overcall-theme-change";

export function getPreference(): ThemePreference {
  try {
    const preference = window.localStorage.getItem(THEME_STORAGE_KEY);
    return preference === "light" || preference === "dark" ? preference : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false,
): ResolvedTheme {
  return preference === "system" ? (systemPrefersDark ? "dark" : "light") : preference;
}

export function applyTheme(preference: ThemePreference): ResolvedTheme {
  const theme = resolveTheme(preference);
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
  return theme;
}

export function setPreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // The visual preference still applies for this session when storage is unavailable.
  }
  applyTheme(preference);
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
}

export function subscribeToSystemTheme(onChange: () => void): () => void {
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (!media) return () => undefined;
  const handleChange = () => {
    if (getPreference() === "system") {
      applyTheme("system");
      onChange();
    }
  };
  media.addEventListener?.("change", handleChange);
  return () => media.removeEventListener?.("change", handleChange);
}
