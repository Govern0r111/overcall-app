import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { PageHeader, Card } from "../components/PageHeader";
import { useLogs } from "../hooks/queries";
import { useApp } from "../context/AppContext";
import { PageSkeleton } from "./Overview";
import type { LogEntry } from "../lib/api";

const demoLogs: LogEntry[] = [
  { id: "log-1", timestamp: new Date().toISOString(), provider: "openai", endpoint: "/v1/chat/completions", status: 200, latency_ms: 842, req_size: 1240, resp_size: 4380, prompt_tokens: 920, completion_tokens: 310, cost_usd: 0.014, flagged_by: ["duplicate_request"] },
  { id: "log-2", timestamp: new Date(Date.now() - 420000).toISOString(), provider: "stripe", endpoint: "/v1/payment_intents", status: 201, latency_ms: 208, req_size: 640, resp_size: 910, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0.002, flagged_by: [] },
  { id: "log-3", timestamp: new Date(Date.now() - 920000).toISOString(), provider: "openai", endpoint: "/v1/embeddings", status: 429, latency_ms: 1204, req_size: 860, resp_size: 180, prompt_tokens: 1220, completion_tokens: 0, cost_usd: 0.008, flagged_by: ["retry_storm"] },
];

export default function Logs() {
  const [filters, setFilters] = useState({ search: "", provider: "", status_class: "" });
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const { data, isLoading, isError } = useLogs(filters);
  const { money } = useApp();
  const filtered = useMemo(() => {
    const rows = data ?? (isError ? demoLogs : []);
    const search = filters.search.toLowerCase();
    return rows.filter((row) =>
      (!search || row.endpoint.toLowerCase().includes(search) || row.provider.includes(search)) &&
      (!filters.provider || row.provider === filters.provider) &&
      (!filters.status_class || `${Math.floor(row.status / 100)}xx` === filters.status_class)
    );
  }, [data, filters, isError]);

  if (isLoading && !isError) return <PageSkeleton />;
  return <div><PageHeader title="Logs" description="Raw request metadata flowing through the proxy. Request bodies are never shown." /><div className="mb-4 flex flex-wrap gap-2"><label className="relative flex min-w-[220px] flex-1 items-center"><Search className="absolute left-3 h-4 w-4 text-muted-foreground" /><input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="Search endpoint or provider" className="h-10 w-full rounded-md border border-input bg-card pl-9 pr-3 text-sm" /></label><select value={filters.provider} onChange={(e) => setFilters({ ...filters, provider: e.target.value })} className="h-10 rounded-md border border-input bg-card px-3 text-sm"><option value="">All providers</option><option value="openai">OpenAI</option><option value="stripe">Stripe</option><option value="aws">AWS</option></select><select value={filters.status_class} onChange={(e) => setFilters({ ...filters, status_class: e.target.value })} className="h-10 rounded-md border border-input bg-card px-3 text-sm"><option value="">All statuses</option><option value="2xx">2xx success</option><option value="4xx">4xx client error</option><option value="5xx">5xx server error</option></select></div><Card><div className="overflow-x-auto"><table className="w-full min-w-[820px] text-left text-sm"><thead className="border-b border-divider text-xs text-muted-foreground"><tr>{["Time", "Provider", "Endpoint", "Status", "Latency", "Size", "Tokens", "Cost", "Flagged by"].map((heading) => <th key={heading} className="px-5 py-3 font-medium">{heading}</th>)}</tr></thead><tbody>{filtered.map((row) => <tr key={row.id} onClick={() => setSelected(row)} className="cursor-pointer border-b border-divider last:border-0 hover:bg-accent/50"><td className="whitespace-nowrap px-5 py-4 text-xs text-muted-foreground">{new Date(row.timestamp).toLocaleTimeString()}</td><td className="px-5 py-4 capitalize">{row.provider}</td><td className="px-5 py-4 font-mono text-xs">{row.endpoint}</td><td className="px-5 py-4 font-mono text-xs">{row.status}</td><td className="px-5 py-4 font-mono text-xs">{row.latency_ms}ms</td><td className="px-5 py-4 font-mono text-xs">{formatBytes(row.req_size + row.resp_size)}</td><td className="px-5 py-4 font-mono text-xs">{(row.prompt_tokens + row.completion_tokens).toLocaleString()}</td><td className="px-5 py-4 font-mono text-xs">{money(row.cost_usd)}</td><td className="px-5 py-4 text-xs text-warning">{row.flagged_by.join(", ") || "—"}</td></tr>)}</tbody></table>{!filtered.length && <p className="px-5 py-10 text-center text-sm text-muted-foreground">No requests match those filters.</p>}</div></Card>{selected && <aside role="dialog" aria-label="Request metadata" className="fixed inset-y-0 right-0 z-40 w-full max-w-md border-l border-border bg-card p-6 "><button aria-label="Close request details" onClick={() => setSelected(null)} className="float-right rounded p-1 text-muted-foreground hover:bg-accent"><X className="h-4 w-4" /></button><h2 className="text-lg font-semibold">Request metadata</h2><dl className="mt-8 space-y-4 text-sm">{Object.entries({ Provider: selected.provider, Endpoint: selected.endpoint, Status: selected.status, Latency: `${selected.latency_ms}ms`, "Request size": formatBytes(selected.req_size), "Response size": formatBytes(selected.resp_size), "Flagged by": selected.flagged_by.join(", ") || "None" }).map(([key, value]) => <div key={key} className="flex justify-between gap-4 border-b border-divider pb-3"><dt className="text-muted-foreground">{key}</dt><dd className="font-mono text-right text-xs">{value}</dd></div>)}</dl></aside>}</div>;
}

function formatBytes(bytes: number) { return bytes > 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`; }
