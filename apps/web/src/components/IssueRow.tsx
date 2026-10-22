import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../lib/utils";
import type { Issue } from "../lib/api";
import { PROVIDER_NAME, formatInt } from "../lib/format";
import { useApp } from "../context/AppContext";
import { SeverityBadge, TierBadge } from "./Badges";
import { IssueDetail } from "./IssueDetail";

const SEVERITY_BAR: Record<string, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  info: "bg-muted-foreground",
};

export const IssueRow = ({ issue, index }: { issue: Issue; index: number }) => {
  const [open, setOpen] = useState(false);
  const { money } = useApp();
  return (
    <li data-testid={`issue-row-${index}`} className="border-b border-divider last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        data-testid={`issue-row-expand-button-${index}`}
        className="group flex w-full items-start gap-4 px-5 py-5 text-left transition-colors hover:bg-accent/50"
      >
        <span className={cn("mt-2 h-8 w-0.5 shrink-0 rounded-full", SEVERITY_BAR[issue.severity])} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={issue.severity} testId={`issue-severity-${index}`} />
            <span className="text-sm font-medium">{issue.title}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{issue.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground">
            <span>{PROVIDER_NAME[issue.provider]}</span>
            <span className="text-divider">·</span>
            <span className="font-mono">{issue.endpoint}</span>
            <span className="text-divider">·</span>
            <span className="font-mono">{formatInt(issue.affected_count)} requests</span>
            <TierBadge tier={issue.tier} confidence={issue.experimental ? issue.confidence : undefined} testId={`issue-tier-${index}`} />
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div data-testid={`issue-savings-${index}`} className="font-mono text-sm font-medium text-savings">
            {money(issue.projected_monthly_usd)}
            <span className="text-muted-foreground">/mo</span>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">projected</div>
        </div>
        <ChevronDown className={cn("mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:text-foreground", open && "rotate-180")} />
      </button>
      <div className={cn("grid transition-[grid-template-rows] duration-200 ease-out", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden">{open && <IssueDetail issue={issue} index={index} />}</div>
      </div>
    </li>
  );
};
