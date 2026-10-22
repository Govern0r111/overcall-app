import type { Currency } from "./api";

export function formatMoney(usd: number, currency: Currency, rate: number, short = false): string {
  const v = currency === "INR" ? usd * rate : usd;
  const a = Math.abs(v);
  let d = a === 0 ? 0 : a >= 100 ? 0 : a >= 0.01 ? 2 : 4;
  if (short) d = a === 0 || a >= 10 ? 0 : 2;
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);
}

export const formatInt = (n: number) => new Intl.NumberFormat("en-US").format(Math.round(n));

export const formatBytes = (b: number) =>
  b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b >= 1e3 ? `${(b / 1e3).toFixed(1)} KB` : `${b} B`;

export const formatDay = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const PROVIDER_NAME: Record<string, string> = { openai: "OpenAI", stripe: "Stripe", aws: "AWS" };
