import { Switch } from "../ui/switch";
import { TierBadge } from "../Badges";
import { useApp } from "../../context/AppContext";
import { useRules, useSaveSettings } from "../../hooks/queries";
import { SettingRow, SettingsSection } from "./SettingsSection";

const TIERS = [
  { tier: 1, title: "Always trustworthy", help: "Exact matches on logged metadata. These feed the headline savings number." },
  { tier: 2, title: "Threshold-based", help: "Depend on the thresholds below. Also counted in the headline number." },
  { tier: 3, title: "Experimental LLM checks", help: "Heuristics with a confidence score. Never included in the headline number." },
];

export const RulesSection = () => {
  const { settings } = useApp();
  const { data: rules = [] } = useRules();
  const save = useSaveSettings();
  const s = settings!;
  const setRule = (id: string, v: boolean) => save.mutate({ ...s, rules: { ...s.rules, [id]: v } });

  return (
    <SettingsSection testId="settings-rules" title="Detection rules" description="Each rule is a separate check. Turning one off removes its issues and savings on the next run.">
      <div className="space-y-8">
        {TIERS.map((t) => (
          <div key={t.tier}>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <TierBadge tier={t.tier} />
              <span className="text-xs text-muted-foreground">{t.help}</span>
            </div>
            {t.tier === 3 && (
              <SettingRow
                className="mb-2 rounded-md border border-dashed border-primary/50 px-4 py-3 first:pt-3 last:border-b last:pb-3"
                label="Enable experimental checks"
                help="Opt-in. Findings show a distinct badge and a confidence score."
                control={
                  <Switch
                    data-testid="tier-3-experimental-toggle"
                    checked={s.experimental_enabled}
                    onCheckedChange={(v: boolean) => save.mutate({ ...s, experimental_enabled: v })}
                    aria-label="Enable experimental checks"
                  />
                }
              />
            )}
            <div className={t.tier === 3 && !s.experimental_enabled ? "pointer-events-none opacity-50" : ""}>
              {rules.filter((r) => r.tier === t.tier).map((r) => (
                <SettingRow
                  key={r.id}
                  label={r.name}
                  help={r.description}
                  control={
                    <Switch
                      data-testid={`rule-toggle-${r.id}`}
                      checked={!!s.rules[r.id]}
                      disabled={t.tier === 3 && !s.experimental_enabled}
                      onCheckedChange={(v: boolean) => setRule(r.id, v)}
                      aria-label={r.name}
                    />
                  }
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </SettingsSection>
  );
};
