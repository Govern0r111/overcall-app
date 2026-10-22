import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "../components/ui/button";
import { Card, PageHeader } from "../components/PageHeader";
import { DemoBanner, EmptyState, ErrorBox, LoadDemoButton, Loading, SeverityBadge } from "../components/common";
import { useApp } from "../context/AppContext";
import { useOverview, useRunDetection } from "../hooks/queries";
import { formatDay, formatInt, PROVIDER_NAME } from "../lib/format";

const Stat = ({ label, value, hint }: { label: string; value: string; hint?: string }) => (
  <Card className="p-5">
    <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
    <p className="mt-2 font-mono text-2xl font-semibold">{value}</p>
    {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
  </Card>
);

export default function Overview() {
  const { data, isLoading, error } = useOverview();
  const { money, settings } = useApp();
  const run = useRunDetection();

  return (
    <>
      <PageHeader
        title="Overview"
        description="How much of your API spend looks avoidable, and where it comes from."
        actions={
          <Button variant="outline" onClick={() => run.mutate()} disabled={run.isPending || !data?.has_data}>
            {run.isPending ? "Running…" : "Re-run detection"}
          </Button>
        }
      />
      <DemoBanner />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} />}
      {data && !data.has_data && (
        <EmptyState
          title="No traffic yet"
          body="Load demo data to see the dashboard with realistic requests, or send real requests through the proxy (see Providers)."
          action={<LoadDemoButton />}
        />
      )}
      {data?.has_data && (
        <div className="space-y-8">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Estimated savings / month"
              value={money(data.spend_savings.projected_monthly_usd)}
              hint={data.spend_savings.projected_monthly_usd === 0
                ? "No waste found in this window."
                : `${data.spend_savings.percent_of_spend}% of spend in this window`}
            />
            <Stat label="Spend in window" value={money(data.total_spend_usd)} hint={`${data.window.days} days`} />
            <Stat
              label="Requests"
              value={formatInt(data.request_count)}
              hint={`${formatInt(data.flagged_request_count)} flagged`}
            />
            <Stat
              label="Reliability findings"
              value={String(data.reliability_findings.count)}
              hint={`≈ ${money(data.reliability_findings.modelled_overhead_monthly_usd)}/mo modelled overhead`}
            />
          </div>
          {data.window.low_confidence_projection && (
            <p className="text-sm text-muted-foreground">
              Based on less than a day of traffic, so this projection may swing a lot.
            </p>
          )}
          {settings?.tier3_enabled && data.experimental_spend_savings.projected_monthly_usd > 0 && (
            <p className="text-sm text-muted-foreground">
              Up to {money(data.experimental_spend_savings.projected_monthly_usd)} more from experimental checks (not included).
            </p>
          )}

          <Card className="p-5">
            <h2 className="mb-4 text-sm font-semibold">Spend and avoidable spend per day</h2>
            <div className="h-64 min-w-0" data-testid="trend-chart" role="img" aria-label="Daily spend and estimated waste trend">
              <ResponsiveContainer width="100%" height={240} minWidth={0}>
                <LineChart data={data.trend.map((t) => ({ ...t, day: formatDay(t.date) }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => money(v, true)} width={60} />
                  <Tooltip formatter={(v: number) => money(v)} />
                  <Line type="monotone" dataKey="spend_usd" name="Spend" stroke="hsl(var(--primary))" dot={false} />
                  <Line type="monotone" dataKey="waste_usd" name="Estimated waste" stroke="hsl(var(--warning))" strokeDasharray="6 4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <table className="sr-only">
              <caption>Daily spend and estimated waste</caption>
              <thead><tr><th>Date</th><th>Spend</th><th>Estimated waste</th></tr></thead>
              <tbody>{data.trend.map((point) => (
                <tr key={point.date}><td>{formatDay(point.date)}</td><td>{money(point.spend_usd)}</td><td>{money(point.waste_usd)}</td></tr>
              ))}</tbody>
            </table>
          </Card>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Top issues</h2>
                <Link to="/issues" className="text-sm text-primary hover:underline">
                  All issues
                </Link>
              </div>
              <ul className="divide-y divide-border">
                {data.top_issues.map((i) => (
                  <li key={i.id} className="flex items-center justify-between gap-4 py-3">
                    <div className="min-w-0">
                      <Link to={`/issues?open=${encodeURIComponent(i.id)}`} className="truncate text-sm font-medium hover:text-primary hover:underline">{i.title}</Link>
                      <p className="truncate text-xs text-muted-foreground">
                        {PROVIDER_NAME[i.provider] ?? i.provider} · {i.endpoint} · {i.affected_count} requests
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="font-mono text-sm">{money(i.projected_monthly_usd)}/mo</span>
                      <SeverityBadge severity={i.severity} />
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
            <Card className="p-5">
              <h2 className="mb-4 text-sm font-semibold">By provider</h2>
              <ul className="space-y-3">
                {data.by_provider.map((p) => (
                  <li key={p.provider} className="flex justify-between text-sm">
                    <span>{PROVIDER_NAME[p.provider] ?? p.provider}</span>
                    <span className="font-mono text-muted-foreground">
                      {money(p.spend_usd)} · {p.issue_count} issues
                    </span>
                  </li>
                ))}
              </ul>
              <h2 className="mb-3 mt-6 text-sm font-semibold">Severity</h2>
              <p className="font-mono text-sm text-muted-foreground">
                {data.severity_breakdown.critical} critical · {data.severity_breakdown.warning} warning ·{" "}
                {data.severity_breakdown.info} info
              </p>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
