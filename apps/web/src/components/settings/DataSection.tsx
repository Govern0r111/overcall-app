import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { useClearData, useLoadSynthetic } from "../../hooks/queries";
import { SettingRow, SettingsSection } from "./SettingsSection";

export const DataSection = () => {
  const [seed, setSeed] = useState("42");
  const [confirming, setConfirming] = useState(false);
  const load = useLoadSynthetic();
  const clear = useClearData();

  const onClear = () => {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 4000);
      return;
    }
    setConfirming(false);
    clear.mutate();
  };

  return (
    <SettingsSection testId="settings-data" title="Data" description="Request logs expire after 30 days automatically.">
      <SettingRow
        label="Synthetic demo data"
        help="Replaces existing synthetic logs with 7 days of realistic traffic. The same seed always produces the same data."
        control={
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">seed</span>
            <Input data-testid="synthetic-seed-input" type="number" value={seed} onChange={(e) => setSeed(e.target.value)} className="h-8 w-20 font-mono text-xs" />
            <Button size="sm" variant="outline" data-testid="settings-load-synthetic-button" disabled={load.isPending} onClick={() => load.mutate(Number(seed) || 0)}>
              {load.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
              Load
            </Button>
          </div>
        }
      />
      <SettingRow
        label="Clear all data"
        help="Deletes every logged request (synthetic and proxied) and all detected issues."
        control={
          <Button size="sm" variant="outline" data-testid="clear-data-button" disabled={clear.isPending} onClick={onClear}
            className={confirming ? "border-primary/50 text-primary hover:text-primary" : ""}>
            {confirming ? "Click again to confirm" : "Clear data"}
          </Button>
        }
      />
    </SettingsSection>
  );
};
