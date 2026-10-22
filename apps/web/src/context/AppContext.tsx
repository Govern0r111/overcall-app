import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { useSettings } from "../hooks/queries";
import type { Currency, Settings } from "../lib/api";
import { formatMoney } from "../lib/format";
import { applyTheme, getPreference, resolveTheme, setPreference, subscribeToSystemTheme, THEME_CHANGE_EVENT } from "../lib/theme";

type Theme = "light" | "dark";

interface AppCtx {
  theme: Theme;
  setTheme: (t: Theme) => void;
  settings?: Settings;
  currency: Currency;
  money: (usd: number, short?: boolean) => string;
}

const Ctx = createContext<AppCtx | null>(null);

const initialTheme = (): Theme => {
  return resolveTheme(getPreference());
};

export const AppProvider = ({ children }: { children: ReactNode }) => {
  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const { data: settings } = useSettings();
  const currency: Currency = settings?.currency ?? "INR";
  const rate = settings?.usd_inr_rate ?? 83.5;

  useEffect(() => {
    const syncTheme = () => setThemeState(applyTheme(getPreference()));
    syncTheme();
    window.addEventListener(THEME_CHANGE_EVENT, syncTheme);
    const unsubscribeFromSystem = subscribeToSystemTheme(syncTheme);
    return () => {
      window.removeEventListener(THEME_CHANGE_EVENT, syncTheme);
      unsubscribeFromSystem();
    };
  }, []);

  const setTheme = useCallback((nextTheme: Theme) => setPreference(nextTheme), []);

  const money = useCallback((usd: number, short = false) => formatMoney(usd, currency, rate, short), [currency, rate]);

  return <Ctx.Provider value={{ theme, setTheme, settings, currency, money }}>{children}</Ctx.Provider>;
};

export const useApp = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
};
