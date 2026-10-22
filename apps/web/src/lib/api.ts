import axios from "axios";
import { supabase } from "./supabase";
import { env } from "./env";

export const BACKEND_URL = env.backendUrl;
export const api = axios.create({ baseURL: `${BACKEND_URL}/api` });
api.interceptors.request.use(async (config) => {
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    if (data.session?.access_token) {
      config.headers.Authorization = `Bearer ${data.session.access_token}`;
    }
  }
  return config;
});

export const PROXY_URLS = {
  openai: `${BACKEND_URL}/api/proxy/openai/v1`,
  stripe: `${BACKEND_URL}/api/proxy/stripe`,
};

export type Severity = "critical" | "warning" | "info";
export type Currency = "INR" | "USD";

export interface SampleRequest {
  id: string;
  timestamp: string;
  method: string;
  endpoint: string;
  status: number;
  latency_ms: number;
  req_size: number;
  resp_size: number;
  req_hash: string;
  cost_usd: number;
  model?: string | null;
  caller?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  provider: string;
  endpoint: string;
  status: number;
  latency_ms: number;
  req_size: number;
  resp_size: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  flagged_by: string[];
  issue_ids?: string[];
}

export interface Issue {
  id: string;
  rule_id: string;
  rule_name: string;
  issue_type: string;
  tier: number;
  experimental: boolean;
  provider: string;
  endpoint: string;
  severity: Severity;
  title: string;
  summary: string;
  explanation: string;
  suggested_fix: string;
  affected_requests: string[];
  affected_count: number;
  estimated_savings_usd: number;
  projected_monthly_usd: number;
  confidence: number;
  sample_requests: SampleRequest[];
  detected_at: string;
}

export interface TrendPoint {
  date: string;
  cost_usd: number;
  waste_usd: number;
}

export interface Overview {
  has_data: boolean;
  request_count: number;
  flagged_request_count: number;
  window_days: number;
  total_cost_usd: number;
  projected_monthly_cost_usd: number;
  window_savings_usd: number;
  projected_monthly_usd: number;
  waste_pct: number;
  experimental_projected_monthly_usd: number;
  issue_counts: Record<Severity, number>;
  sources: Record<string, number>;
  trend: TrendPoint[];
  top_issues: Issue[];
  ran_at: string;
}

export interface Windows {
  short_window_s: number;
  long_window_s: number;
  retry_min_backoff_ms: number;
  retry_min_attempts: number;
  oversized_bytes: number;
  unbatched_min_calls: number;
  unbatched_window_s: number;
  token_bloat_min_repeats: number;
  token_bloat_min_prompt_tokens: number;
  model_overuse_max_prompt_tokens: number;
  model_overuse_max_completion_tokens: number;
}

export interface Settings {
  rules: Record<string, boolean>;
  experimental_enabled: boolean;
  windows: Windows;
  currency: Currency;
  usd_inr_rate: number;
  openai_upstream: "mock" | "real";
}

export interface Rule {
  id: string;
  name: string;
  tier: number;
  description: string;
}

export interface Provider {
  id: "openai" | "stripe" | "aws";
  status: "receiving_traffic" | "synthetic_only" | "waiting" | "stubbed";
  counts: { proxy: number; synthetic: number };
  last_proxy_request_at: string | null;
  issue_count: number;
  pricing: any;
  upstream_mode: string | null;
}

export interface RuleAccuracy {
  rule_id: string;
  rule_name: string;
  tier: number;
  ground_truth: number;
  flagged: number;
  true_positives: number;
  precision: number;
  recall: number;
}

export interface Evaluation {
  has_data: boolean;
  requests?: number;
  using_default_windows?: boolean;
  rules: RuleAccuracy[];
}
