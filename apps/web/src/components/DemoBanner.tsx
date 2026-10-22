import { Link } from "react-router-dom";
import { Database, ArrowRight } from "lucide-react";

export const DemoBanner = () => (
  <div
    data-testid="demo-data-banner"
    className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-5 py-3 text-sm"
  >
    <span className="flex items-center gap-2.5 text-muted-foreground">
      <span className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-accent">
        <Database className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
      </span>
      You're looking at synthetic demo data. Point your app at the proxy to see your own traffic.
    </span>
    <Link
      to="/providers"
      data-testid="demo-banner-proxy-link"
      className="flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
    >
      Get proxy URL
      <ArrowRight className="h-3.5 w-3.5" />
    </Link>
  </div>
);
