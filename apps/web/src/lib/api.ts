import axios from "axios";
import { env } from "./env";
import { authClient } from "../auth/authClient";

export const BACKEND_URL = env.backendUrl;
export const api = axios.create({ baseURL: BACKEND_URL });
api.interceptors.request.use(async (config) => {
  const token = await authClient.getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export class ApiError extends Error {
  code: string;
  requestId?: string;
  fields?: { path: string; message: string }[];
  constructor(code: string, message: string, requestId?: string, fields?: { path: string; message: string }[]) {
    super(message);
    this.code = code;
    this.requestId = requestId;
    this.fields = fields;
  }
}

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const e = err?.response?.data?.error;
    if (e) return Promise.reject(new ApiError(e.code, e.message, e.request_id, e.details?.fields));
    if (err instanceof Error && err.message.includes("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY")) {
      return Promise.reject(new ApiError("auth_configuration_error", err.message));
    }
    return Promise.reject(
      new ApiError("network_error", `Could not reach the Overcall API at ${BACKEND_URL}. Is the dev server running?`),
    );
  },
);

export type Severity = "critical" | "warning" | "info";
export type Currency = "INR" | "USD";

export interface Issue {
  id: string;
  rule_id: string;
  rule_name: string;
  tier: number;
  experimental: boolean;
  provider: string;
  endpoint: string;
  severity: Severity;
  impact_kind: "spend" | "reliability";
  title: string;
  summary: string;
  explanation: string;
  suggested_fix: string;
  affected_count: number;
  window_savings_usd: number;
  projected_monthly_usd: number;
  confidence: number | null;
  is_demo_data: boolean;
  detected_at: string;
}

export interface SampleRequest {
  request_id: string;
  occurred_at: string;
  req_hash: string | null;
  req_size: number | null;
  resp_size: number | null;
  status: number;
  cost_usd: number;
}

export interface IssueDetail extends Issue {
  sample_requests?: SampleRequest[];
}

export interface FlaggedBy {
  issue_id: string;
  rule_id: string;
  rule_name?: string;
}

export interface LogEntry {
  id: string;
  occurred_at: string;
  provider: string;
  method: string;
  endpoint: string;
  status: number;
  latency_ms: number | null;
  ttfb_ms: number | null;
  req_size: number | null;
  resp_size: number | null;
  req_hash: string | null;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  tokens_estimated: boolean;
  stream: boolean;
  cost_usd: number;
  cost_basis: string;
  pricing_version: string | null;
  caller: string | null;
  has_idempotency_key: boolean;
  error_code: string | null;
  origin: string;
  is_demo: boolean;
  flagged_by: FlaggedBy[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface TrendPoint {
  date: string;
  spend_usd: number;
  waste_usd: number;
}

export interface Overview {
  has_data: boolean;
  is_demo_data: boolean;
  generated_at: string | null;
  window: { start: string | null; end: string | null; days: number; low_confidence_projection: boolean };
  request_count: number;
  flagged_request_count: number;
  total_spend_usd: number;
  spend_savings: { window_usd: number; projected_monthly_usd: number; percent_of_spend: number };
  experimental_spend_savings: { projected_monthly_usd: number };
  reliability_findings: { count: number; modelled_overhead_monthly_usd: number };
  severity_breakdown: Record<Severity, number>;
  by_provider: { provider: string; spend_usd: number; issue_count: number }[];
  trend: TrendPoint[];
  top_issues: Issue[];
}

export interface Me {
  id: string;
  email: string | null;
  proxy_status: string;
  last_request_at: string | null;
  issue_count: number;
  is_demo_data: boolean;
  has_data: boolean;
  real_upstream_available: boolean;
}

export interface Settings {
  currency: Currency;
  usd_inr_rate: number;
  rules_enabled: Record<string, boolean>;
  tier3_enabled: boolean;
  thresholds: Record<string, number>;
  upstream_mode: "mock" | "test" | "real";
  confirm_real_upstream: boolean;
  retention_days: number;
  updated_at: string;
}

export interface RuleInfo {
  id: string;
  name: string;
  tier: number;
  description: string;
  default_enabled: boolean;
  threshold_keys: string[];
}

export interface Provider {
  id: string;
  name: string;
  status: string;
  proxy_base_url: string | null;
  snippets: { id: string; label: string; code: string }[];
  traffic: { proxy: number; demo: number; last_request_at: string | null };
  upstream_mode: string | null;
  pricing: {
    version: string;
    effective_from: string;
    source_url: string;
    rows: { label: string; usd_per_1m: number | null; usd_per_request: number | null }[];
  } | null;
  notes: string | null;
}

export interface IngestKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface CreatedIngestKey extends IngestKey {
  key: string;
}

export interface RunSummary {
  run_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  request_count: number;
  issue_counts: Record<Severity, number>;
  duration_ms: number;
}

export interface FacetValue {
  value: string;
  count?: number;
}

export interface LogFacets {
  providers: FacetValue[];
  endpoints: FacetValue[];
  callers: FacetValue[];
  models: FacetValue[];
}

export interface Accuracy {
  datasets: {
    id: string;
    label: string;
    note: string;
    requests: number;
    rules: {
      rule_id: string;
      tier: number;
      positives: number;
      flagged: number;
      true_positives: number;
      precision: number | null;
      recall: number | null;
    }[];
  }[];
}
