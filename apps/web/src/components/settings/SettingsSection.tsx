import { ReactNode } from "react";
import { cn } from "../../lib/utils";

export const SettingsSection = ({ title, description, children, testId }: { title: string; description?: ReactNode; children: ReactNode; testId: string }) => (
  <section data-testid={testId} className="grid gap-6 rounded-lg border border-border bg-card p-6 lg:grid-cols-[260px_1fr] lg:gap-10">
    <div>
      <h2 className="text-sm font-medium">{title}</h2>
      {description && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{description}</p>}
    </div>
    <div className="min-w-0">{children}</div>
  </section>
);

export const SettingRow = ({ label, help, control, className }: { label: ReactNode; help?: ReactNode; control: ReactNode; className?: string }) => (
  <div className={cn("flex items-start justify-between gap-6 border-b border-divider py-4 first:pt-0 last:border-b-0 last:pb-0", className)}>
    <div className="min-w-0">
      <div className="text-sm">{label}</div>
      {help && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{help}</p>}
    </div>
    <div className="shrink-0">{control}</div>
  </div>
);

export const Segmented = <T extends string>({ value, options, onChange, testIdPrefix }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  testIdPrefix: string;
}) => (
  <div role="radiogroup" data-testid={testIdPrefix} className="inline-flex rounded-md border border-border p-0.5">
    {options.map((o) => (
      <button
        key={o.value}
        type="button"
        role="radio"
        aria-checked={value === o.value}
        data-testid={`${testIdPrefix}-${o.value.toLowerCase()}`}
        onClick={() => onChange(o.value)}
        className={cn(
          "rounded px-3 py-1 text-xs font-medium transition-colors",
          value === o.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
        )}
      >
        {o.label}
      </button>
    ))}
  </div>
);
