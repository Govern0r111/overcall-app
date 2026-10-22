import { Link } from "react-router-dom";
import { ArrowRight, Loader2, RefreshCw, AlertTriangle, AlertCircle, Info } from "lucide-react";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { PageHeader, Card } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { HeroSavings } from "../components/HeroSavings";
import { TrendChart } from "../components/TrendChart";
import { IssueRow } from "../components/IssueRow";
import { DemoBanner } from "../components/DemoBanner";
import { useOverview, useRerun } from "../hooks/queries";
import { useApp } from "../context/AppContext";
import { formatInt, timeAgo, PROVIDER_NAME } from "../lib/format";
import type { Severity } from "../lib/api";

export const PageSkeleton = () => (
  <div data-testid="page-loading" className="space-y-6">
    <Skeleton className="h-8 w-48" />
    <div className="grid gap-6 lg:grid-cols-5">
      <Skeleton className="h-80 lg:col-span-2" />
      <Skeleton className="h-80 lg:col-span-3" />
    </div>
  </div>
);

const SEVERITY_META: Record<Severity, { label: string; icon: typeof AlertTriangle; color: string }> = {
  critical: { label: "Critical", icon: AlertCircle, color: "text-critical" },
  warning: { label: "Warning", icon: AlertTriangle, color: "text-warning" },
  info: { label: "Low", icon: Info, color: "text-muted-foreground" },
};

const SeverityBar = ({ counts }: { counts: Record<Severity, number> }) => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  const order: Severity[] = ["critical", "warning", "info"];
  const widths = order.map((s) => ({ s, w: (counts[s] / total) * 100 }));
  return (
    <div data-testid="severity-distribution" className="flex flex-wrap items-center gap-4">
      <div className="flex h-1.5 w-48 overflow-hidden rounded-full bg-accent">
        {widths.filter((w) => w.w > 0).map(({ s, w }) => (
          <div
            key={s}
            data-testid={`severity-bar-${s}`}
            className={s === "critical" ? "bg-critical" : s === "warning" ? "bg-warning" : "bg-muted-foreground"}
            style={{ width: `${w}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-4">
        {order.map((s) => {
          const meta = SEVERITY_META[s];
          const Icon = meta.icon;
          return (
            <span key={s} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Icon className={`h-3.5 w-3.5 ${meta.color}`} strokeWidth={2} />
              <span className="font-mono text-foreground">{counts[s]}</span>
              {meta.label}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const SourceBreakdown = ({ sources }: { sources: Record<string, number> }) => {
  const entries = Object.entries(sources).filter(([, v]) => v > 0);
  if (!entries.length) return null;
  const total = entries.reduce((a, [, v]) => a + v, 0);
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span>Sources:</span>
      {entries.map(([k, v]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          <span className="capitalize">{k}</span>
          <span className="font-mono text-foreground">{formatInt(v)}</span>
          <span>({Math.round((v / total) * 100)}%)</span>
        </span>
      ))}
    </div>
  );
};

export default function Overview() {
  const { data, isLoading } = useOverview();
  const rerun = useRerun();
  if (isLoading || !data) return <PageSkeleton />;
  if (!data.has_data) return <EmptyState />;

  const demoOnly = !!data.sources.synthetic && !data.sources.proxy;
  return (
    <div>
      <PageHeader
        title="Overview"
        description={`${data.window_days.toFixed(1)} days of traffic · ${formatInt(data.request_count)} requests analyzed · updated ${timeAgo(data.ran_at)}`}
        actions={
          <Button variant="outline" size="sm" data-testid="rerun-detection-button" onClick={() => rerun.mutate()} disabled={rerun.isPending}>
            {rerun.isPending ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-2 h-3.5 w-3.5" />}
            Re-run detection
          </Button>
        }
      />
      {demoOnly && <DemoBanner />}
      <div className="grid gap-6 lg:grid-cols-5">
        <HeroSavings data={data} className="lg:col-span-2" />
        <TrendChart data={data.trend} className="lg:col-span-3" />
      </div>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <SeverityBar counts={data.issue_counts} />
        <SourceBreakdown sources={data.sources} />
      </div>
      <Card testId="top-issues-card" className="mt-10">
        <div className="flex items-center justify-between border-b border-divider px-5 py-4">
          <h2 className="text-sm font-medium">Highest-impact issues</h2>
          <Link to="/issues" data-testid="view-all-issues-link" className="flex items-center gap-1 text-sm text-primary hover:underline">
            View all issues <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        {data.top_issues.length ? (
          <ul>{data.top_issues.map((i, idx) => <IssueRow key={i.id} issue={i} index={idx} />)}</ul>
        ) : (
          <p data-testid="no-issues-message" className="px-5 py-8 text-sm text-muted-foreground">No wasteful patterns found. Nice work.</p>
        )}
      </Card>
    </div>
  );
}
