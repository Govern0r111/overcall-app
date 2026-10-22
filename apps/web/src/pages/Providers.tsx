import { FormEvent, useState } from "react";
import { CopyField, copyToClipboard } from "../components/CopyField";
import { Card, PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { DemoBanner, ErrorBox, Loading, Pill } from "../components/common";
import { useApp } from "../context/AppContext";
import { useIngestKeys, useProviders } from "../hooks/queries";
import { ApiError, api, type CreatedIngestKey, type IngestKey, type Provider } from "../lib/api";
import { timeAgo } from "../lib/format";
import { cn } from "../lib/utils";
import { useQueryClient } from "@tanstack/react-query";

const STATUS: Record<string, string> = {
  live: "receiving traffic",
  receiving_traffic: "receiving traffic",
  waiting_for_traffic: "waiting for traffic",
  no_key: "no ingest key",
  demo_only: "demo traffic only",
  coming_soon: "coming soon",
};

const Snippets = ({ p }: { p: Provider }) => {
  const [tab, setTab] = useState(p.snippets[0]?.id);
  const cur = p.snippets.find((s) => s.id === tab);
  return (
    <div className="mt-4">
      <div className="mb-2 flex gap-1" role="tablist">
        {p.snippets.map((s) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={tab === s.id}
            aria-controls={`snippet-panel-${p.id}`}
            id={`snippet-tab-${p.id}-${s.id}`}
            onClick={() => setTab(s.id)}
            type="button"
            className={cn("rounded-md px-3 py-1 text-xs", tab === s.id ? "bg-secondary font-medium" : "text-muted-foreground hover:text-foreground")}
          >
            {s.label}
          </button>
        ))}
      </div>
      {cur && <pre role="tabpanel" tabIndex={0} id={`snippet-panel-${p.id}`} aria-labelledby={`snippet-tab-${p.id}-${cur.id}`} className="overflow-x-auto rounded-md border border-border bg-background p-3 font-mono text-xs leading-5">{cur.code}</pre>}
    </div>
  );
};

const IngestKeyManager = () => {
  const queryClient = useQueryClient();
  const keys = useIngestKeys();
  const [name, setName] = useState("");
  const [createdKey, setCreatedKey] = useState<CreatedIngestKey | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<IngestKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const activeKeys = keys.data?.items.filter((key) => !key.revoked_at) ?? [];
  const apiPending = keys.error instanceof ApiError && keys.error.code === "not_found";

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const safeName = name.trim();
    if (!safeName || safeName.length > 80) {
      setError("Give the key a name between 1 and 80 characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await api.post<CreatedIngestKey>("/v1/ingest-keys", { name: safeName });
      setCreatedKey(response.data);
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["ingest-keys"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the key.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!revokeTarget) return;
    setBusy(true);
    setError("");
    try {
      await api.delete(`/v1/ingest-keys/${encodeURIComponent(revokeTarget.id)}`);
      setRevokeTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["ingest-keys"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not revoke the key.");
    } finally {
      setBusy(false);
    }
  };

  const copyCreatedKey = async () => {
    if (!createdKey) return;
    try {
      await copyToClipboard(createdKey.key);
      setCopied(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Copy failed. Select the key and copy it manually.");
    }
  };

  return (
    <>
      <Card className="mb-6 p-6">
        <h2 className="text-lg font-semibold">Ingest keys</h2>
        <p className="mt-1 text-sm text-muted-foreground">Use a key in your application to authenticate requests sent through the Overcall proxy. A new key is shown only once.</p>
        {keys.isLoading && <Loading />}
        {keys.error && (
          <p role="alert" className="mt-4 rounded-md border border-border bg-background px-4 py-3 text-sm text-muted-foreground">
            {apiPending
              ? "Key management endpoints are not available on this backend yet. The create, list and revoke interface is ready for the B10 API."
              : keys.error instanceof Error ? keys.error.message : "Could not load ingest keys."}
          </p>
        )}
        {!keys.error && (
          <>
            {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
            <form onSubmit={create} className="mt-4 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted-foreground">
                Key name
                <input value={name} maxLength={80} onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. staging app" className="h-9 w-64 rounded-md border border-input bg-background px-3 text-sm" />
              </label>
              <Button type="submit" disabled={busy || keys.isLoading || activeKeys.length >= 5}>
                {busy ? "Working…" : "Create ingest key"}
              </Button>
            </form>
            {activeKeys.length >= 5 && <p className="mt-2 text-xs text-muted-foreground">You have reached the limit of five active keys.</p>}
            <ul className="mt-5 divide-y divide-border">
              {keys.data?.items.map((key) => (
                <li key={key.id} className={cn("flex flex-wrap items-center justify-between gap-3 py-3", key.revoked_at && "opacity-55")}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{key.name} {key.revoked_at && <Pill>revoked</Pill>}</p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">
                      {key.prefix} · created {timeAgo(key.created_at)} · last used {timeAgo(key.last_used_at)}
                    </p>
                  </div>
                  {!key.revoked_at && (
                    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => setRevokeTarget(key)}>Revoke</Button>
                  )}
                </li>
              ))}
            </ul>
            {keys.data?.items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">No ingest keys yet. Create one to send proxy traffic.</p>}
          </>
        )}
      </Card>

      {(createdKey || revokeTarget) && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
          <section role="alertdialog" aria-modal="true" aria-labelledby="key-dialog-title" className="w-full max-w-lg rounded-lg border border-border bg-card p-6">
            {createdKey ? (
              <>
                <h2 id="key-dialog-title" className="text-lg font-semibold">Save your ingest key</h2>
                <p className="mt-2 text-sm text-muted-foreground">This secret will not be shown again. Copy it and store it somewhere safe before closing this dialog.</p>
                <div className="mt-4 flex gap-2">
                  <input readOnly value={createdKey.key} aria-label="New ingest key" className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 font-mono text-xs" />
                  <Button type="button" variant="outline" onClick={copyCreatedKey}>{copied ? "Copied" : "Copy key"}</Button>
                </div>
                {error && <p className="mt-2 text-sm text-destructive" role="alert">{error}</p>}
                <div className="mt-6 flex justify-end">
                  <Button type="button" onClick={() => { setCreatedKey(null); setCopied(false); setError(""); }}>I have saved it</Button>
                </div>
              </>
            ) : (
              <>
                <h2 id="key-dialog-title" className="text-lg font-semibold">Revoke {revokeTarget?.name}?</h2>
                <p className="mt-2 text-sm text-muted-foreground">Applications using this key will no longer be able to send requests.</p>
                <div className="mt-6 flex justify-end gap-3">
                  <Button type="button" variant="outline" onClick={() => setRevokeTarget(null)}>Cancel</Button>
                  <Button type="button" variant="destructive" disabled={busy} onClick={revoke}>Revoke key</Button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
};

const ProviderCard = ({ p }: { p: Provider }) => {
  const { money } = useApp();
  return (
    <Card className="p-6" testId={`provider-${p.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{p.name}</h2>
        <div className="flex gap-2">
          <Pill>{STATUS[p.status] ?? p.status}</Pill>
          {p.upstream_mode && <Pill>upstream: {p.upstream_mode}</Pill>}
        </div>
      </div>
      {p.notes && <p className="mt-2 text-sm text-muted-foreground">{p.id === "stripe" ? "Test keys only. Stripe does not bill per call; savings are modelled overhead." : p.notes}</p>}
      {p.proxy_base_url && (
        <>
          <p className="mb-1 mt-4 text-xs text-muted-foreground">Proxy base URL</p>
          <CopyField value={p.proxy_base_url} testId={`copy-${p.id}-url`} />
          <p className="mt-4 text-sm text-muted-foreground">
            Live requests: <span className="font-mono text-foreground">{p.traffic.proxy}</span> · demo requests:{" "}
            <span className="font-mono text-foreground">{p.traffic.demo}</span> · last live request{" "}
            {timeAgo(p.traffic.last_request_at)}
          </p>
          <Snippets p={p} />
        </>
      )}
      {p.pricing && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-medium">Pricing used for cost estimates (version {p.pricing.version})</summary>
          <table className="mt-2 w-full text-xs">
            <tbody>
              {p.pricing.rows.map((r) => (
                <tr key={r.label} className="border-t border-border/60">
                  <td className="py-1.5">{r.label}</td>
                  <td className="py-1.5 text-right font-mono">
                    {r.usd_per_1m != null ? `${money(r.usd_per_1m)} / 1M tokens` : `${money(r.usd_per_request ?? 0)} / request`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <a href={p.pricing.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-primary hover:underline">
            Pricing source
          </a>
        </details>
      )}
    </Card>
  );
};

export default function Providers() {
  const { data, isLoading, error } = useProviders();
  return (
    <>
      <PageHeader title="Providers" description="Use a proxy URL to send requests through Overcall. Local mode uses a safe mock upstream." />
      <DemoBanner />
      <Card className="mb-6 p-4 text-sm text-muted-foreground">
        Snippets use <code className="font-mono">YOUR_OVERCALL_KEY</code>. The proxy forwards requests to a built-in mock in this local setup; no real provider is called.
      </Card>
      <IngestKeyManager />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} />}
      <div className="space-y-6">{data?.map((p) => <ProviderCard key={p.id} p={p} />)}</div>
    </>
  );
}
