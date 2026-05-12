import type { AnalyzeResponse, Listing } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** URL or pasted listing content; backend auto-detects. */
export async function analyze(
  content: string,
  sourceUrl?: string,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, source_url: sourceUrl }),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = b.detail ?? detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export interface StreamCallbacks {
  onListing: (listing: Listing) => void;
  onVerdict: (data: AnalyzeResponse) => void;
  onError: (err: string) => void;
}

/**
 * SSE streaming variant — emits listing data as soon as parsed,
 * then full verdict when the analysis completes.
 */
export async function analyzeStream(
  content: string,
  sourceUrl: string | undefined,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, source_url: sourceUrl }),
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = b.detail ?? detail;
    } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop()!;

    for (const part of parts) {
      let eventType = "";
      let data = "";
      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) eventType = line.slice(7);
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!eventType || !data) continue;

      const parsed = JSON.parse(data);
      if (eventType === "listing") callbacks.onListing(parsed as Listing);
      else if (eventType === "verdict") callbacks.onVerdict(parsed as AnalyzeResponse);
      else if (eventType === "error") callbacks.onError(parsed.detail ?? "Erreur inconnue");
    }
  }
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
