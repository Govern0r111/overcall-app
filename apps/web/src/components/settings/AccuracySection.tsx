import { useEvaluation, useProviders } from "../../hooks/queries";
import { SettingsSection } from "./SettingsSection";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export const AccuracySection = () => {
  const { data } = useEvaluation();
  const { data: providers } = useProviders();
  return (
    <SettingsSection
      testId="settings-accuracy"
      title="Pricing and accuracy"
      description="Pricing tables are versioned config files that need a manual update when providers change prices. Accuracy is measured against the synthetic data's known ground truth."
    >
      <ul className="mb-6 space-y-1.5 text-xs">
        {providers?.map((p) => (
          <li key={p.id} data-testid={`pricing-version-${p.id}`} className="flex justify-between gap-4 font-mono">
            <span>pricing/{p.id}.json</span>
            <span className="text-muted-foreground">v{p.pricing.version}</span>
          </li>
        ))}
      </ul>
      {data?.has_data && !data.using_default_windows && (
        <p data-testid="accuracy-custom-windows-note" className="mb-3 text-xs leading-relaxed text-muted-foreground">
          Measured with your custom thresholds. The ground truth assumes the defaults, so lower recall here means your
          thresholds are stricter than the patterns in the demo data.
        </p>
      )}
      {data?.has_data ? (
        <div className="overflow-x-auto rounded-md border border-border">
          <table data-testid="accuracy-table" className="w-full min-w-[480px] text-xs">
            <thead>
              <tr className="border-b border-divider text-left text-muted-foreground">
                {["Rule", "Known waste", "Flagged", "Precision", "Recall"].map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}
              </tr>
            </thead>
            <tbody className="font-mono">
              {data.rules.map((r) => (
                <tr key={r.rule_id} data-testid={`accuracy-row-${r.rule_id}`} className="border-b border-divider last:border-b-0">
                  <td className="px-3 py-2 font-sans">{r.rule_name}</td>
                  <td className="px-3 py-2">{r.ground_truth}</td>
                  <td className="px-3 py-2">{r.flagged}</td>
                  <td className="px-3 py-2">{pct(r.precision)}</td>
                  <td className="px-3 py-2">{pct(r.recall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Load synthetic data to see how accurately each rule detects known waste.</p>
      )}
    </SettingsSection>
  );
};
