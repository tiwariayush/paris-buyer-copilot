import { Card, CardLabel, CardTitle } from "./Card";
import type { MarketIndex, Neighborhood } from "@/lib/types";

function formatPpm2(n: number) {
  return `${n.toLocaleString("fr-FR")} €/m²`;
}

export function NeighborhoodCard({
  data,
  marketIndex,
}: {
  data?: Neighborhood | null;
  marketIndex?: MarketIndex | null;
}) {
  if (!data) return null;

  const schools = (data.nearest_schools ?? []).slice(0, 4);
  const transit = (data.nearest_transit ?? []).slice(0, 4);
  const trends = data.market_trends ?? [];

  return (
    <Card>
      <CardLabel>Quartier</CardLabel>
      <CardTitle className="mt-1">
        {data.iris_name ?? data.iris_code ?? data.commune_name ?? "—"}
      </CardTitle>
      {data.market_area_label ? (
        <p className="mt-1 text-xs text-[var(--muted)]">
          Marché DVF · {data.market_area_label}
          {data.trend_yoy_pct != null ? (
            <span
              className={
                data.trend_yoy_pct >= 0
                  ? " text-[var(--negative)]"
                  : " text-[var(--positive)]"
              }
            >
              {" "}
              · {data.trend_yoy_pct >= 0 ? "+" : ""}
              {data.trend_yoy_pct}% sur 1 an (médiane €/m²)
            </span>
          ) : null}
        </p>
      ) : null}

      {(data.population != null || data.median_household_income_eur != null) && (
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          {data.population != null ? (
            <div>
              <div className="text-xs uppercase tracking-wider text-[var(--muted)]">
                Population
              </div>
              <div className="font-medium mt-0.5">
                {data.population.toLocaleString("fr-FR")}
              </div>
            </div>
          ) : null}
          {data.median_household_income_eur != null ? (
            <div>
              <div className="text-xs uppercase tracking-wider text-[var(--muted)]">
                Revenu médian foyer
              </div>
              <div className="font-medium mt-0.5">
                {data.median_household_income_eur.toLocaleString("fr-FR")} €/an
              </div>
              <p className="text-[10px] text-[var(--muted)] mt-0.5">INSEE Filosofi · arrond.</p>
            </div>
          ) : null}
        </div>
      )}

      {trends.length > 0 && (
        <div className="mt-4">
          <div className="text-xs uppercase tracking-wider text-[var(--muted)] mb-2">
            Prix médian appartements (DVF)
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-[var(--muted)] text-left">
                  <th className="pb-1 pr-3">Année</th>
                  <th className="pb-1 pr-3">€/m²</th>
                  <th className="pb-1">Ventes</th>
                </tr>
              </thead>
              <tbody>
                {trends.map((row) => (
                  <tr key={row.year} className="border-t border-[var(--border)]/60">
                    <td className="py-1.5 pr-3">{row.year}</td>
                    <td className="py-1.5 pr-3">{formatPpm2(row.median_price_per_m2)}</td>
                    <td className="py-1.5 text-[var(--muted)]">{row.transaction_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {marketIndex && marketIndex.data_source === "dvf_live" && (
        <p className="mt-3 text-xs text-[var(--muted)]">
          Annonce vs marché local (12 mois, {marketIndex.n_transactions_12m} ventes) :{" "}
          <span className="font-medium text-[var(--foreground)]">
            {marketIndex.listing_vs_median_pct >= 0 ? "+" : ""}
            {marketIndex.listing_vs_median_pct}%
          </span>{" "}
          vs {formatPpm2(marketIndex.arrondissement_median_ppm2)}
        </p>
      )}

      {transit.length > 0 && (
        <div className="mt-4">
          <div className="text-xs uppercase tracking-wider text-[var(--muted)] mb-2">
            Transports
          </div>
          <ul className="space-y-1.5 text-sm">
            {transit.map((t, i) => (
              <li key={i} className="flex justify-between gap-2">
                <span>
                  <span className="font-medium">{t.name}</span>
                  {t.line ? (
                    <span className="text-[var(--muted)]"> · {t.line}</span>
                  ) : null}
                </span>
                <span className="text-xs text-[var(--muted)] flex-shrink-0">
                  {Math.round(t.walk_minutes ?? 0)} min
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4">
        <div className="text-xs uppercase tracking-wider text-[var(--muted)] mb-2">
          Écoles à proximité
        </div>
        {schools.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">Aucune école dans le rayon proche.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {schools.map((s, i) => (
              <li key={i} className="flex items-start justify-between gap-3">
                <span className="font-medium">{s.name ?? "—"}</span>
                <span className="text-xs text-[var(--muted)] flex-shrink-0">
                  {s.nature ?? s.type ?? ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
