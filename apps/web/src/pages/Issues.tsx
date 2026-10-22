import { useState } from "react";
import { Link } from "react-router-dom";
import { FlaskConical, Filter } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { PageHeader, Card } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { IssueRow } from "../components/IssueRow";
import { useIssues, useOverview } from "../hooks/queries";
import { useApp } from "../context/AppContext";
import { PageSkeleton } from "./Overview";

const FILTERS = [
  { key: "provider", label: "Provider", options: [["all", "All providers"], ["openai", "OpenAI"], ["stripe", "Stripe"], ["aws", "AWS"]] },
  { key: "severity", label: "Severity", options: [["all", "All severities"], ["critical", "Critical"], ["warning", "Warning"], ["info", "Low"]] },
  { key: "tier", label: "Detection tier", options: [["all", "All tiers"], ["1", "Deterministic"], ["2", "Tunable threshold"], ["3", "Experimental"]] },
] as const;

const FilterSelect = ({ f, value, onChange }: { f: (typeof FILTERS)[number]; value: string; onChange: (v: string) => void }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger data-testid={`issue-filter-${f.key}-select`} aria-label={f.label} className="h-9 w-[170px] bg-card text-sm">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      {f.options.map(([v, l]) => (
        <SelectItem key={v} value={v} data-testid={`issue-filter-${f.key}-option-${v}`}>{l}</SelectItem>
      ))}
    </SelectContent>
  </Select>
);

export default function Issues() {
  const [filters, setFilters] = useState({ provider: "all", severity: "all", tier: "all" });
  const overview = useOverview();
  const { data: issues, isLoading } = useIssues(filters);
  const { money, settings } = useApp();

  if (overview.isLoading || !overview.data) return <PageSkeleton />;
  if (!overview.data.has_data) return <EmptyState />;

  const total = (issues ?? []).reduce((s, i) => s + i.projected_monthly_usd, 0);
  const activeFilters = Object.values(filters).filter((v) => v !== "all").length;

  return (
    <div>
      <PageHeader title="Issues" description="Every wasteful pattern we found, highest impact first. Select a row to see what we detected and how to fix it." />
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Filter className="h-3.5 w-3.5" />
          Filter
        </div>
        {FILTERS.map((f) => (
          <FilterSelect key={f.key} f={f} value={filters[f.key]} onChange={(v) => setFilters({ ...filters, [f.key]: v })} />
        ))}
        <p data-testid="issues-summary" className="ml-auto text-sm text-muted-foreground">
          <span className="font-mono text-foreground">{issues?.length ?? 0}</span> issues ·{" "}
          <span className="font-mono text-savings">{money(total)}</span>/mo
        </p>
      </div>
      {!settings?.experimental_enabled && (
        <p data-testid="experimental-off-hint" className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
          <FlaskConical className="h-3.5 w-3.5" /> Experimental LLM checks are off.
          <Link to="/settings" className="text-primary hover:underline">Turn them on in Settings</Link>
        </p>
      )}
      <Card testId="issues-list">
        {isLoading ? (
          <p className="px-5 py-8 text-sm text-muted-foreground">Loading issues…</p>
        ) : issues?.length ? (
          <ul>{issues.map((i, idx) => <IssueRow key={i.id} issue={i} index={idx} />)}</ul>
        ) : (
          <p data-testid="issues-empty-filtered" className="px-5 py-10 text-sm text-muted-foreground">
            No issues match these filters. Try widening the provider, severity or tier.
          </p>
        )}
      </Card>
    </div>
  );
}
