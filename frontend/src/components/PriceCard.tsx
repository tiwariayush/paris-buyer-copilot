import { Card, CardLabel } from "./Card";
import { formatEur, formatPct } from "@/lib/api";
import type { Listing, Valuation } from "@/lib/types";
import { cn } from "@/lib/cn";

const tierLabel: Record<string, string> = {
  building: "Même immeuble",
  street: "Même rue",
  iris: "Quartier (rayon 500 m)",
  none: "Pas de comparable",
};

const confidenceLabel: Record<string, string> = {
  low: "faible",
  medium: "moyenne",
  high: "élevée",
};

const confidenceColor: Record<string, string> = {
  low: "text-[var(--warning)]",
  medium: "text-[var(--accent)]",
  high: "text-[var(--positive)]",
};

export function PriceCard({
  listing,
  valuation,
  deltaPct,
  deltaEur,
}: {
  listing: Listing;
  valuation: Valuation;
  deltaPct?: number | null;
  deltaEur?: number | null;
}) {
  const overpriced = (deltaPct ?? 0) > 1.5;
  const underpriced = (deltaPct ?? 0) < -1.5;
  const accent = overpriced
    ? "text-[var(--negative)]"
    : underpriced
      ? "text-[var(--positive)]"
      : "text-[var(--foreground)]";

  return (
    <Card className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <CardLabel>Prix demandé</CardLabel>
          <div className="text-3xl font-semibold tracking-tight mt-1">
            {formatEur(listing.price_eur)}
          </div>
          {listing.surface_m2 && listing.price_eur ? (
            <div className="text-sm text-[var(--muted)] mt-1 font-mono">
              {Math.round(listing.price_eur / listing.surface_m2).toLocaleString("fr-FR")} €/m²
              {" · "}
              {listing.surface_m2} m²
              {listing.rooms ? ` · ${listing.rooms} pièces` : null}
            </div>
          ) : null}
        </div>

        <div>
          <CardLabel>Estimation marché</CardLabel>
          <div className="text-3xl font-semibold tracking-tight mt-1">
            {formatEur(valuation.fair_value_eur)}
          </div>
          {valuation.price_per_m2_estimate ? (
            <div className="text-sm text-[var(--muted)] mt-1 font-mono">
              {valuation.price_per_m2_estimate.toLocaleString("fr-FR")} €/m² médian
            </div>
          ) : null}
        </div>
      </div>

      <div className="border-t border-[var(--border)] pt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Écart">
          <span className={cn("font-mono", accent)}>
            {formatPct(deltaPct)}
          </span>
        </Stat>
        <Stat label="En €">
          <span className={cn("font-mono", accent)}>
            {deltaEur != null
              ? `${deltaEur > 0 ? "+" : ""}${formatEur(deltaEur)}`
              : "—"}
          </span>
        </Stat>
        <Stat label="Comparables">
          <span className="font-mono">
            {valuation.n_comps} · {tierLabel[valuation.base_tier] ?? valuation.base_tier}
          </span>
        </Stat>
        <Stat label="Confiance">
          <span className={cn("font-mono", confidenceColor[valuation.confidence])}>
            {confidenceLabel[valuation.confidence]}
          </span>
        </Stat>
      </div>

      {valuation.fair_value_low_eur && valuation.fair_value_high_eur ? (
        <div className="text-xs text-[var(--muted)]">
          Fourchette plausible :{" "}
          <span className="font-mono text-[var(--foreground)]">
            {formatEur(valuation.fair_value_low_eur)} – {formatEur(valuation.fair_value_high_eur)}
          </span>
        </div>
      ) : null}

      {valuation.rationale ? (
        <div className="text-xs text-[var(--muted)] leading-relaxed">{valuation.rationale}</div>
      ) : null}
    </Card>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
        {label}
      </div>
      <div className="mt-1 text-base">{children}</div>
    </div>
  );
}
