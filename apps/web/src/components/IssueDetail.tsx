import type { Issue, SampleRequest } from "../lib/api";
import { formatBytes, formatInt, formatTime } from "../lib/format";
import { useApp } from "../context/AppContext";

const Meta = ({ label, value, testId }: { label: string; value: React.ReactNode; testId?: string }) => (
  <div>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd data-testid={testId} className="mt-1 font-mono text-xs">{value}</dd>
  </div>
);

const SampleTable = ({ rows }: { rows: SampleRequest[] }) => {
  const { money } = useApp();
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[720px] font-mono text-xs">
        <thead className="text-left text-muted-foreground">
          <tr className="border-b border-divider">
            {["Time", "Method", "Endpoint", "Status", "Latency", "Size", "Payload hash", "Cost"].map((h) => (
              <th key={h} className="px-3 py-2 font-normal">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-divider last:border-b-0">
              <td className="whitespace-nowrap px-3 py-2">{formatTime(r.timestamp)}</td>
              <td className="px-3 py-2">{r.method}</td>
              <td className="px-3 py-2">{r.endpoint}</td>
              <td className="px-3 py-2">{r.status}</td>
              <td className="px-3 py-2">{Math.round(r.latency_ms)} ms</td>
              <td className="px-3 py-2">{formatBytes(Math.max(r.req_size, r.resp_size))}</td>
              <td className="px-3 py-2 text-muted-foreground">{r.req_hash}</td>
              <td className="px-3 py-2">{money(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export const IssueDetail = ({ issue, index }: { issue: Issue; index: number }) => {
  const { money } = useApp();
  return (
    <div data-testid={`issue-detail-${index}`} className="space-y-6 border-t border-divider bg-background/60 px-5 py-6">
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <h4 className="mb-2 text-xs text-muted-foreground">What we detected</h4>
          <p className="text-sm leading-relaxed">{issue.explanation}</p>
        </div>
        <div>
          <h4 className="mb-2 text-xs text-muted-foreground">Suggested fix</h4>
          <p data-testid="issue-suggested-fix" className="text-sm leading-relaxed">{issue.suggested_fix}</p>
        </div>
      </div>
      <dl className="flex flex-wrap gap-x-10 gap-y-4">
        <Meta label="Rule" value={issue.rule_id} />
        <Meta label="Affected requests" value={formatInt(issue.affected_count)} />
        <Meta label="Waste in observed window" value={money(issue.estimated_savings_usd)} />
        <Meta label="Projected monthly" value={money(issue.projected_monthly_usd)} />
        {issue.experimental && <Meta label="Confidence" value={`${Math.round(issue.confidence * 100)}%`} testId="issue-confidence" />}
      </dl>
      <div>
        <h4 className="mb-2 text-xs text-muted-foreground">Sample requests ({issue.sample_requests.length} of {formatInt(issue.affected_count)})</h4>
        <SampleTable rows={issue.sample_requests} />
      </div>
    </div>
  );
};
