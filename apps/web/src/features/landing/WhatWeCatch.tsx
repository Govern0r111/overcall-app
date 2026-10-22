import { Badge } from "../../components/ui/LandingBadge";

const rules = [
  { name: "Duplicate calls", detail: "Finds the same request being sent more than once." },
  { name: "Missing cache", detail: "Spots repeated reads that could reuse a recent result." },
  { name: "Retry storms", detail: "Flags fast retries after a failed request." },
  { name: "Oversized payloads", detail: "Highlights requests that send more data than needed." },
  { name: "Unbatched calls", detail: "Finds groups of small calls that could be sent together." },
  { name: "Token bloat", detail: "Spots repeated chat context that may be using extra tokens." },
  { name: "Model overuse", detail: "Finds simple tasks sent to a more costly model." },
];

export function WhatWeCatch() {
  return (
    <section className="section catch-section" aria-labelledby="catch-title">
      <div className="container catch-layout">
        <div className="section-heading">
          <p className="eyebrow">What it catches</p>
          <h2 id="catch-title">Plain-language fixes, not mystery alerts.</h2>
          <p className="section-intro">
            Every finding explains what happened, why it matters and what you can try next.
          </p>
        </div>
        <ul className="rule-list">
          {rules.map((rule, index) => (
            <li className="rule-item" key={rule.name}>
              <span className="rule-item__number">{String(index + 1).padStart(2, "0")}</span>
              <span className="rule-item__copy">
                <strong>{rule.name}</strong>
                <small>{rule.detail}</small>
              </span>
              {index > 4 ? <Badge className="badge--experimental">Experimental</Badge> : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
