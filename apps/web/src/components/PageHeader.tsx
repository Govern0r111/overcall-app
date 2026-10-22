import { ReactNode } from "react";

interface Props {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export const PageHeader = ({ title, description, actions }: Props) => (
  <header className="mb-10 flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 data-testid="page-title" className="text-2xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p>}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </header>
);

export const Card = ({ children, className = "", testId }: { children: ReactNode; className?: string; testId?: string }) => (
  <section data-testid={testId} className={`rounded-lg border border-border bg-card ${className}`}>{children}</section>
);
