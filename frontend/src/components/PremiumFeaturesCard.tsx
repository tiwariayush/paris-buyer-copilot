"use client";

import { Sparkles } from "lucide-react";
import { Card, CardLabel, CardTitle } from "@/components/Card";
import type { PremiumFeatures } from "@/lib/types";

export function PremiumFeaturesCard({
  premium,
  adjustments,
}: {
  premium: PremiumFeatures;
  adjustments?: Record<string, number>;
}) {
  const applied = Object.entries(adjustments || {}).filter(
    ([k]) => k.startsWith("view_") || k.startsWith("light_"),
  );

  return (
    <Card>
      <CardLabel className="flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" />
        Atouts détectés
      </CardLabel>
      <CardTitle className="mt-1 text-base font-medium">
        Vue & luminosité pris en compte
      </CardTitle>
      <ul className="mt-3 space-y-1.5 text-sm text-[var(--foreground)]">
        {premium.highlights_fr.map((h) => (
          <li key={h}>· {h}</li>
        ))}
      </ul>
      {applied.length > 0 && (
        <p className="mt-3 text-xs text-[var(--muted)]">
          Ajustements estimation :{" "}
          {applied
            .map(([k, v]) => `${k.replace(/_/g, " ")} ×${v.toFixed(2)}`)
            .join(" · ")}
        </p>
      )}
      {premium.sources.length > 0 && (
        <p className="mt-1 text-xs text-[var(--muted)]">
          Sources : {premium.sources.join(", ")}
        </p>
      )}
    </Card>
  );
}
