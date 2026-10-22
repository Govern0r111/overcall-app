import { Database, Loader2, ArrowRight, ShieldCheck, TrendingDown, Zap } from "lucide-react";
import { Button } from "./ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { CopyField } from "./CopyField";
import { useLoadSynthetic } from "../hooks/queries";
import { PROXY_URLS } from "../lib/api";

const SNIPPETS = {
  openai: `from openai import OpenAI\n\nclient = OpenAI(base_url="${PROXY_URLS.openai}")`,
  stripe: `import stripe\n\nstripe.api_key = "sk_test_..."\nstripe.api_base = "${PROXY_URLS.stripe}"`,
};

const FEATURES = [
  { icon: ShieldCheck, title: "Detect waste", desc: "7 rules across 3 tiers flag duplicate calls, retry storms, token bloat and more." },
  { icon: TrendingDown, title: "Quantify savings", desc: "Every issue shows projected monthly savings in your currency." },
  { icon: Zap, title: "Zero-code proxy", desc: "Point your SDK at the proxy URL — nothing else changes in your app." },
];

const Step = ({ n, title, children }: { n: number; title: string; children?: React.ReactNode }) => (
  <li className="grid grid-cols-[28px_1fr] gap-3">
    <span className="flex h-6 w-6 items-center justify-center rounded-full border border-primary/30 bg-primary/[0.06] font-mono text-xs font-medium text-primary">{n}</span>
    <div className="min-w-0 space-y-3">
      <p className="pt-0.5 text-sm font-medium">{title}</p>
      {children}
    </div>
  </li>
);

export const EmptyState = () => {
  const load = useLoadSynthetic();
  return (
    <section data-testid="empty-state" className="max-w-3xl rounded-lg border border-border bg-card p-8 lg:p-10">
      <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-lg border border-primary/20 bg-primary/[0.06]">
        <ShieldCheck className="h-6 w-6 text-primary" strokeWidth={1.5} />
      </div>
      <h2 className="text-2xl font-semibold tracking-tight">Nothing to show yet</h2>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
        Once requests flow through Overcall, this page shows how much you could save each month, a daily cost trend,
        and the most expensive wasteful patterns — each with a plain-language fix.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {FEATURES.map((f) => {
          const Icon = f.icon;
          return (
            <div key={f.title} className="rounded-lg border border-border bg-background p-4">
              <Icon className="h-5 w-5 text-primary" strokeWidth={1.5} />
              <p className="mt-3 text-sm font-medium">{f.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{f.desc}</p>
            </div>
          );
        })}
      </div>
      <Tabs defaultValue="openai" className="mt-8">
        <ol className="space-y-7">
          <Step n={1} title="Copy your proxy URL">
            <TabsList data-testid="empty-state-provider-tabs">
              <TabsTrigger value="openai" data-testid="empty-state-tab-openai">OpenAI</TabsTrigger>
              <TabsTrigger value="stripe" data-testid="empty-state-tab-stripe">Stripe (test mode)</TabsTrigger>
            </TabsList>
            {(["openai", "stripe"] as const).map((p) => (
              <TabsContent key={p} value={p} className="mt-0 space-y-3">
                <CopyField value={PROXY_URLS[p]} testId={p === "openai" ? "copy-proxy-url-button" : "copy-stripe-proxy-url-button"} />
                <pre className="overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-xs leading-relaxed">{SNIPPETS[p]}</pre>
              </TabsContent>
            ))}
          </Step>
          <Step n={2} title="Use it as your SDK's base URL, then make a request as usual" />
          <Step n={3} title="Come back here — requests appear within about 15 seconds" />
        </ol>
      </Tabs>
      <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-divider pt-6">
        <p className="max-w-md text-sm text-muted-foreground">
          No traffic handy? Load a realistic 7-day demo dataset with known waste patterns.
        </p>
        <Button data-testid="load-synthetic-data-button" onClick={() => load.mutate(42)} disabled={load.isPending} className="gap-2">
          {load.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
          {load.isPending ? "Loading demo data…" : "Load synthetic data"}
          {!load.isPending && <ArrowRight className="h-4 w-4" />}
        </Button>
      </div>
    </section>
  );
};
