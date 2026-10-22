import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { getPreference, setPreference, subscribeToSystemTheme, THEME_CHANGE_EVENT, type ThemePreference } from "../lib/theme";

const options: Array<{ value: ThemePreference; label: string; Icon: typeof Monitor }> = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

export function ThemeToggle() {
  const [preference, setCurrentPreference] = useState<ThemePreference>(getPreference);

  useEffect(() => {
    const syncPreference = () => setCurrentPreference(getPreference());
    window.addEventListener(THEME_CHANGE_EVENT, syncPreference);
    const unsubscribeFromSystem = subscribeToSystemTheme(syncPreference);
    return () => {
      window.removeEventListener(THEME_CHANGE_EVENT, syncPreference);
      unsubscribeFromSystem();
    };
  }, []);

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      {options.map(({ value, label, Icon }) => (
        <button
          aria-label={`Use ${label.toLowerCase()} theme`}
          aria-pressed={preference === value}
          className="theme-toggle__option"
          key={value}
          onClick={() => {
            setPreference(value);
            setCurrentPreference(value);
          }}
          title={label}
          type="button"
        >
          <Icon aria-hidden="true" size={15} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
