import { PageHeader, Card } from "../components/PageHeader";
import { CopyField } from "../components/CopyField";
import { PricingTable } from "../components/PricingTable";
import { useProviders } from "../hooks/queries";
import { PROXY_URLS, Provider } from "../lib/api";
import { PROVIDER_NAME, formatInt, timeAgo } from "../lib/format";
import { cn } from "../lib/utils";
import { PageSkeleton } from "./Overview";

const STATUS: Record<Provider["status"], { label: string; dot: string; ring: string }> = {
  receiving_traffic: { label: "Receiving traffic", dot: "bg-savings", ring: "ring-savings/20" },
  synthetic_only: { label: "Demo data only", dot: "bg-muted-foreground", ring: "" },
  waiting: { label: "Waiting for first request", dot: "border border-muted-foreground", ring: "" },
  stubbed: { label: "Stubbed — coming later", dot: "border border-dashed border-muted-foreground", ring: "" },
};

const UPSTREAM: Record<string, string> = {
  mock: "Local mock LLM server",
  real: "api.openai.com (pass-through)",
  test: "Stripe test mode",
};

const PROVIDER_ICON: Record<string, string> = { openai: "AI", stripe: "$", aws: "☁" };

const Stat = ({ label, value, testId }: { label: string; value: string; testId: string }) => (
  <div>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd data-testid={testId} className="mt-1 font-mono text-sm">{value}</dd>
  </div>
);

const ProviderCard = ({ p }: { p: Provider }) => {
  const s = STATUS[p.status];
  return (
    <Card testId={`provider-card-${p.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-accent font-mono text-sm text-muted-foreground">
            {PROVIDER_ICON[p.id]}
          </div>
          <h2 className="text-sm font-medium">{PROVIDER_NAME[p.id]}</h2>
        </div>
        <span
          data-testid={`provider-status-${p.id}`}
          className={cn(
            "flex items-center gap-2 rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground",
            p.status === "receiving_traffic" && "border-savings/20 bg-savings/[0.06] text-savings",
          )}
        >
          {p.status === "receiving_traffic" ? (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-savings opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-savings" />
            </span>
          ) : (
            <span className={cn("h-2 w-2 rounded-full", s.dot)} />
          )}
          {s.label}
        </span>
      </div>
      <div className="space-y-6 px-6 py-6">
        {p.id !== "aws" ? (
          <>
            <div>
              <p className="mb-2 text-xs text-muted-foreground">Proxy base URL · upstream: {UPSTREAM[p.upstream_mode ?? "test"]}</p>
              <CopyField value={PROXY_URLS[p.id]} testId={`provider-${p.id}-copy-url-button`} />
            </div>
            <dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">
              <Stat label="Via proxy" value={formatInt(p.counts.proxy)} testId={`provider-${p.id}-proxy-count`} />
              <Stat label="Synthetic" value={formatInt(p.counts.synthetic)} testId={`provider-${p.id}-synthetic-count`} />
              <Stat label="Open issues" value={formatInt(p.issue_count)} testId={`provider-${p.id}-issue-count`} />
              <Stat label="Last proxied" value={timeAgo(p.last_proxy_request_at)} testId={`provider-${p.id}-last-seen`} />
            </dl>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">{p.pricing.notes}</p>
        )}
        <PricingTable provider={p} />
      </div>
    </Card>
  );
};

export default function Providers() {
  const { data, isLoading } = useProviders();
  if (isLoading || !data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader
        title="Providers"
        description="Where your traffic goes, whether we're seeing it, and the pricing we use to estimate cost. API keys are forwarded to the provider and never stored."
      />
      <div className="space-y-6">{data.map((p) => <ProviderCard key={p.id} p={p} />)}</div>
    </div>
  );
}
