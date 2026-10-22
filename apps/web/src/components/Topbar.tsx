import { Loader2, Moon, Sun, Database, Wifi } from "lucide-react";
import { Button } from "./ui/button";
import { useApp } from "../context/AppContext";
import { useOverview, useLoadSynthetic } from "../hooks/queries";
import { Currency } from "../lib/api";
import { useSaveSettings } from "../hooks/queries";
import { cn } from "../lib/utils";

const CurrencyToggle = () => {
  const { settings, money } = useApp();
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

const ThemeToggle = () => {
  const { theme, setTheme } = useApp();
  return (
    <button
      type="button"
      data-testid="theme-toggle-button"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label="Toggle theme"
      className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
};

const ProxyStatus = () => {
  const { data } = useOverview();
  const hasData = data?.has_data;
  return (
    <div
      data-testid="topbar-proxy-status"
      className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-xs"
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-savings opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-savings" />
      </span>
      <span className="hidden text-muted-foreground sm:inline">Proxy online</span>
      <span className="hidden font-mono text-muted-foreground sm:inline">:8000</span>
      {hasData === false && <span className="hidden font-mono text-muted-foreground md:inline">· listening</span>}
    </div>
  );
};

export const Topbar = () => {
  const load = useLoadSynthetic();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-border bg-background/80 px-6 backdrop-blur-md lg:px-8">
      <ProxyStatus />
      <div className="flex items-center gap-2.5">
        <Button
          size="sm"
          variant="outline"
          data-testid="topbar-load-synthetic-button"
          onClick={() => load.mutate(42)}
          disabled={load.isPending}
          className="h-8 gap-1.5 text-xs"
        >
          {load.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
          {load.isPending ? "Loading…" : "Load demo data"}
        </Button>
        <CurrencyToggle />
        <ThemeToggle />
      </div>
    </header>
  );
};
