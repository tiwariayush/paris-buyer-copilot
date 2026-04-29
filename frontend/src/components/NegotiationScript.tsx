"use client";

import { useState } from "react";
import { Card, CardLabel, CardTitle } from "./Card";
import type { NegotiationScript as Script } from "@/lib/types";
import { cn } from "@/lib/cn";
import { Copy, Check } from "lucide-react";

const strengthDot: Record<string, string> = {
  weak: "bg-gray-300",
  moderate: "bg-amber-500",
  strong: "bg-emerald-600",
};

export function NegotiationScript({ script }: { script: Script }) {
  const [copied, setCopied] = useState(false);

  async function copyMessage() {
    await navigator.clipboard.writeText(script.opening_message);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Card className="space-y-6">
      <div>
        <CardLabel>Verdict</CardLabel>
        <p className="mt-2 text-base leading-relaxed">{script.verdict}</p>
      </div>

      <div>
        <CardLabel>Leviers de négociation</CardLabel>
        <ol className="mt-3 space-y-3">
          {script.levers.map((l, i) => (
            <li
              key={i}
              className="flex gap-3 rounded-lg border border-[var(--border)] p-3"
            >
              <span
                className={cn("mt-1 h-2 w-2 rounded-full flex-shrink-0", strengthDot[l.strength])}
                title={l.strength}
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{l.title}</span>
                  {l.impact_pct != null ? (
                    <span className="text-xs font-mono text-[var(--muted)]">
                      {l.impact_pct > 0 ? "+" : ""}
                      {l.impact_pct.toFixed(1)}%
                    </span>
                  ) : null}
                </div>
                <div className="text-sm text-[var(--muted)] mt-0.5 leading-relaxed">
                  {l.detail}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <CardLabel>Message d&apos;ouverture</CardLabel>
          <button
            onClick={copyMessage}
            className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-[var(--border)] hover:bg-[var(--accent-soft)] transition-colors"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copié" : "Copier"}
          </button>
        </div>
        <CardTitle className="sr-only">Message d&apos;ouverture</CardTitle>
        <p className="mt-2 text-sm bg-[var(--accent-soft)] rounded-lg p-3 leading-relaxed whitespace-pre-wrap">
          {script.opening_message}
        </p>
      </div>
    </Card>
  );
}
