import { useEffect, useState } from "react";
import { Switch } from "../ui/switch";
import { Input } from "../ui/input";
import { useApp } from "../../context/AppContext";
import { useSaveSettings } from "../../hooks/queries";
import { Currency } from "../../lib/api";
import { Segmented, SettingRow, SettingsSection } from "./SettingsSection";

export const AppearanceSection = () => {
  const { theme, setTheme, settings } = useApp();
  const save = useSaveSettings();
  const [rate, setRate] = useState(String(settings!.usd_inr_rate));
  useEffect(() => setRate(String(settings!.usd_inr_rate)), [settings]);

  const commitRate = () => {
    const v = Number(rate);
    if (v > 0 && v !== settings!.usd_inr_rate) save.mutate({ ...settings!, usd_inr_rate: v });
    else setRate(String(settings!.usd_inr_rate));
  };

  return (
    <SettingsSection testId="settings-appearance" title="Appearance" description="How the dashboard looks and which currency costs are shown in.">
      <SettingRow
        label="Dark mode"
        help="Saved in this browser."
        control={<Switch data-testid="theme-toggle-button" checked={theme === "dark"} onCheckedChange={(v: boolean) => setTheme(v ? "dark" : "light")} aria-label="Dark mode" />}
      />
      <SettingRow
        label="Currency"
        help="Pricing tables are in USD; savings are converted for display."
        control={
          <Segmented<Currency>
            testIdPrefix="currency-switch"
            value={settings!.currency}
            options={[{ value: "INR", label: "₹ INR" }, { value: "USD", label: "$ USD" }]}
            onChange={(c) => save.mutate({ ...settings!, currency: c })}
          />
        }
      />
      <SettingRow
        label="Exchange rate"
        help="Rupees per US dollar. Update it when rates move."
        control={
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">$1 = ₹</span>
            <Input
              data-testid="usd-inr-rate-input"
              type="number"
              step="0.1"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              onBlur={commitRate}
              onKeyDown={(e) => e.key === "Enter" && commitRate()}
              className="h-8 w-24 font-mono text-xs"
            />
          </div>
        }
      />
    </SettingsSection>
  );
};
