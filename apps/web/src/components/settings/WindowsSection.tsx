import { useEffect, useState } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { useApp } from "../../context/AppContext";
import { useSaveSettings } from "../../hooks/queries";
import type { Windows } from "../../lib/api";
import { SettingsSection } from "./SettingsSection";

const FIELDS: { key: keyof Windows; label: string; unit: string; help: string }[] = [
  { key: "short_window_s", label: "Short window", unit: "s", help: "Identical calls this close together count as duplicates." },
  { key: "long_window_s", label: "Long window", unit: "s", help: "Identical read calls within this gap suggest missing caching." },
  { key: "retry_min_backoff_ms", label: "Minimum retry backoff", unit: "ms", help: "Retries after an error faster than this are a storm." },
  { key: "retry_min_attempts", label: "Attempts in a storm", unit: "calls", help: "How many rapid attempts before we flag it." },
  { key: "oversized_bytes", label: "Oversized payload", unit: "bytes", help: "Request or response bodies above this are flagged." },
  { key: "unbatched_min_calls", label: "Calls per burst", unit: "calls", help: "Single calls in a burst before suggesting batching." },
  { key: "unbatched_window_s", label: "Burst gap", unit: "s", help: "Max gap between calls in the same burst." },
  { key: "token_bloat_min_repeats", label: "Context resends", unit: "times", help: "Experimental: repeats of the same context." },
  { key: "token_bloat_min_prompt_tokens", label: "Large context", unit: "tokens", help: "Experimental: prompt size that counts as large." },
  { key: "model_overuse_max_prompt_tokens", label: "Small task — prompt", unit: "tokens", help: "Experimental: max prompt for a 'small' task." },
  { key: "model_overuse_max_completion_tokens", label: "Small task — answer", unit: "tokens", help: "Experimental: max answer for a 'small' task." },
];

export const WindowsSection = () => {
  const { settings } = useApp();
  const save = useSaveSettings();
  const [draft, setDraft] = useState<Windows>(settings!.windows);
  useEffect(() => setDraft(settings!.windows), [settings]);
  const dirty = FIELDS.some((f) => draft[f.key] !== settings!.windows[f.key]);
  const valid = FIELDS.every((f) => Number(draft[f.key]) > 0);

  return (
    <SettingsSection testId="settings-windows" title="Windows and thresholds" description="Detection windows are config parameters. Lower thresholds catch more, but may flag legitimate traffic.">
      <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <label key={f.key} className="block">
            <span className="text-sm">{f.label}</span>
            <div className="mt-1.5 flex items-center gap-2">
              <Input
                data-testid={`window-input-${f.key}`}
                type="number"
                min={0}
                value={draft[f.key]}
                onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value === "" ? "" : Number(e.target.value) } as Windows)}
                className="h-8 font-mono text-xs"
              />
              <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">{f.unit}</span>
            </div>
            <span className="mt-1 block text-xs text-muted-foreground">{f.help}</span>
          </label>
        ))}
      </div>
      <div className="mt-6 flex items-center gap-3">
        <Button size="sm" data-testid="save-windows-button" disabled={!dirty || !valid || save.isPending} onClick={() => save.mutate({ ...settings!, windows: draft })}>
          Save thresholds
        </Button>
        {dirty && (
          <Button size="sm" variant="ghost" data-testid="discard-windows-button" onClick={() => setDraft(settings!.windows)}>
            Discard changes
          </Button>
        )}
      </div>
    </SettingsSection>
  );
};
