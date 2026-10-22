import type { Provider } from "../lib/api";

const usd = (v: number) => `$${v}`;

const Row = ({ cells }: { cells: React.ReactNode[] }) => (
  <tr className="border-b border-divider last:border-b-0">
    {cells.map((c, i) => <td key={i} className="px-3 py-2">{c}</td>)}
  </tr>
);

const Table = ({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) => (
  <div className="overflow-x-auto rounded-md border border-border">
    <table className="w-full min-w-[480px] font-mono text-xs">
      <thead>
        <tr className="border-b border-divider text-left text-muted-foreground">
          {head.map((h) => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}
        </tr>
      </thead>
      <tbody>{rows.map((r, i) => <Row key={i} cells={r} />)}</tbody>
    </table>
  </div>
);

const body = (p: Provider) => {
  const cfg = p.pricing;
  if (p.id === "openai") {
    return (
      <Table
        head={["Model", "Input / 1M", "Cached input / 1M", "Output / 1M", "Class"]}
        rows={Object.entries<any>(cfg.models).map(([m, v]) => [m, usd(v.input_per_1m), usd(v.cached_input_per_1m), usd(v.output_per_1m), v.tier])}
      />
    );
  }
  if (p.id === "stripe") {
    return (
      <Table
        head={["Item", "Value"]}
        rows={[
          ["Per successful request (overhead model)", usd(cfg.per_request_usd)],
          ["Per failed request", usd(cfg.failed_request_usd)],
          ["Money-moving endpoints", cfg.money_moving_endpoints.join(", ")],
          ["Mode", "Test keys only (sk_test_…)"],
        ]}
      />
    );
  }
  return <Table head={["Service", "Pricing slot"]} rows={Object.entries<any>(cfg.services).map(([k, v]) => [k, JSON.stringify(v)])} />;
};

export const PricingTable = ({ provider }: { provider: Provider }) => (
  <div data-testid={`provider-${provider.id}-pricing`}>
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <p className="text-xs text-muted-foreground">
        Pricing config <span className="font-mono text-foreground">pricing/{provider.id}.json</span> · version{" "}
        <span data-testid={`provider-${provider.id}-pricing-version`} className="font-mono text-foreground">{provider.pricing.version}</span>
      </p>
      <a href={provider.pricing.source} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
        Official pricing
      </a>
    </div>
    {body(provider)}
    {provider.id !== "aws" && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{provider.pricing.notes}</p>}
  </div>
);
