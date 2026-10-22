import { Card } from "../../components/ui/LandingCard";
import { previewData } from "./previewData";

export function DashboardPreview() {
  return (
    <section aria-labelledby="preview-title" className="preview-section">
      <div className="container">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">A look inside</p>
            <h2 id="preview-title">The next useful step, at a glance.</h2>
          </div>
          <span className="example-label">Example data</span>
        </div>

        <Card className="preview-card">
          <div className="preview-card__header">
            <div>
              <p className="preview-card__title">Overview</p>
              <p className="preview-card__caption">Last 7 days · 12,480 requests analysed</p>
            </div>
            <span className="demo-label"><span aria-hidden="true" /> Demo data</span>
          </div>

          <div className="preview-metrics">
            {previewData.metrics.map(({ label, value, note }) => (
              <div className="preview-metric" key={label}>
                <span>{label}</span>
                <strong className="mono">{value}</strong>
                <small>{note}</small>
              </div>
            ))}
          </div>

          <div className="preview-lower">
            <div className="preview-chart">
              <div className="preview-chart__heading">
                <h3>Spend over time</h3>
                <span>Daily estimate</span>
              </div>
              <svg
                aria-label="Example chart comparing spend and estimated waste over seven days"
                className="preview-chart__svg"
                role="img"
                viewBox="0 0 640 190"
                preserveAspectRatio="none"
              >
                <line x1="0" x2="640" y1="45" y2="45" />
                <line x1="0" x2="640" y1="95" y2="95" />
                <line x1="0" x2="640" y1="145" y2="145" />
                <path className="preview-chart__spend" d="M0 126 C45 112 62 122 98 97 S151 82 190 92 246 57 284 66 341 75 375 53 432 61 468 38 527 58 561 31 607 45 640 21" />
                <path className="preview-chart__waste" d="M0 158 C48 148 62 153 98 138 S152 124 190 133 244 104 284 115 340 121 375 100 430 113 468 90 527 109 561 82 606 97 640 73" />
              </svg>
              <div className="chart-legend">
                <span><i className="chart-legend__spend" /> Spend</span>
                <span><i className="chart-legend__waste" /> Estimated waste</span>
              </div>
            </div>
            <div className="preview-issues">
              <h3>Fix these first</h3>
              {previewData.issues.map((issue) => (
                <div className="preview-issue" key={issue.title}>
                  <span className="preview-issue__dot" aria-hidden="true" />
                  <span>{issue.title}</span>
                  <strong className="mono">{issue.impact}</strong>
                </div>
              ))}
            </div>
          </div>
        </Card>
        <p className="preview-footnote">Savings are estimates. Spend savings and reliability findings are shown separately.</p>
      </div>
    </section>
  );
}
