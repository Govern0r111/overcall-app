import { Fragment, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/button";
import { PageHeader } from "../components/PageHeader";
import { DemoBanner, EmptyState, ErrorBox, LoadDemoButton, Loading, Pill, Select } from "../components/common";
import { useApp } from "../context/AppContext";
import { useFacets, useLogs } from "../hooks/queries";
import { formatBytes, formatInt, formatTime } from "../lib/format";
import type { LogEntry } from "../lib/api";
import { cn } from "../lib/utils";

const statusColor = (status: number) =>
  status >= 500 ? "text-red-600 dark:text-red-400" : status >= 400 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400";

const Detail = ({ log }: { log: LogEntry }) => {
  const { money } = useApp();
  const rows: [string, string][] = [
    ["Request id", log.id],
    ["Request hash", log.req_hash ?? "—"],
    ["Model", log.model ?? "—"],
    ["Caller", log.caller ?? "—"],
    ["Tokens", `${formatInt(log.prompt_tokens ?? 0)} in / ${formatInt(log.completion_tokens ?? 0)} out${log.tokens_estimated ? " (estimated)" : ""}`],
    ["Cost", `${money(log.cost_usd)} · ${log.cost_basis} · pricing ${log.pricing_version ?? "—"}`],
    ["Latency", `${log.latency_ms ?? "—"} ms (first byte ${log.ttfb_ms ?? "—"} ms)`],
    ["Size", `${formatBytes(log.req_size ?? 0)} request · ${formatBytes(log.resp_size ?? 0)} response`],
    ["Streaming", log.stream ? "yes" : "no"],
    ["Idempotency key", log.has_idempotency_key ? "sent" : "not sent"],
    ["Error", log.error_code ?? "—"],
    ["Origin", `${log.origin}${log.is_demo ? " (demo)" : ""}`],
  ];
  return (
    <div className="space-y-3 bg-background/50 px-4 py-4 text-xs" data-testid="log-detail">
      <dl className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
        {rows.map(([key, value]) => (
          <div key={key} className="flex gap-3">
            <dt className="w-28 shrink-0 text-muted-foreground">{key}</dt>
            <dd className="min-w-0 break-all font-mono">{value}</dd>
          </div>
        ))}
      </dl>
      {log.flagged_by.length > 0 && (
        <p>
          Flagged by:{" "}
          {log.flagged_by.map((flag) => (
            <Link key={flag.issue_id} to={`/issues?open=${encodeURIComponent(flag.issue_id)}`} className="mr-2 inline-block">
              <Pill className="hover:text-foreground">{flag.rule_name ?? flag.rule_id}</Pill>
            </Link>
          ))}
        </p>
      )}
    </div>
  );
};

const rangeStart = (range: string): string | undefined => {
  const durations: Record<string, number> = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "24h": 24 * 60 * 60_000,
    "7d": 7 * 24 * 60 * 60_000,
    "30d": 30 * 24 * 60 * 60_000,
  };
  return durations[range] ? new Date(Date.now() - durations[range]).toISOString() : undefined;
};

const localDateTime = (value: string) => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? ""
    : new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};

export default function Logs() {
  const { money } = useApp();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [debouncedSearch, setDebouncedSearch] = useState(params.get("q") ?? "");
  const [provider, setProvider] = useState(params.get("provider") ?? "all");
  const [statusClass, setStatusClass] = useState(params.get("status_class") ?? "all");
  const [endpoint, setEndpoint] = useState(params.get("endpoint") ?? "all");
  const [model, setModel] = useState(params.get("model") ?? "all");
  const [caller, setCaller] = useState(params.get("caller") ?? "all");
  const [range, setRange] = useState(params.get("range") ?? "all");
  const [openId, setOpenId] = useState<string | null>(null);
  const facets = useFacets();
  const issueId = params.get("issue") ?? undefined;
  const customFrom = params.get("from") ?? "";
  const customTo = params.get("to") ?? "";
  const invalidCustomRange =
    Boolean(customFrom && Number.isNaN(new Date(customFrom).getTime())) ||
    Boolean(customTo && Number.isNaN(new Date(customTo).getTime())) ||
    Boolean(customFrom && customTo && new Date(customFrom) > new Date(customTo));
  const q = useLogs({
    q: debouncedSearch,
    provider,
    status_class: statusClass,
    endpoint,
    model,
    caller,
    issue_id: issueId,
    from: invalidCustomRange ? undefined : customFrom || undefined,
    to: invalidCustomRange ? undefined : customTo || undefined,
  });
  const items = q.data?.pages.flatMap((page) => page.items) ?? [];

  useEffect(() => {
    setSearch(params.get("q") ?? "");
    setProvider(params.get("provider") ?? "all");
    setStatusClass(params.get("status_class") ?? "all");
    setEndpoint(params.get("endpoint") ?? "all");
    setModel(params.get("model") ?? "all");
    setCaller(params.get("caller") ?? "all");
    setRange(params.get("range") ?? "all");
    setDebouncedSearch(params.get("q") ?? "");
  }, [params]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      setDebouncedSearch(search.trim());
      if (search.trim()) next.set("q", search.trim());
      else next.delete("q");
      if (next.toString() !== params.toString()) setParams(next, { replace: true });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search, params, setParams]);

  const updateFilters = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (!value || value === "all") next.delete(key);
      else next.set(key, value);
    }
    if ("range" in changes) {
      next.delete("from");
      next.delete("to");
      const from = rangeStart(changes.range);
      if (from) next.set("from", from);
    }
    setParams(next, { replace: true });
  };
  const options = (values?: { value: string }[]) => [
    { value: "all", label: "All" },
    ...(values ?? []).map((item) => ({ value: item.value, label: item.value })),
  ];

  return (
    <>
      <PageHeader title="Logs" description="Every request seen by Overcall, newest first. Search and filter metadata, then open a row for details." />
      <DemoBanner />
      {issueId && (
        <p className="mb-4 text-sm">
          Showing requests for issue <code className="font-mono">{issueId}</code>{" "}
          <button className="text-primary underline" onClick={() => updateFilters({ issue: "" })}>Clear issue filter</button>
        </p>
      )}
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Search
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Path, model, caller or hash"
            className="h-9 w-56 rounded-md border border-input bg-card px-3 text-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          />
        </label>
        <Select label="Provider" value={provider} onChange={(value) => updateFilters({ provider: value })} options={options(facets.data?.providers)} />
        <Select label="Status" value={statusClass} onChange={(value) => updateFilters({ status_class: value })} options={[
          { value: "all", label: "All" }, { value: "2xx", label: "2xx" }, { value: "3xx", label: "3xx" },
          { value: "4xx", label: "4xx" }, { value: "5xx", label: "5xx" },
        ]} />
        <Select label="Endpoint" value={endpoint} onChange={(value) => updateFilters({ endpoint: value })} options={options(facets.data?.endpoints)} />
        <Select label="Model" value={model} onChange={(value) => updateFilters({ model: value })} options={options(facets.data?.models)} />
        <Select label="Caller" value={caller} onChange={(value) => updateFilters({ caller: value })} options={options(facets.data?.callers)} />
        <Select label="Time range" value={range} onChange={(value) => updateFilters({ range: value })} options={[
          { value: "all", label: "All time" }, { value: "15m", label: "Last 15 minutes" }, { value: "1h", label: "Last hour" },
          { value: "24h", label: "Last 24 hours" }, { value: "7d", label: "Last 7 days" }, { value: "30d", label: "Last 30 days" },
          { value: "custom", label: "Custom range" },
        ]} />
        {range === "custom" && (
          <>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              From
              <input type="datetime-local" value={localDateTime(customFrom)}
                onChange={(event) => {
                  const next = new URLSearchParams(params);
                  const value = event.target.value ? new Date(event.target.value).toISOString() : "";
                  if (value) next.set("from", value);
                  else next.delete("from");
                  setParams(next, { replace: true });
                }}
                className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground" />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              To
              <input type="datetime-local" value={localDateTime(customTo)}
                onChange={(event) => {
                  const next = new URLSearchParams(params);
                  const value = event.target.value ? new Date(event.target.value).toISOString() : "";
                  if (value) next.set("to", value);
                  else next.delete("to");
                  setParams(next, { replace: true });
                }}
                className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground" />
            </label>
          </>
        )}
      </div>
      {invalidCustomRange && <p className="mb-4 text-sm text-destructive" role="alert">The start time must be before the end time.</p>}
      {q.isLoading && <Loading />}
      {q.error && <ErrorBox error={q.error} />}
      {q.data && items.length === 0 && (
        <EmptyState title="No requests to show" body="Adjust the filters, load demo data, or send a request through the proxy." action={<LoadDemoButton />} />
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm" data-testid="logs-table">
            <thead className="sticky top-0 border-b border-border bg-card text-left text-xs text-muted-foreground">
              <tr>{["Time", "Provider", "Request", "Status", "Latency", "Size", "Tokens", "Cost", "Flags"].map((heading) => <th key={heading} className="px-4 py-2 font-medium">{heading}</th>)}</tr>
            </thead>
            <tbody>
              {items.map((log) => (
                <Fragment key={log.id}>
                  <tr
                    tabIndex={0}
                    className={cn("cursor-pointer border-b border-border/60 hover:bg-accent/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary", openId === log.id && "bg-accent/40")}
                    onClick={() => setOpenId(openId === log.id ? null : log.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setOpenId(openId === log.id ? null : log.id);
                      }
                    }}
                    data-testid="log-row"
                  >
                    <td title={new Date(log.occurred_at).toISOString()} className="whitespace-nowrap px-4 py-2 text-xs text-muted-foreground">{formatTime(log.occurred_at)}</td>
                    <td className="px-4 py-2">{log.provider}</td>
                    <td className="max-w-[280px] truncate px-4 py-2 font-mono text-xs">{log.method} {log.endpoint}</td>
                    <td className={cn("px-4 py-2 font-mono", statusColor(log.status))}>{log.status}</td>
                    <td className="px-4 py-2 font-mono text-xs">{log.latency_ms != null ? `${Math.round(log.latency_ms)} ms` : "—"}</td>
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-xs">{formatBytes(log.req_size ?? 0)} / {formatBytes(log.resp_size ?? 0)}</td>
                    <td className="px-4 py-2 font-mono text-xs">
                      {formatInt((log.prompt_tokens ?? 0) + (log.completion_tokens ?? 0))}
                      {log.tokens_estimated && <span title="Estimated tokens, not reported by the provider"> ~</span>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-xs" title={log.cost_basis === "modelled" ? "Modelled cost" : undefined}>
                      {log.cost_basis === "modelled" ? "~" : ""}{money(log.cost_usd)}
                    </td>
                    <td className="space-x-1 whitespace-nowrap px-4 py-2">
                      {log.is_demo ? <Pill>demo</Pill> : <Pill className="border-primary/40 text-primary">live</Pill>}
                      {log.stream && <Pill>stream</Pill>}
                      {log.flagged_by.length > 0 && <Pill className="border-amber-500/40 text-amber-700 dark:text-amber-300">flagged</Pill>}
                    </td>
                  </tr>
                  {openId === log.id && <tr><td colSpan={9} className="p-0"><Detail log={log} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
