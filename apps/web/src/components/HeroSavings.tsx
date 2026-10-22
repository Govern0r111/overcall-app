import { ArrowDownRight, FlaskConical } from "lucide-react";
import type { Overview } from "../lib/api";
import { formatInt } from "../lib/format";
import { useApp } from "../context/AppContext";
import { useCountUp } from "../hooks/useCountUp";
import { Card } from "./PageHeader";

const Stat = ({ label, value, testId }: { label: string; value: string; testId: string }) => (
  <div>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd data-testid={testId} className="mt-1 font-mono text-sm">{value}</dd>
  </div>
);

export const HeroSavings = ({ data, className = "" }: { data: Overview; className?: string }) => {
  const { money, settings } = useApp();
  const total = Object.values(data.issue_counts).reduce((a, b) => a + b, 0);
  const pct = data.waste_pct.toFixed(data.waste_pct < 10 ? 1 : 0);
  const animatedSavings = useCountUp(data.projected_monthly_usd);
  const hasSavings = data.projected_monthly_usd > 0;

  const line = hasSavings
    ? `Fixing the issues below would cut your API bill by about ${money(data.projected_monthly_usd)} a month — roughly ${pct}% of the ${money(data.projected_monthly_cost_usd)} you're on track to spend.`
    : "No wasteful patterns found in the current traffic. We'll keep watching new requests.";

  return (
    <Card testId="hero-savings-card" className={`flex flex-col p-6 lg:p-8 ${className}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Projected monthly savings</p>
        {hasSavings && (
          <span className="flex items-center gap-1 rounded-full border border-savings/30 bg-savings/[0.06] px-2 py-0.5 text-xs font-medium text-savings">
            <ArrowDownRight className="h-3 w-3" strokeWidth={2} />
            {pct}% avoidable
          </span>
        )}
      </div>
      <p
        data-testid="hero-projected-savings"
        className="mt-3 font-mono text-5xl font-medium tracking-tight text-savings tabular-nums"
      >
        {money(animatedSavings)}
      </p>
      <p data-testid="hero-supporting-line" className="mt-4 text-sm leading-relaxed">{line}</p>
      <dl className="mt-8 grid grid-cols-2 gap-5 border-t border-divider pt-6">
        <Stat label="Current spend" value={`${money(data.projected_monthly_cost_usd)}/mo`} testId="hero-monthly-spend" />
        <Stat label="Avoidable" value={`${pct}%`} testId="hero-waste-pct" />
        <Stat label="Flagged requests" value={`${formatInt(data.flagged_request_count)} of ${formatInt(data.request_count)}`} testId="hero-flagged-requests" />
        <Stat label="Open issues" value={formatInt(total)} testId="hero-issue-count" />
      </dl>
      <p data-testid="hero-trust-note" className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        {settings?.experimental_enabled && data.experimental_projected_monthly_usd > 0 ? (
          <>
            <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
            Experimental checks suggest another {money(data.experimental_projected_monthly_usd)}/mo. Not included above.
          </>
        ) : (
          "Only deterministic and threshold-based checks count toward this number."
        )}
      </p>
    </Card>
  );
};
