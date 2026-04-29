import type { AnalyzeResponse } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function analyze(url: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export function formatEur(n: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    notation: opts.compact ? "compact" : "standard",
    maximumFractionDigits: opts.compact ? 1 : 0,
  }).format(n);
}

export function formatPct(n: number | null | undefined, signed = true): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = signed && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
