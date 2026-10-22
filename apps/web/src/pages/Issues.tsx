import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { copyToClipboard } from "../components/CopyField";
import { PageHeader } from "../components/PageHeader";
import { DemoBanner, EmptyState, ErrorBox, LoadDemoButton, Loading, Pill, Select, SeverityBadge } from "../components/common";
import { useApp } from "../context/AppContext";
import { useIssue, useIssues, useSettings } from "../hooks/queries";
import { formatBytes, formatTime, PROVIDER_NAME } from "../lib/format";
import type { Issue } from "../lib/api";

const Detail = ({ id }: { id: string }) => {
  const { data, isLoading, error } = useIssue(id);
  const { money } = useApp();
  const [copiedFix, setCopiedFix] = useState(false);
  const [copyError, setCopyError] = useState("");
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;

  return (
    <div className="space-y-4 border-t border-border bg-background/50 px-5 py-4 text-sm" data-testid="issue-detail">
      <div>
        <h3 className="font-semibold">What we detected</h3>
        <p className="mt-1 text-muted-foreground">{data.summary}</p>
      </div>
      <div>
        <h3 className="font-semibold">Why it matters</h3>
        <p className="mt-1 text-muted-foreground">{data.explanation}</p>
      </div>
      <div>
        <h3 className="font-semibold">Suggested fix</h3>
        <p className="mt-1 text-muted-foreground">{data.suggested_fix}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2"
          onClick={async () => {
            setCopyError("");
            try {
              await copyToClipboard(data.suggested_fix);
              setCopiedFix(true);
            } catch (cause) {
              setCopyError(cause instanceof Error ? cause.message : "Could not copy the suggested fix.");
            }
          }}
        >
          {copiedFix ? "Copied" : "Copy suggested fix"}
        </Button>
        {copyError && <p role="alert" className="mt-1 text-xs text-destructive">{copyError}</p>}
      </div>
      <p className="text-xs text-muted-foreground">
        {data.impact_kind === "spend"
          ? `Estimated savings: ${money(data.window_savings_usd)} in this window.`
          : data.provider === "stripe"
            ? "Modelled overhead (not billed by Stripe)."
            : "Reliability finding; this is not counted as spend savings."}
      </p>
      <p className="font-mono text-xs text-muted-foreground">
        Detected {formatTime(data.detected_at)}
        {data.experimental && ` · confidence ${data.confidence == null ? "unknown" : `${Math.round(data.confidence * 100)}%`}`}
      </p>
      {!!data.sample_requests?.length && (
        <div>
          <h3 className="mb-1 font-semibold">Sample requests</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3">Hash</th><th className="pr-3">Size</th><th className="pr-3">Time</th>
                  <th className="pr-3">Status</th><th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {data.sample_requests.map((sample) => (
                  <tr key={sample.request_id} className="border-t border-border/60 font-mono">
                    <td className="py-1.5 pr-3">{sample.req_hash ?? "—"}</td>
                    <td className="pr-3">{formatBytes(sample.req_size ?? 0)}</td>
                    <td className="pr-3">{formatTime(sample.occurred_at)}</td>
                    <td className="pr-3">{sample.status}</td>
                    <td>{money(sample.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <Link to={`/logs?issue=${encodeURIComponent(id)}`} className="inline-block text-xs text-primary hover:underline">
        View matching requests in logs
      </Link>
    </div>
  );
};

const Row = ({ issue, open, onToggle }: { issue: Issue; open: boolean; onToggle: () => void }) => {
  const { money } = useApp();
  return (
    <li className="rounded-lg border border-border bg-card" data-testid="issue-row">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{issue.title}</span>
          <span className="mt-1 block truncate text-xs text-muted-foreground">
            {PROVIDER_NAME[issue.provider] ?? issue.provider} · <span className="font-mono">{issue.endpoint}</span> · {issue.affected_count} requests · tier {issue.tier}
            {issue.experimental && " · experimental"}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {issue.impact_kind === "spend"
            ? <span className="font-mono text-sm">{money(issue.projected_monthly_usd)}/mo</span>
            : <Pill>reliability</Pill>}
          <SeverityBadge severity={issue.severity} />
        </span>
      </button>
      {open && <Detail id={issue.id} />}
    </li>
  );
};

export default function Issues() {
  const [params, setParams] = useSearchParams();
  const [provider, setProvider] = useState(params.get("provider") ?? "all");
  const [severity, setSeverity] = useState(params.get("severity") ?? "all");
  const [tier, setTier] = useState(params.get("tier") ?? "all");
  const [openId, setOpenId] = useState<string | null>(params.get("open"));
  const settings = useSettings();
  const q = useIssues({ provider, severity, tier });
  const allItems = q.data?.pages.flatMap((page) => page.items) ?? [];
  const items = allItems.filter((issue) => settings.data?.tier3_enabled || !issue.experimental);
  const filtered = provider !== "all" || severity !== "all" || tier !== "all";

  useEffect(() => {
    setProvider(params.get("provider") ?? "all");
    setSeverity(params.get("severity") ?? "all");
    setTier(params.get("tier") ?? "all");
    setOpenId(params.get("open"));
  }, [params]);

  const updateFilters = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => {
      if (!value || value === "all") next.delete(key);
      else next.set(key, value);
    });
    setParams(next, { replace: true });
  };
  const toggleOpen = (id: string) => updateFilters({ open: openId === id ? "" : id });
  const clearFilters = () => {
    const next = new URLSearchParams();
    if (openId) next.set("open", openId);
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader title="Issues" description="Patterns that waste money or hurt reliability. Open an issue to see what we detected and how to fix it." />
      <DemoBanner />
      <div className="mb-6 flex flex-wrap gap-4">
        <Select label="Provider" value={provider} onChange={(value) => updateFilters({ provider: value })} options={[
          { value: "all", label: "All" }, { value: "openai", label: "OpenAI" }, { value: "stripe", label: "Stripe" },
        ]} />
        <Select label="Severity" value={severity} onChange={(value) => updateFilters({ severity: value })} options={[
          { value: "all", label: "All" }, { value: "critical", label: "Critical" },
          { value: "warning", label: "Warning" }, { value: "info", label: "Info" },
        ]} />
        <Select label="Tier" value={tier} onChange={(value) => updateFilters({ tier: value })} options={[
          { value: "all", label: "All" }, { value: "1", label: "Tier 1" }, { value: "2", label: "Tier 2" },
          { value: "3", label: settings.data?.tier3_enabled ? "Tier 3 (experimental)" : "Tier 3 (off)" },
        ]} />
      </div>
      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} />}
      {q.data && items.length === 0 && (
        <EmptyState
          title={filtered ? "No issues match these filters" : "No issues found"}
          body={filtered ? "Clear a filter or turn on experimental findings in Settings." : "Load demo data, or send traffic through the proxy and run detection."}
          action={filtered ? <Button variant="outline" onClick={clearFilters}>Clear filters</Button> : <LoadDemoButton />}
        />
      )}
      <ul className="space-y-3">
        {items.map((issue) => (
          <Row key={issue.id} issue={issue} open={openId === issue.id} onToggle={() => toggleOpen(issue.id)} />
        ))}
      </ul>
      {q.hasNextPage && (
        <div className="mt-6 flex justify-center">
          <Button variant="outline" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
            {q.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}
    </>
  );
}
