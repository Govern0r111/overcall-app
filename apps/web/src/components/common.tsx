import { ReactNode } from "react";
import { Database, Loader2 } from "lucide-react";
import { Button } from "./ui/button";
import { useLoadDemo, useMe } from "../hooks/queries";
import { Severity } from "../lib/api";
import { cn } from "../lib/utils";

const SEV: Record<Severity, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

export const Pill = ({ children, className }: { children: ReactNode; className?: string }) => (
  <span className={cn("inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground", className)}>
    {children}
  </span>
);

export const SeverityBadge = ({ severity }: { severity: Severity }) => (
  <Pill className={SEV[severity]}>{severity}</Pill>
);

export const ErrorBox = ({ error }: { error: unknown }) => (
  <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm">
    {error instanceof Error ? error.message : "Something went wrong."}
  </p>
);

export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <p role="status" className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
    <Loader2 className="h-4 w-4 animate-spin" /> {label}
  </p>
);

export const LoadDemoButton = ({ label = "Load demo data" }: { label?: string }) => {
  const load = useLoadDemo();
  return (
    <Button onClick={() => load.mutate()} disabled={load.isPending} data-testid="load-demo-button" className="gap-2">
      {load.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
      {load.isPending ? "Loading…" : label}
    </Button>
  );
};

export const EmptyState = ({ title, body, action }: { title: string; body: string; action?: ReactNode }) => (
  <div className="rounded-lg border border-dashed border-border p-10 text-center" data-testid="empty-state">
    <h2 className="text-lg font-semibold">{title}</h2>
    <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{body}</p>
    {action && <div className="mt-6 flex justify-center">{action}</div>}
  </div>
);

export const DemoBanner = () => {
  const { data } = useMe();
  if (!data?.is_demo_data) return null;
  return (
    <p data-testid="demo-banner" className="mb-6 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm">
      You are looking at <strong>demo data</strong>. Nothing here came from your real traffic. Remove it in Settings.
    </p>
  );
};

export const Select = ({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) => (
  <label className="flex flex-col gap-1 text-xs text-muted-foreground">
    {label}
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  </label>
);
