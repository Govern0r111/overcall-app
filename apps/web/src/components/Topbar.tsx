import { Loader2, Database, Menu } from "lucide-react";
import { Button } from "./ui/button";
import { useApp } from "../context/AppContext";
import { useLoadDemo, useMe } from "../hooks/queries";
import { Currency } from "../lib/api";
import { useSaveSettings } from "../hooks/queries";
import { cn } from "../lib/utils";
import { ThemeToggle as ThemePreferenceToggle } from "./ThemeToggle";
import { BACKEND_URL } from "../lib/api";

const CurrencyToggle = () => {
  const { settings } = useApp();
  const save = useSaveSettings();
  if (!settings) return null;
  const active = settings.currency;
  const swap = (c: Currency) => save.mutate({ ...settings, currency: c });
  return (
    <div className="flex items-center rounded-md border border-border bg-card p-0.5 text-xs" data-testid="topbar-currency-switch">
      {(["INR", "USD"] as Currency[]).map((c) => (
        <button
          key={c}
          type="button"
          data-testid={`topbar-currency-${c.toLowerCase()}`}
          onClick={() => swap(c)}
          className={cn(
            "rounded px-2.5 py-1 font-mono font-medium transition-colors",
            active === c ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {c === "INR" ? "₹" : "$"}
        </button>
      ))}
    </div>
  );
};

const ProxyStatus = () => {
  const { data, error, isLoading } = useMe();
  const labels: Record<string, string> = {
    no_key: "No ingest key",
    waiting_for_traffic: "Waiting for traffic",
    receiving_traffic: "Receiving traffic",
    demo_only: "Demo data only",
  };
  const status = error ? "API unavailable" : isLoading ? "Checking API" : labels[data?.proxy_status ?? ""] ?? "Proxy status unknown";
  const dotColor = error
    ? "bg-destructive"
    : data?.proxy_status === "receiving_traffic"
      ? "bg-savings"
      : data?.proxy_status === "demo_only"
        ? "bg-amber-500"
        : "bg-muted-foreground";
  const apiPort = new URL(BACKEND_URL).port;
  return (
    <div
      data-testid="topbar-proxy-status"
      className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs"
    >
      <span className={cn("inline-flex h-2 w-2 rounded-full", dotColor)} />
      <span className="hidden text-muted-foreground sm:inline">{status}</span>
      {apiPort && <span className="hidden font-mono text-muted-foreground sm:inline">:{apiPort}</span>}
    </div>
  );
};

export const Topbar = ({ onMenuClick, menuOpen = false }: { onMenuClick?: () => void; menuOpen?: boolean }) => {
  const load = useLoadDemo();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-background/80 px-6 backdrop-blur-md lg:px-8">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary md:hidden"
        >
          <Menu className="h-4 w-4" />
        </button>
        <ProxyStatus />
      </div>
      <div className="flex items-center gap-2.5">
        <Button
          size="sm"
          variant="outline"
          data-testid="topbar-load-synthetic-button"
          onClick={() => load.mutate()}
          disabled={load.isPending}
          className="h-8 gap-1.5 text-xs"
        >
          {load.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
          {load.isPending ? "Loading…" : "Load demo data"}
        </Button>
        <CurrencyToggle />
        <ThemePreferenceToggle />
      </div>
    </header>
  );
};
